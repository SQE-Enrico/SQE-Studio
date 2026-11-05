"""Runs; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError

def list_runs(self,request):
    pid=request.pid
    uid=request.uid
    listed=self.app.store.runs(uid,pid)
    for item in listed:
        item['is_sweep']=False
        if item['state']!='completed':continue
        try:
            _info,run_dir=self._run_folder(uid,pid,item['id'])
            marker=run_dir/'SWEEP_MANIFEST.json'
            item['is_sweep']=marker.is_file() and not marker.is_symlink()
        except ApiError:
            # An unsafe run stays visible as evidence, but is not
            # presented as a verified result or eligible for comparison.
            item['unsafe_location']=True
    return self.send_json({'runs':listed})


def create(self,request):
    pid=request.pid
    uid=request.uid
    obj=self.json_body()
    if set(obj)!={'revision','study_id'}:raise ApiError('Run requires revision and study_id',422)
    return self.send_json({'run_id':self.app.jobs.start(uid,pid,obj['revision'],obj['study_id'])},202)

