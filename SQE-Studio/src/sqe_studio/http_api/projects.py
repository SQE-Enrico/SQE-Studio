"""Projects; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from sqe_studio.contracts import stage_status
from sqe_studio.design_library import instantiate

def list_projects(self,request):
    uid=request.uid
    return self.send_json({'projects':self.app.store.list_projects(uid)})


def create(self,request):
    uid=request.uid
    obj=self.json_body()
    if set(obj) not in ({'name','family'}, {'name','family','template_id'}):
        raise ApiError('Project requires name, family and optional starter design',422)
    name, family=obj['name'],obj['family']
    model=instantiate(obj['template_id'],name,family) if 'template_id' in obj else None
    return self.send_json(self.app.store.create(uid,name,family,model=model),201)


def read(self,request):
    pid=request.pid
    uid=request.uid
    project=self.app.store.project(uid,pid)
    project['stages']=stage_status(project['model'],[r['engine'] for r in self.app.store.runs(uid,pid) if r['state']=='completed' and r['revision_id']==project['head']])
    return self.send_json(project)


def revisions(self,request):
    pid=request.pid
    uid=request.uid
    return self.send_json({'revisions':self.app.store.revisions(uid,pid)})


def revision(self,request):
    parts=request.parts
    pid=request.pid
    uid=request.uid
    return self.send_json(self.app.store.project(uid,pid,parts[4]))


def commit(self,request):
    pid=request.pid
    uid=request.uid
    obj=self.json_body()
    if set(obj)!={'expected_revision','model'}:raise ApiError('Commit requires expected_revision and model',422)
    rid=self.app.store.commit(uid,pid,obj['expected_revision'],obj['model'])
    return self.send_json({'revision':rid})

