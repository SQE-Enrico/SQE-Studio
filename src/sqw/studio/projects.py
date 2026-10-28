"""Project ownership, optimistic drafts, immutable revisions and portable project capsules."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import re
import tempfile
import time
import zipfile

from .auth import Problem
from .db import dumps, uid
from .process import document


class Projects:
    def __init__(self, store): self.store = store

    def access(self, user, project_id, edit=False):
        project = self.store.one('SELECT * FROM projects WHERE id=?', (project_id,))
        if not project: raise Problem('Project not found', 404)
        member = self.store.one('SELECT role FROM members WHERE project_id=? AND user_id=?', (project_id,user['id']))
        role = 'owner' if project['owner_id']==user['id'] or user['role']=='admin' else member['role'] if member else None
        if role is None or (edit and (role=='viewer' or user['role']=='viewer')):
            raise Problem('You do not have access to this operation', 403)
        project['access_role'] = role
        return project

    def list(self, user):
        if user['role']=='admin': rows=self.store.rows('SELECT * FROM projects ORDER BY updated DESC')
        else: rows=self.store.rows('SELECT DISTINCT p.* FROM projects p LEFT JOIN members m ON m.project_id=p.id '
                                  'WHERE p.owner_id=? OR m.user_id=? ORDER BY p.updated DESC',(user['id'],user['id']))
        return [{k:r[k] for k in ('id','name','draft_version','updated','created','owner_id')} for r in rows]

    def create(self, user, name, doc=None):
        if user['role']=='viewer': raise Problem('Researcher access required',403)
        name=str(name).strip()
        if not 1<=len(name)<=100: raise Problem('Project name must have 1–100 characters')
        project_id=uid(); now=time.time()
        with self.store.connect(True) as db:
            db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)',
                       (project_id,name,user['id'],dumps(doc or document()),1,now,now))
        return project_id

    def detail(self,user,project_id):
        p=self.access(user,project_id)
        p['document']=json.loads(p.pop('draft'))
        p['revisions']=self.store.rows('SELECT id,parent_id,note,author_id,created FROM revisions WHERE project_id=? ORDER BY created DESC',(project_id,))
        p['jobs']=self.store.rows('SELECT * FROM jobs WHERE project_id=? ORDER BY created DESC',(project_id,))
        for job in p['jobs']:
            job['options']=json.loads(job['options'])
            job['results']=self.store.rows('SELECT * FROM results WHERE job_id=?',(job['id'],))
        p['assets']=self.store.rows('SELECT * FROM assets WHERE project_id=?',(project_id,))
        p['members']=self.store.rows('SELECT u.id,u.email,u.name,m.role FROM members m JOIN users u ON u.id=m.user_id WHERE project_id=?',(project_id,))
        return p

    def save(self,user,project_id,doc,version):
        self.access(user,project_id,True)
        if not isinstance(doc,dict) or len(dumps(doc))>1_000_000: raise Problem('Invalid or excessively large project document')
        with self.store.connect(True) as db:
            cursor=db.execute('UPDATE projects SET draft=?,draft_version=draft_version+1,updated=? WHERE id=? AND draft_version=?',
                              (dumps(doc),time.time(),project_id,version))
            if cursor.rowcount!=1: raise Problem('A newer draft exists. Reload before saving your changes.',409)
        return {'draft_version':version+1,'saved_at':time.time()}

    def revise(self,user,project_id,note,parent=None,expected_version=None):
        self.access(user,project_id,True)
        if parent and not self.store.one('SELECT id FROM revisions WHERE id=? AND project_id=?',(parent,project_id)):
            raise Problem('Parent revision does not belong to this project')
        revision=uid()
        with self.store.connect(True) as db:
            current=db.execute('SELECT draft,draft_version FROM projects WHERE id=?',(project_id,)).fetchone()
            if expected_version is not None and current['draft_version']!=expected_version:
                raise Problem('The draft changed before snapshotting. Reload and review before running.',409)
            if parent is None:
                latest=db.execute('SELECT id FROM revisions WHERE project_id=? ORDER BY created DESC LIMIT 1',(project_id,)).fetchone()
                parent=latest['id'] if latest else None
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)',
                       (revision,project_id,parent,current['draft'],str(note)[:1000],user['id'],time.time()))
        self.store.audit(user['id'],project_id,'save_revision',{'revision':revision})
        return revision

    def restore(self,user,project_id,revision):
        p=self.access(user,project_id,True)
        r=self.store.one('SELECT * FROM revisions WHERE id=? AND project_id=?',(revision,project_id))
        if not r: raise Problem('Revision not found',404)
        return self.save(user,project_id,json.loads(r['document']),p['draft_version'])

    def share(self,user,project_id,user_email,role):
        p=self.access(user,project_id,True)
        if p['access_role']!='owner': raise Problem('Only the owner or an administrator can manage members',403)
        person=self.store.one('SELECT id FROM users WHERE email=? AND active=1',(str(user_email).lower(),))
        if not person: raise Problem('Create or activate the account before adding it to a project')
        if role not in ('editor','viewer','remove'): raise Problem('Invalid member role')
        with self.store.connect(True) as db:
            db.execute('DELETE FROM members WHERE project_id=? AND user_id=?',(project_id,person['id']))
            if role!='remove': db.execute('INSERT INTO members VALUES(?,?,?)',(project_id,person['id'],role))
        self.store.audit(user['id'],project_id,'change_member',{'user':person['id'],'role':role})

    def asset(self,user,project_id,name,kind,content):
        self.access(user,project_id,True)
        if kind not in ('logo','junction_gds','geometry_gds','data'): raise Problem('Unknown asset type')
        if len(content)>self.store.settings.max_upload_mb*1024**2: raise Problem('Asset exceeds upload limit',413)
        if kind=='logo':
            from PIL import Image
            try:
                with Image.open(io.BytesIO(content)) as image:
                    if image.width*image.height>4_000_000: raise ValueError('Logo exceeds 4 megapixels')
                    image.verify()
            except Exception as exc: raise Problem(f'Upload a valid raster logo: {exc}') from exc
        asset_id=uid(); folder=self.store.root/'assets'/project_id; folder.mkdir(parents=True,exist_ok=True)
        (folder/asset_id).write_bytes(content)
        with self.store.connect(True) as db:
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?)',
                       (asset_id,project_id,Path(name).name[:150],kind,hashlib.sha256(content).hexdigest(),len(content),time.time()))
        return asset_id

    def export(self,user,project_id):
        p=self.access(user,project_id)
        with self.store.connect() as db:
            db.execute('BEGIN')
            p=dict(db.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
            revisions=[dict(r) for r in db.execute('SELECT * FROM revisions WHERE project_id=?',(project_id,))]
            jobs=[dict(r) for r in db.execute('SELECT * FROM jobs WHERE project_id=?',(project_id,))]
            assets=[dict(r) for r in db.execute('SELECT * FROM assets WHERE project_id=?',(project_id,))]
            complete=[j for j in jobs if j['state'] in ('succeeded','failed','cancelled','interrupted')]
            results=[dict(r) for j in complete for r in db.execute('SELECT * FROM results WHERE job_id=?',(j['id'],))]
            db.commit()
        capsule={'schema_version':1,'project':p,'revisions':revisions,'jobs':jobs,'results':results,'assets':assets,
                 'note':'Active workspaces are omitted; finalized checkpoints and the latest partial draft are included.'}
        folder=self.store.root/'exports'; folder.mkdir(exist_ok=True)
        path=folder/f'{uid()}.sqe.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('project.json',dumps(capsule))
            for asset in assets:
                source=self.store.root/'assets'/project_id/asset['id']
                z.write(source,'assets/'+asset['id'])
            for job in complete:
                source=self.store.root/'jobs'/job['id']
                if source.exists():
                    for f in source.rglob('*'):
                        if f.is_file() and not f.is_symlink(): z.write(f,'jobs/'+job['id']+'/'+f.relative_to(source).as_posix())
        return path

    def import_capsule(self,user,content):
        """Validate and stage disk contents before atomically publishing research state."""
        if user['role']=='viewer': raise Problem('Researcher access required',403)
        source=io.BytesIO(content) if isinstance(content,bytes) else content
        with zipfile.ZipFile(source) as z, tempfile.TemporaryDirectory(dir=self.store.root) as temporary:
            staging=Path(temporary)
            info=z.infolist()
            if len(info)>100000 or sum(f.file_size for f in info)>self.store.settings.max_expanded_mb*1024**2:
                raise Problem('Expanded project capsule exceeds the configured server limit',413)
            names=set()
            for f in info:
                path=PurePosixPath(f.filename)
                if (path.is_absolute() or '..' in path.parts or '\\' in f.filename
                        or stat.S_ISLNK(f.external_attr>>16) or f.filename in names):
                    raise Problem('Unsafe or duplicate archive path')
                names.add(f.filename)
            if z.getinfo('project.json').file_size>32*1024**2: raise Problem('Capsule metadata exceeds 32 MiB')
            data=json.loads(z.read('project.json'))
            if data.get('schema_version')!=1: raise Problem('Unsupported project capsule')
            def identities(records):
                ids=[r['id'] for r in records]
                if len(set(ids))!=len(ids) or any(not re.fullmatch(r'[a-f0-9]{32}',v) for v in ids):
                    raise Problem('Capsule contains invalid or duplicate identities')
                return {v:uid() for v in ids}
            assetmap=identities(data['assets'])
            revmap=identities(data['revisions'])
            jobmap=identities(data['jobs'])
            def remap(value):
                if isinstance(value,dict): return {k:remap(v) for k,v in value.items()}
                if isinstance(value,list): return [remap(v) for v in value]
                return assetmap.get(value,value) if isinstance(value,str) else value
            def project_document(value):
                result=remap(json.loads(value))
                if not isinstance(result,dict) or len(dumps(result))>1_000_000:
                    raise Problem('Invalid or excessively large project document')
                return dumps(result)
            draft=project_document(data['project']['draft'])
            for r in data['revisions']:
                r['_document']=project_document(r['document'])
                if r['parent_id'] and r['parent_id'] not in revmap: raise Problem('Unknown parent revision')
            for j in data['jobs']:
                if j['revision_id'] not in revmap: raise Problem('Unknown job revision')
                if j['mode'] not in ('demo','fem'): raise Problem('Invalid job workflow mode')
                j['_options']=dumps(json.loads(j['options']))
            for r in data['results']:
                if r['job_id'] not in jobmap: raise Problem('Unknown result job')
            # All decompression and asset hashing happen before taking the SQLite write lock.
            for a in data['assets']:
                member=z.getinfo('assets/'+a['id'])
                if member.file_size!=a['size'] or member.file_size>self.store.settings.max_upload_mb*1024**2:
                    raise Problem('Asset size mismatch or upload limit exceeded')
                target=staging/'assets'/assetmap[a['id']]
                target.parent.mkdir(exist_ok=True)
                with z.open(member) as src,target.open('wb') as dest: shutil.copyfileobj(src,dest,1024**2)
                from ..io import sha256
                if sha256(target)!=a['sha256']: raise Problem('Asset checksum mismatch')
            for f in info:
                parts=PurePosixPath(f.filename).parts
                if len(parts)>=3 and parts[0]=='jobs' and parts[1] in jobmap and not f.is_dir():
                    target=staging/'jobs'/jobmap[parts[1]]/Path(*parts[2:])
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(f) as src,target.open('wb') as dest: shutil.copyfileobj(src,dest,1024**2)
            project_id=uid(); now=time.time(); published=[]
            try:
                with self.store.connect(True) as db:
                    db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)',
                               (project_id,str(data['project']['name'])[:89]+' (imported)',user['id'],draft,1,now,now))
                    for r in data['revisions']:
                        db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)',
                                   (revmap[r['id']],project_id,revmap.get(r['parent_id']),r['_document'],str(r['note'])[:1000],user['id'],r['created']))
                    for j in data['jobs']:
                        finalized=j['state'] in ('succeeded','failed','cancelled','interrupted')
                        state=j['state'] if finalized else 'interrupted'
                        error=j['error'] if finalized else 'Active workspace was not exported; resume from a completed checkpoint'
                        db.execute('INSERT INTO jobs(id,project_id,revision_id,author_id,target,mode,state,cpus,memory_gb,baseline_id,options,progress,stage,error,created,finished) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                   (jobmap[j['id']],project_id,revmap[j['revision_id']],user['id'],j['target'],j['mode'],state,j['cpus'],j['memory_gb'],jobmap.get(j['baseline_id']),j['_options'],j['progress'],j['stage'],error,j['created'],j['finished'] if finalized else now))
                    for r in data['results']:
                        db.execute('INSERT INTO results(job_id,stage,signature,reused_from,notes) VALUES(?,?,?,?,?)',
                                   (jobmap[r['job_id']],r['stage'],r['signature'],jobmap.get(r['reused_from']),'Imported result; consolidation requires local review.'))
                    for a in data['assets']:
                        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?)',
                                   (assetmap[a['id']],project_id,a['name'],a['kind'],a['sha256'],a['size'],a['created']))
                    if (staging/'assets').exists():
                        target=self.store.root/'assets'/project_id
                        target.parent.mkdir(exist_ok=True)
                        (staging/'assets').rename(target); published.append(target)
                    if (staging/'jobs').exists():
                        (self.store.root/'jobs').mkdir(exist_ok=True)
                        for folder in (staging/'jobs').iterdir():
                            target=self.store.root/'jobs'/folder.name
                            folder.rename(target); published.append(target)
            except Exception:
                for folder in published: shutil.rmtree(folder,ignore_errors=True)
                raise
            self.store.audit(user['id'],project_id,'import_project',{'revision_count':len(revmap),'job_count':len(jobmap)})
            return project_id
