#!/usr/bin/env python3
"""Read a bounded code map or one symbol. Standard library only, no native import.

Examples: python tools/context.py http
          python tools/context.py --symbol sqe_studio.http_api.extraction:extract
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
MAX_OUTPUT_CHARS=16000


def symbols(path):
    """Index declaration ranges without importing scientific packages."""
    source=path.read_text(encoding='utf-8');rows=[]
    if path.suffix=='.py':
        def collect(nodes,prefix=''):
            for node in nodes:
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    rows.append({'name':prefix+node.name,'line':node.lineno,'end':node.end_lineno})
                    if isinstance(node,ast.ClassDef):collect(node.body,node.name+'.')
        collect(ast.parse(source).body)
    elif path.suffix=='.js':
        for line,text in enumerate(source.splitlines(),1):
            match=re.match(r'(?:async )?function ([A-Za-z_$][\w$]*)\(',text)
            if match:rows.append({'name':match[1],'line':line})
    return rows


def area_context(root,area):
    mapping=json.loads((root/'PROJECT_MAP.json').read_text(encoding='utf-8'))
    if area not in mapping['areas']:raise ValueError('Unknown area; run without an area to list choices')
    spec=mapping['areas'][area];found=[]
    for pattern in spec['code']:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                found.append({'file':path.relative_to(root).as_posix(),
                              'symbols':[row['name']+'@'+str(row['line']) for row in symbols(path)]})
    return {'area':area,'purpose':spec['purpose'],'files':found,'tests':spec['tests'],
            'next':'Read only the relevant symbol; do not load the whole repository.'}


def symbol_context(root,selector,max_lines=100):
    try:module,name=selector.split(':',1)
    except ValueError:raise ValueError('Use package.module:Symbol or package.module:Class.method') from None
    if re.fullmatch(r'web/(?:app|modules/[a-z_]+)\.js',module):
        path=root/'src/sqe_studio'/module
    elif re.fullmatch(r'sqe_studio(?:\.[a-z_][a-z_0-9]*)+',module):
        path=root/'src'/Path(*module.split('.')).with_suffix('.py')
    else:raise ValueError('Use a package module or web/modules/name.js')
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to((root/'src').resolve()):
        raise ValueError('Unknown or unsafe source module')
    declarations=symbols(path)
    if path.suffix=='.js':
        count=len(path.read_text(encoding='utf-8').splitlines())
        for i,row in enumerate(declarations):
            row['end']=declarations[i+1]['line']-1 if i+1<len(declarations) else count
    rows=[row for row in declarations if row['name']==name]
    if len(rows)!=1:raise ValueError('Symbol must match exactly one declaration')
    row=rows[0];lines=path.read_text(encoding='utf-8').splitlines()
    end=min(row['end'],row['line']+max_lines-1)
    return {'file':path.relative_to(root).as_posix(),'symbol':name,'line':row['line'],
            'end':row['end'],'truncated':end<row['end'],
            'source':'\n'.join(f'{i+1}: {lines[i]}' for i in range(row['line']-1,end))}


def bounded_json(value,limit=MAX_OUTPUT_CHARS):
    encoded=json.dumps(value,indent=2,ensure_ascii=False)
    if len(encoded)>limit:
        return json.dumps({'status':'CONTEXT_TOO_LARGE','limit_chars':limit,
                           'next':'Use --symbol package.module:name for a smaller source excerpt.'},indent=2)
    return encoded


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('area',nargs='?');parser.add_argument('--symbol')
    parser.add_argument('--max-lines',type=int,default=100,choices=range(1,201),metavar='1..200')
    args=parser.parse_args()
    try:
        if args.symbol:value=symbol_context(ROOT,args.symbol,args.max_lines)
        elif args.area:value=area_context(ROOT,args.area)
        else:
            mapping=json.loads((ROOT/'PROJECT_MAP.json').read_text(encoding='utf-8'))
            value={'start':['AGENTS.md','CURRENT_STATE.json'],
                   'areas':{k:v['purpose'] for k,v in mapping['areas'].items()}}
        print(bounded_json(value));return 0
    except (OSError,ValueError,SyntaxError,KeyError) as error:
        parser.error(str(error))


if __name__=='__main__':raise SystemExit(main())
