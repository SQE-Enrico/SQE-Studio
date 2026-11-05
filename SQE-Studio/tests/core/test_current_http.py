"""Real loopback transport across the extracted resource modules."""
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request

from sqe_studio.testing.native_extraction import FixtureSession
from sqe_studio.web_assets import javascript_bundle


class ModularHTTP(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='sqe-current-http-');self.addCleanup(temp.cleanup)
        self.session=FixtureSession(temp.name).__enter__()
        self.addCleanup(self.session.__exit__,None,None,None)

    def raw(self,path,data=None,**headers):
        request=urllib.request.Request(self.session.base+path,data=data,
            headers={'Content-Type':'application/json',**headers})
        try:response=self.session.client.open(request,timeout=8)
        except urllib.error.HTTPError as error:response=error
        with response:return response.status,response.read(),response.headers

    def test_served_ui_is_the_complete_package_bundle_with_security_headers(self):
        status,data,headers=self.raw('/app.js')
        self.assertEqual(status,200);self.assertEqual(data,javascript_bundle())
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')

    def test_private_catalog_and_revision_routes_still_work(self):
        for path in ('/api/design/templates','/api/design/capabilities','/api/engines',
                     f'/api/projects/{self.session.pid}/revisions'):
            with self.subTest(path=path):self.assertEqual(self.raw(path)[0],200)

    def test_origin_and_host_checks_run_before_resource_dispatch(self):
        status,_,_=self.raw('/api/logout',b'{}',Origin='http://other.invalid',
                           **{'X-CSRF-Token':self.session.csrf})
        self.assertEqual(status,403)
        self.assertEqual(self.raw('/api/design/templates',Host='other.invalid')[0],403)

    def test_duplicate_json_and_missing_csrf_remain_rejected(self):
        status,_,_=self.raw('/api/projects',b'{"name":"one","name":"two","family":"transmon"}',
                           **{'X-CSRF-Token':self.session.csrf})
        self.assertEqual(status,400)
        self.assertEqual(self.raw('/api/logout',b'{}')[0],403)

    def test_unregistered_routes_do_not_bypass_authenticated_project_identity(self):
        for path in ('/api/projects/invalid/run','/api/projects/'+('a'*32)+'/unknown',
                     '/modules/extraction.js'):
            with self.subTest(path=path):self.assertEqual(self.raw(path)[0],404)


if __name__=='__main__':unittest.main()
