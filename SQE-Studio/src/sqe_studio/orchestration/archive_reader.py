"""Bounded portable ZIP reader; no source ownership, merge or historical state."""
import json
from pathlib import Path,PurePosixPath
import zipfile

MAX_ARCHIVE=32_000_000
MAX_MEMBER=12_000_000

class ArchiveCorruptError(ValueError):
    """Invalid ZIP structure/CRC; distinct from baseline source mismatch."""

def safe_name(name: str) -> str:
    if not isinstance(name,str) or len(name)>255 or '\\' in name or '\x00' in name:
        raise ValueError('Invalid or long path')
    p=PurePosixPath(name)
    if (p.is_absolute() or not name or name.startswith('./') or name.startswith('/') or
        any(x in ('..','.','') for x in name.split('/')) or ':' in name or p.as_posix()!=name):
        raise ValueError('Traversal or invalid path')
    # Windows silently collapses trailing dots/spaces and reserves device
    # basenames even when they appear inside a path. Reject on every host so
    # a Linux-produced owned archive cannot alias a file during Win32 merge.
    for component in name.split('/'):
        if (component.endswith(('.', ' ')) or
            component.split('.', 1)[0].upper() in
            {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
             *(f'LPT{i}' for i in range(1, 10))}):
            raise ValueError('Invalid Windows-incompatible path')
    return name

def read_zip(path: Path) -> tuple[dict,dict[str,bytes]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('Archive missing, linked or oversized')
    try:
        with zipfile.ZipFile(path) as bundle:
            infos = bundle.infolist()
            if len(infos) > 250 or not infos:
                raise ValueError('Archive entries duplicated or missing manifest')
            bodies = {}
            seen_portable = set()
            if sum(i.file_size for i in infos) > 64_000_000:
                raise ValueError('Archive decompressed size budget exceeded')
            for info in infos:
                # Do not rely on CPython-private ZIP normalization helpers,
                # locale, or the OS's preferred path separator. The decoded
                # central-directory name *before* normalization is public.
                name = safe_name(info.orig_filename)
                if info.filename != name:
                    raise ValueError('Invalid normalized ZIP member name')
                portable = name.casefold()
                if portable in seen_portable:
                    raise ValueError('Archive entries duplicated or case-colliding')
                seen_portable.add(portable)
                if name.endswith('/') or info.file_size > MAX_MEMBER or info.is_dir():
                    raise ValueError('Unexpected directory or oversized content')
                entry_type = (info.external_attr >> 16) & 0o170000
                if entry_type == 0o120000:
                    raise ValueError('Symlink archive entries forbidden')
                if entry_type not in (0, 0o100000):
                    raise ValueError('Non-regular archive entries forbidden')
                # Pass the checked ZipInfo, not an ambiguous filename lookup.
                # The ZIP reader verifies header-name matching and CRC here.
                bodies[name] = bundle.read(info)
            if 'MANIFEST.json' not in bodies:
                raise ValueError('Archive entries duplicated or missing manifest')
            if bundle.testzip() is not None:
                raise ArchiveCorruptError('Corrupt archive ZIP payload')
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as exc:
        raise ArchiveCorruptError('Corrupt archive ZIP structure or payload') from exc
    metadata = json.loads(bodies.pop('MANIFEST.json'))
    if not isinstance(metadata, dict):
        raise ValueError('Invalid archive manifest object')
    return metadata, bodies
