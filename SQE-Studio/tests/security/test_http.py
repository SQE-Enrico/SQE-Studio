import json
import threading
import urllib.error
import urllib.request
import http.cookiejar
import pytest
from sqe_studio.server import make_server

@pytest.fixture
def host(tmp_path):
    h=make_server(tmp_path,0)
    server_thread=threading.Thread(target=h.serve_forever,daemon=True);server_thread.start()
    try:yield f'http://127.0.0.1:{h.server_port}',h
    finally:h.shutdown();h.server_close();server_thread.join(timeout=3)

def test_http_login_csrf_revision_and_result_access(host):
    base,h=host
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def req(path,method='GET',data=None,csrf='',origin=None,client_override=None):
        headers={}
        if data is not None:headers['Content-Type']='application/json'
        if csrf:headers['X-CSRF-Token']=csrf
        if origin:headers['Origin']=origin
        r=urllib.request.Request(base+path, data=json.dumps(data).encode() if data is not None else None,
                                  headers=headers,method=method)
        try:
            with (client_override or client).open(r,timeout=5) as f:
                return f.status,json.loads(f.read()) if f.headers.get('Content-Type','').startswith('application/json') else f.read()
        except urllib.error.HTTPError as e:
            return e.code,json.loads(e.read())
    assert req('/api/me')[0]==401
    assert req('/api/status')[1]['setup_required']
    token=h.app.setup_file.read_text()
    assert req('/api/setup','POST',{'setup_token':'bad','email':'a@b.com','password':'LongPassword0000'})[0]==403
    assert req('/api/setup','POST',{'setup_token':token,'email':'a@b.com','password':'LongPassword0000'})[0]==200
    assert req('/api/login','POST',{'email':'a@b.com','password':'incorrect'})[0]==401
    code,auth=req('/api/login','POST',{'email':'a@b.com','password':'LongPassword0000'})
    assert code==200;csrf=auth['csrf']
    assert req('/api/projects','POST',{'name':'Secure Project','family':'transmon'})[0]==403
    assert req('/api/projects','POST',{'name':'Secure Project','family':'transmon'},csrf,origin='https://attacker.example')[0]==403
    code,p=req('/api/projects','POST',{'name':'Secure Project','family':'transmon'},csrf)
    assert code==201
    pid=p['id'];assert req('/api/projects')[1]['projects'][0]['id']==pid
    m=p['model'];m['intent']['targets']=[{'name':'f01','value':5.1,'unit':'GHz'}]
    code,v=req('/api/projects/'+pid+'/commit','POST',{'expected_revision':p['head'],'model':m},csrf)
    assert code==200
    assert req('/api/projects/'+pid+'/commit','POST',{'expected_revision':p['head'],'model':m},csrf)[0]==409
    assert req('/api/projects/'+pid+'/runs','POST',{'revision':p['head'],'study_id':'fake'},csrf)[0]==409
    assert req('/api/projects/'+pid+'/runs/not_a_run/download')[0]==404
    assert req('/api/logout','POST',{},csrf)[0]==200
    assert req('/api/projects')[0]==401

def test_static_and_host_header(host):
    base,h=host
    req=urllib.request.Request(base+'/app.js',headers={'Host':'malicious.example'})
    with pytest.raises(urllib.error.HTTPError) as x:urllib.request.urlopen(req)
    assert x.value.code==403
    with urllib.request.urlopen(base+'/app.js') as r:
        body=r.read();assert b'Quantum Metal' in body and b'workspaceBody' in body
