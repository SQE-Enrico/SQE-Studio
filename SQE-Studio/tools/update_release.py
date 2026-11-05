#!/usr/bin/env python3
"""Refresh only current development fingerprints after review and validation.

Does not change frozen numerical/core hashes, declare a reviewer, or approve science.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sqe_studio.governance import fingerprint,check


def main():
    path=ROOT/'DEVELOPMENT_POLICY.json'
    policy=json.loads(path.read_text(encoding='utf-8'))
    old=path.read_bytes()
    policy['protected_fingerprint']=fingerprint(ROOT)
    path.write_text(json.dumps(policy,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    try:check(ROOT)
    except BaseException:
        path.write_bytes(old)
        raise
    return subprocess.call([sys.executable,str(ROOT/'tools/verify_release_source.py'),str(ROOT),'--write'])


if __name__=='__main__':raise SystemExit(main())
