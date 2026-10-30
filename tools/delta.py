#!/usr/bin/env python3
"""Make, verify, admit and deterministically merge owned agent deltas.

Never writes into the baseline source. Paths, hashes, ownership and preimages
are verified. Final integration requires all A01..A08 and re-runs tests.
"""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

AGENTS=[f'A{i:02}' for i in range(1,9)]
EXCLUDE={'FOUNDATION_LOCK.json'}
IGNORED_DIRS={'.git','.venv','studio-data','__pycache__','.pytest_cache','dist','build','node_modules'}

def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def files(root):
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file() and not p.is_symlink() and p.relative_to(root).as_posix() not in EXCLUDE and not any(part in IGNORED_DIRS or part.endswith('.egg-info') for part in p.relative_to(root).parts) and p.suffix not in ('.pyc','.pyo')}
def tree_digest(root):return sha(canonical(files(root)))
def contract_digest(root):
    data={p.relative_to(root).as_posix():sha(p.read_bytes()) for p in (root/'contracts').rglob('*') if p.is_file()}
    return sha(canonical(data))
def ownership(root):return json.loads((root/'contracts/ownership.json').read_text())
def owned(agent,path,owners):
    allowed=owners['agents'][agent]['paths'];frozen=owners['frozen_paths']
    if any(path==f or (f.endswith('/') and path.startswith(f)) for f in frozen):return False
    return any(path==a or (a.endswith('/') and path.startswith(a)) or (a.endswith('_') and path.startswith(a)) for a in allowed)
def valid_path(p):
    if not isinstance(p,str) or not p or p.startswith('/') or '\\' in p or any(x in ('','.','..') for x in p.split('/')):raise ValueError('Unsafe archive path: '+repr(p))
    return p

def lock(root):
    output={'schema':'sqe.foundation-lock.v1','tree_digest':tree_digest(root),'contract_digest':contract_digest(root),'file_count':len(files(root)), 'agent_ids':AGENTS}
    (root/'FOUNDATION_LOCK.json').write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    return output

def baseline(root):
    rec=json.loads((root/'FOUNDATION_LOCK.json').read_text())
    if rec.get('schema')!='sqe.foundation-lock.v1' or rec['tree_digest']!=tree_digest(root) or rec['contract_digest']!=contract_digest(root):
        raise ValueError('Foundation tree or frozen contract digest mismatch')
    return rec

def add_delta(root,modified,agent,output,logs,exit_code):
    b=baseline(root);owners=ownership(root)
    if agent not in AGENTS:raise ValueError('Unknown agent identity')
    old=files(root);new=files(modified)
    changes=[];payloads=[]
    for path in sorted(set(old)|set(new)):
        if old.get(path)==new.get(path):continue
        if not owned(agent,path,owners):raise ValueError('Change outside '+agent+' ownership: '+path)
        row={'path':path,'op':'delete' if path not in new else 'put','preimage_sha256':old.get(path)}
        if path in new:
            row['sha256']=new[path];payloads.append((f'files/{path}',(modified/path).read_bytes()))
        changes.append(row)
    records=[]
    for name in logs:
        p=Path(name)
        if not p.is_file():raise ValueError('Missing test log: '+str(p))
        records.append({'path':'logs/'+p.name,'sha256':sha(p.read_bytes()),'declared_exit_code':exit_code})
        payloads.append(('logs/'+p.name,p.read_bytes()))
    manifest={'schema':'sqe.agent-delta.v1','agent_id':agent,'baseline_tree_digest':b['tree_digest'],
              'frozen_contract_digest':b['contract_digest'],'changes':changes,
              'test_records':records,'dependencies':[], 'limitations':[],
              'note':'Test exit code is declared by the submitting agent; log checksum is independently verified.'}
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('DELTA_MANIFEST.json',json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        for key,data in payloads:z.writestr(key,data)
    return manifest

def read_delta(root,archive):
    b=baseline(root);owners=ownership(root)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP entries')
        for i in z.infolist():
            valid_path(i.filename)
            if i.is_dir() or (i.external_attr>>16)&0o170000==0o120000:raise ValueError('Directory/symlink ZIP entries prohibited')
        if 'DELTA_MANIFEST.json' not in names:raise ValueError('Missing DELTA_MANIFEST.json')
        m=json.loads(z.read('DELTA_MANIFEST.json'))
        if set(m)!={'schema','agent_id','baseline_tree_digest','frozen_contract_digest','changes','test_records','dependencies','limitations','note'}:raise ValueError('Delta manifest schema mismatch')
        agent=m['agent_id']
        if m['schema']!='sqe.agent-delta.v1' or agent not in AGENTS:raise ValueError('Invalid delta identity')
        if (m['baseline_tree_digest'],m['frozen_contract_digest'])!=(b['tree_digest'],b['contract_digest']):raise ValueError('Baseline or contract hash mismatch')
        changes=m['changes'];changed=set();wanted={'DELTA_MANIFEST.json'}
        if not isinstance(changes,list):raise ValueError('Expected changes list')
        for row in changes:
            if set(row) not in ({'path','op','preimage_sha256','sha256'},{'path','op','preimage_sha256'}):raise ValueError('Invalid change fields')
            path=valid_path(row['path'])
            if path in changed or not owned(agent,path,owners):raise ValueError('Duplicate/unowned path '+path)
            changed.add(path)
            pre=(root/path)
            old=sha(pre.read_bytes()) if pre.is_file() else None
            if row['preimage_sha256']!=old:raise ValueError('Preimage mismatch '+path)
            if row['op']=='put':
                key='files/'+path;wanted.add(key)
                if key not in names or sha(z.read(key))!=row.get('sha256'):raise ValueError('File hash mismatch '+path)
            elif row['op']=='delete':
                if 'sha256' in row or old is None:raise ValueError('Invalid deletion '+path)
            else: raise ValueError('Unknown operation')
        for record in m['test_records']:
            if set(record)!={'path','sha256','declared_exit_code'}:raise ValueError('Test record fields mismatch')
            key=valid_path(record['path']);wanted.add(key)
            if not key.startswith('logs/') or key not in names or sha(z.read(key))!=record['sha256']:
                raise ValueError('Test record integrity error')
            if record['declared_exit_code'] is None or type(record['declared_exit_code']) is not int:
                raise ValueError('Every test log must declare its actual exit code; edit manifest before admission')
        if not m['test_records']:raise ValueError('At least one test log required')
        if not isinstance(m['dependencies'],list) or any(x not in AGENTS or x==agent for x in m['dependencies']):raise ValueError('Invalid declared dependencies')
        if not isinstance(m['limitations'],list):raise ValueError('Invalid limitations')
        if set(names)!=wanted:raise ValueError('Extra or missing delta payloads: '+repr(set(names)^wanted))
        return m

def merge(root,archives,output,dry):
    seen={};changed={}
    for archive in archives:
        m=read_delta(root,archive);a=m['agent_id']
        if a in seen:raise ValueError('Duplicate agent delta '+a)
        seen[a]=m
        for row in m['changes']:
            p=row['path']
            if p in changed:raise ValueError('Conflicting source path '+p)
            changed[p]=(archive,row)
    missing=set(AGENTS)-set(seen)
    if missing:raise ValueError('Required agent deltas missing: '+','.join(sorted(missing)))
    for a,m in seen.items():
        if not set(m['dependencies'])<=set(seen):raise ValueError('Unmet agent dependency '+a)
    if dry:
        return {'status':'dry_run_ok','agents':sorted(seen),'changes':len(changed)}
    with tempfile.TemporaryDirectory(prefix='sqe-merge-') as td:
        staging=Path(td)/'SQE-Studio';shutil.copytree(root,staging)
        for path,(archive,row) in sorted(changed.items()):
            target=staging/path
            if row['op']=='delete':target.unlink()
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with zipfile.ZipFile(archive) as z:target.write_bytes(z.read('files/'+path))
        # Migration of frozen contracts requires a separate reviewed change; agents cannot edit them.
        if contract_digest(staging)!=contract_digest(root):raise ValueError('Frozen contract changed')
        report={'schema':'sqe.integration.v1','status':'MERGED_NOT_QUALIFIED','baseline':baseline(root),
                'agent_ids':sorted(seen),'delta_sha256':{a:sha(Path(p).read_bytes()) for p in archives for a in [read_delta(root,p)['agent_id']]},
                'changes':len(changed),'scientific_status':'not_independently_validated','release_candidate':'blocked_pending_full_regression'}
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(staging.rglob('*')):
                if p.is_file():z.write(p,'SQE-Studio/'+p.relative_to(staging).as_posix())
            z.writestr('INTEGRATION_MANIFEST.json',json.dumps(report,indent=2,sort_keys=True)+'\n')
        return report

def main():
    parser=argparse.ArgumentParser(description='SQE Studio ownership-verified agent delta tooling')
    commands=parser.add_subparsers(dest='command',required=True)
    l=commands.add_parser('lock');l.add_argument('foundation')
    v=commands.add_parser('verify');v.add_argument('foundation')
    d=commands.add_parser('pack');d.add_argument('foundation');d.add_argument('modified');d.add_argument('agent');d.add_argument('output');d.add_argument('--log',action='append',default=[]);d.add_argument('--exit-code',type=int,required=True)
    a=commands.add_parser('admit');a.add_argument('foundation');a.add_argument('deltas',nargs='+')
    m=commands.add_parser('merge');m.add_argument('foundation');m.add_argument('output');m.add_argument('deltas',nargs='+');m.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:
        root=Path(args.foundation).resolve()
        if args.command=='lock':result=lock(root)
        elif args.command=='verify':result=baseline(root)
        elif args.command=='pack':result=add_delta(root,Path(args.modified),args.agent,Path(args.output),args.log,args.exit_code)
        elif args.command=='admit':result=[{'file':p,'agent_id':read_delta(root,p)['agent_id']} for p in args.deltas]
        else:result=merge(root,args.deltas,Path(args.output),args.dry_run)
        print(json.dumps(result,indent=2,sort_keys=True));return 0
    except (ValueError,KeyError,OSError,zipfile.BadZipFile) as e:print('REJECT:',e,file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
