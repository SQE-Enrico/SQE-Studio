"""Serve the ordered UI modules as one classic script, without a build tool.

Module order is explicit in web/modules.json. There is one copy of each function;
no generated bundle is kept in the repository. HTTP still exposes /app.js.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

WEB_ROOT=Path(__file__).parent/'web'
ASSETS={'index.html':'text/html; charset=utf-8',
        'app.js':'text/javascript; charset=utf-8',
        'style.css':'text/css; charset=utf-8'}
MODULE_PATH=re.compile(r'(?:app|modules/[a-z_]+)\.js\Z')
MAX_BUNDLE_BYTES=1024*1024


def javascript_sources(web_root: Path | None=None) -> list[Path]:
    """Resolve only regular, bounded, package-owned module paths."""
    root=Path(web_root) if web_root is not None else WEB_ROOT
    manifest=root/'modules.json'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size>8192:
        raise ValueError('Missing or unsafe UI module manifest')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    names=data.get('scripts') if isinstance(data,dict) else None
    if (not isinstance(data,dict) or data.get('schema')!='sqe.web-modules.v1' or not isinstance(names,list)
            or not 2<=len(names)<=40 or names[0]!='app.js'
            or any(not isinstance(n,str) or not MODULE_PATH.fullmatch(n) for n in names)
            or len(set(names))!=len(names)):
        raise ValueError('Invalid UI module manifest')
    paths=[];total=0
    for name in names:
        path=root/name
        if (path.is_symlink() or path.parent.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('Unsafe or missing UI module: '+name)
        total+=path.stat().st_size
        if total>MAX_BUNDLE_BYTES:raise ValueError('UI source exceeds bundle budget')
        paths.append(path)
    return paths


def javascript_bundle(web_root: Path | None=None) -> bytes:
    return b''.join(path.read_bytes() for path in javascript_sources(web_root))


def read_asset(name: str) -> bytes:
    if name not in ASSETS:raise ValueError('Unknown UI asset')
    if name=='app.js':return javascript_bundle()
    return (WEB_ROOT/name).read_bytes()
