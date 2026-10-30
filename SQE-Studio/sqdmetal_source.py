"""Opt-in, provenance-recorded acquisition of upstream SQDMetal sources.

Desktop scientific-environment provisioning only; never available to HTTP/jobs.
First successful acquisition pins the official Git commit and the downloaded
archive SHA-256. Later installs use that exact cached archive unless the user
explicitly requests an upgrade. An upstream GitHub commit is NOT independent
code review or a scientific qualification.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import urllib.request
import zipfile

REPOSITORY = 'sqdlab/SQDMetal'
COMMIT_ENDPOINT = 'https://api.github.com/repos/sqdlab/SQDMetal/commits/main'
ARCHIVE_BASE = 'https://codeload.github.com/sqdlab/SQDMetal/zip/'
SCHEMA = 'sqe.sqdmetal-source-pin.v1'
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024
MAX_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_FILES = 12000
HEX40 = re.compile(r'[a-f0-9]{40}\Z')
HEX64 = re.compile(r'[a-f0-9]{64}\Z')


class UpstreamSourceError(ValueError):
    """Fail closed for an untrusted, malformed or unavailable source."""


def _request(opener, url: str, *, allowed_host: str, limit: int) -> bytes:
    from urllib.parse import urlparse
    req = urllib.request.Request(url, headers={
        'User-Agent': 'SQE-Studio-Scientific-Setup/0.1.1',
        'Accept': 'application/vnd.github+json' if 'api.github' in url else 'application/zip',
    })
    try:
        with opener(req, timeout=45) as response:
            final_url = response.geturl()
            if urlparse(final_url).scheme != 'https' or urlparse(final_url).hostname != allowed_host:
                raise UpstreamSourceError('Official GitHub source redirected to a different host')
            pieces = []
            total = 0
            while True:
                piece = response.read(min(1024 * 1024, limit + 1 - total))
                if not piece:
                    break
                total += len(piece)
                if total > limit:
                    raise UpstreamSourceError('Official source exceeds download size limit')
                pieces.append(piece)
            return b''.join(pieces)
    except (OSError, TimeoutError) as exc:
        raise UpstreamSourceError('Cannot retrieve official SQDMetal source over HTTPS: '+type(exc).__name__) from exc


def _current_commit(opener) -> str:
    try:
        obj = json.loads(_request(opener, COMMIT_ENDPOINT, allowed_host='api.github.com', limit=128000))
    except UpstreamSourceError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise UpstreamSourceError('GitHub returned invalid official commit metadata') from exc
    sha = obj.get('sha') if isinstance(obj, dict) else None
    if not isinstance(sha, str) or not HEX40.fullmatch(sha):
        raise UpstreamSourceError('Official GitHub API response has no valid immutable Git SHA')
    return sha


def _read_pin(root: Path) -> dict | None:
    try:
        doc = json.loads((root/'pin.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (not isinstance(doc, dict) or doc.get('schema') != SCHEMA or
        doc.get('repository') != REPOSITORY or
        not isinstance(doc.get('commit'), str) or not HEX40.fullmatch(doc['commit']) or
        not isinstance(doc.get('archive_sha256'), str) or not HEX64.fullmatch(doc['archive_sha256'])):
        return None
    return doc


def _check_zip(data: bytes, commit: str):
    """Validate the complete ZIP before any member is extracted or pip executes."""
    from io import BytesIO
    try:
        archive = zipfile.ZipFile(BytesIO(data))
        infos = archive.infolist()
        if not infos or len(infos) > MAX_FILES:
            raise UpstreamSourceError('Official archive has an invalid number of files')
        prefix = 'SQDMetal-' + commit + '/'
        total = 0
        names = set()
        for entry in infos:
            # ZIP filenames can be silently normalized by Python's zipfile
            # reader on Windows (backslash -> slash, NUL truncation). Reject
            # the original name BEFORE accepting its normalized form.
            raw_name = entry.orig_filename
            name = entry.filename
            if (raw_name != name or '\\' in raw_name or '\x00' in raw_name or
                    not name.startswith(prefix)):
                raise UpstreamSourceError('Archive contains an unexpected or unsafe path')
            relative = name[len(prefix):]
            bits = relative.rstrip('/').split('/')
            if not relative or any(part in ('', '.', '..') for part in bits):
                if relative: raise UpstreamSourceError('Archive path is not normalized')
                continue
            if name.casefold() in names:
                raise UpstreamSourceError('Archive has duplicate file paths')
            names.add(name.casefold())
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise UpstreamSourceError('Archive contains a link or special file')
            total += entry.file_size
            if total > MAX_UNPACKED_BYTES:
                raise UpstreamSourceError('Archive expands beyond the permitted size')
        required = {prefix+'pyproject.toml',
                    prefix+'SQDMetal/PALACE/Eigenmode_Simulation.py'}
        if not required.issubset({e.filename for e in infos}):
            raise UpstreamSourceError('Upstream archive lacks required SQDMetal files')
        return archive, prefix
    except (zipfile.BadZipFile, OSError) as exc:
        raise UpstreamSourceError('Official SQDMetal download is not a valid ZIP') from exc


def acquire_source(cache: Path, notify, *, opener=urllib.request.urlopen,
                   refresh: bool = False) -> dict:
    """Acquire and lock an official archive. Does not install or execute it.

    A cached pin is reused only if its entire ZIP matches its recorded digest.
    A failed refresh never overwrites the working pin/cache.
    """
    cache = Path(cache)
    pin = _read_pin(cache)
    if (cache/'pin.json').exists() and pin is None:
        raise UpstreamSourceError('Existing SQDMetal source pin is invalid; no automatic replacement permitted')
    if pin is not None and not refresh:
        path = cache / (pin['commit'] + '.zip')
        if not path.is_file() or path.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise UpstreamSourceError('Pinned SQDMetal archive missing or oversized; request a new reviewed download')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != pin['archive_sha256']:
            raise UpstreamSourceError('Pinned SQDMetal archive SHA-256 differs; refusing installation')
        _check_zip(data, pin['commit'])
        notify('Reusing official SQDMetal commit '+pin['commit'][:12]+'; archive SHA-256 verified')
        return {'archive':path, 'commit':pin['commit'], 'archive_sha256':pin['archive_sha256'], 'reused':True}

    notify('Resolving the official sqdlab/SQDMetal main revision over HTTPS')
    commit = _current_commit(opener)
    notify('Official upstream commit: '+commit)
    content = _request(opener, ARCHIVE_BASE+commit, allowed_host='codeload.github.com', limit=MAX_DOWNLOAD_BYTES)
    archive, prefix = _check_zip(content, commit)
    archive.close()
    digest = hashlib.sha256(content).hexdigest()
    notify('Official source ZIP SHA-256: '+digest)
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / (commit+'.zip')
    pinfile = cache/'pin.json'
    # Same-file staging + atomic replace. No partial pin on network failure.
    pending = dest.with_suffix('.zip.pending')
    marker = pinfile.with_suffix('.json.pending')
    try:
        with pending.open('wb') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(pending, dest)
        doc = {'schema':SCHEMA,'repository':REPOSITORY,'commit':commit,
               'archive_sha256':digest,'archive_url':ARCHIVE_BASE+commit,
               'trust':'Official HTTPS GitHub commit, not independently audited',
               'status':'SOURCE_ACQUIRED_NOT_INSTALLED_NOT_QUALIFIED'}
        marker.write_text(json.dumps(doc,indent=2,sort_keys=True)+'\n', encoding='utf-8')
        os.replace(marker,pinfile)
    finally:
        pending.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
    return {'archive':dest,'commit':commit,'archive_sha256':digest,'reused':False}


def extract_checked(acquired: dict, destination: Path) -> Path:
    """Extract verified pinned ZIP to a disposable directory; no arbitrary paths."""
    data = Path(acquired['archive']).read_bytes()
    if hashlib.sha256(data).hexdigest() != acquired['archive_sha256']:
        raise UpstreamSourceError('Official source ZIP has changed since acquisition')
    archive, prefix = _check_zip(data, acquired['commit'])
    destination = Path(destination)
    root = destination / prefix.rstrip('/')
    destination.mkdir(parents=True, exist_ok=True)
    try:
        for info in archive.infolist():
            relative = info.filename[len(prefix):]
            if not relative:
                continue
            dest = root.joinpath(*relative.split('/'))
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, dest.open('wb') as sink:
                    import shutil
                    shutil.copyfileobj(src,sink,1024*1024)
    finally:
        archive.close()
    return root
