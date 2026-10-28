"""Actual HTTP login and real concurrent subprocess jobs; no browser or native FEM mocked."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import http.cookiejar
from wsgiref.simple_server import make_server, WSGIRequestHandler

from sqw.studio.launch import ThreadedServer
from sqw.studio.server import Application
from sqw.studio.settings import Settings
from sqw.studio.jobs import Scheduler


class QuietHandler(WSGIRequestHandler):
    def log_message(self,*args): pass


class RemoteTests(unittest.TestCase):
    def test_actual_http_setup_login_and_project_creation(self):
        with tempfile.TemporaryDirectory() as d:
            application=Application(Settings(Path(d)))
            server=make_server('127.0.0.1',0,application,server_class=ThreadedServer,handler_class=QuietHandler)
            origin=f'http://127.0.0.1:{server.server_port}'
            application.settings.origin=origin
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def request(path,body=None,csrf=None):
                headers={'Origin':origin}
                if csrf: headers['X-CSRF-Token']=csrf
                data=None
                if body is not None: data=json.dumps(body).encode(); headers['Content-Type']='application/json'
                with client.open(urllib.request.Request(origin+path,data=data,headers=headers),timeout=10) as response:
                    return json.loads(response.read())
            try:
                request('/api/auth/setup',{'token':application.auth.setup_token(),'email':'http@example.org','name':'HTTP user','password':'long scientific password'})
                session=request('/api/auth/login',{'email':'http@example.org','password':'long scientific password'})
                created=request('/api/projects',{'name':'Created over HTTP'},session['csrf'])
                project=request('/api/projects/'+created['id'])
                self.assertEqual(project['name'],'Created over HTTP')
                with client.open(origin+'/') as response:
                    self.assertIn(b'SQE Studio',response.read())
                with client.open(origin+'/app.js') as response:
                    self.assertIn(b'Run to report',response.read())
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_real_concurrent_workers_and_queued_admission(self):
        with tempfile.TemporaryDirectory() as d:
            app=Application(Settings(Path(d),total_cpus=4,total_memory_gb=8,max_jobs=2))
            app.auth.setup(app.auth.setup_token(),'owner@example.org','Owner','long scientific password')
            _,_,user=app.auth.login('owner@example.org','long scientific password','local')
            jobs=[]
            for i in range(3):
                project=app.projects.create(user,f'Concurrent project {i}')
                revision=app.projects.revise(user,project,'Parallel test')
                jobs.append(app.jobs.enqueue(user,project,revision,'report',cpus=2,memory_gb=2))
            scheduler=Scheduler(app.store); scheduler.acquire()
            try:
                scheduler.tick(); scheduler.tick(); scheduler.tick()
                states=[app.store.one('SELECT state FROM jobs WHERE id=?',(job,))['state'] for job in jobs]
                self.assertEqual(states[:2],['running','running'])
                self.assertEqual(states[2],'queued')
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    scheduler.tick()
                    states=[app.store.one('SELECT state FROM jobs WHERE id=?',(job,))['state'] for job in jobs]
                    if all(s in ('succeeded','failed','interrupted','cancelled') for s in states): break
                    time.sleep(.1)
                self.assertEqual(states,['succeeded']*3,
                    [app.store.one('SELECT state,error FROM jobs WHERE id=?',(job,)) for job in jobs])
            finally:
                for process in scheduler.children.values():
                    if process.poll() is None:
                        import os,signal
                        os.killpg(process.pid,signal.SIGTERM)
                        process.wait(timeout=10)
                scheduler.lock.close()



class RecoveryTests(unittest.TestCase):
    def test_running_macro_can_be_cancelled_and_queue_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            app=Application(Settings(Path(d),max_jobs=1))
            app.auth.setup(app.auth.setup_token(),'owner@example.org','Owner','long scientific password')
            _,_,user=app.auth.login('owner@example.org','long scientific password','local')
            p=app.projects.create(user,'Cancellation test')
            revision=app.projects.revise(user,p,'Before macro')
            macro=app.jobs.save_macro(user,'Slow trusted test','def apply(project):\n import time\n time.sleep(30)\n return project\n')
            app.jobs.approve_macro(user,macro)
            job=app.jobs.enqueue(user,p,revision,'macro:'+macro)
            next_job=app.jobs.enqueue(user,p,revision,'spec')
            scheduler=Scheduler(app.store); scheduler.acquire()
            try:
                scheduler.tick()
                deadline=time.monotonic()+10
                while time.monotonic()<deadline and not (Path(d)/'jobs'/job/'macro.py').exists(): time.sleep(.05)
                self.assertTrue((Path(d)/'jobs'/job/'macro.py').exists())
                app.jobs.cancel(user,job)
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    scheduler.tick()
                    state=app.store.one('SELECT state FROM jobs WHERE id=?',(next_job,))['state']
                    if state=='succeeded': break
                    time.sleep(.1)
                self.assertEqual(app.store.one('SELECT state FROM jobs WHERE id=?',(job,))['state'],'cancelled')
                self.assertEqual(state,'succeeded')
            finally:
                for process in scheduler.children.values():
                    if process.poll() is None:
                        import os,signal
                        os.killpg(process.pid,signal.SIGTERM); process.wait(timeout=10)
                scheduler.lock.close()

    def test_expired_heartbeat_becomes_interrupted_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            app=Application(Settings(Path(d)))
            app.auth.setup(app.auth.setup_token(),'owner@example.org','Owner','long scientific password')
            _,_,u=app.auth.login('owner@example.org','long scientific password','local')
            p=app.projects.create(u,'Recovery'); rev=app.projects.revise(u,p,'Initial')
            job=app.jobs.enqueue(u,p,rev,'spec')
            with app.store.connect(True) as db:
                db.execute("UPDATE jobs SET state='running',started=?,heartbeat=? WHERE id=?",(time.time()-200,time.time()-200,job))
            reopened=Application(Settings(Path(d)))
            Scheduler(reopened.store).tick()
            record=reopened.store.one('SELECT state,error FROM jobs WHERE id=?',(job,))
            self.assertEqual(record['state'],'interrupted')
            self.assertIn('heartbeat expired',record['error'])


if __name__=='__main__': unittest.main()
