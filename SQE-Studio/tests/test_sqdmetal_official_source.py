"""No network tests: official provenance, ZIP limits, cache pin, installer fail-closed."""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(file, name):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

s = load('sqdmetal_source.py','sqdmetal_source')
w = load('workstation_setup.py','workstation_setup')
COMMIT='a'*40

def archive(commit=COMMIT, *, malicious=None, drop=None):
    buf=io.BytesIO()
    root=f'SQDMetal-{commit}/'
    names={root+'pyproject.toml':'[project]\nname = "SQDMetal"\n',
           root+'SQDMetal/PALACE/Eigenmode_Simulation.py':'# package fixture\n'}
    if drop: del names[root+drop]
    if malicious: names[malicious]='bad'
    with ZipFile(buf,'w') as z:
        for k,v in names.items():z.writestr(k,v)
    data = buf.getvalue()
    # On Windows zipfile normalizes backslashes to forward slashes while
    # creating ZipInfo. To exercise the REAL hostile ZIP bytes on every OS,
    # restore the backslash in both the local and central directory headers.
    # This metadata-only, length-preserving change does not alter file CRCs.
    if malicious and "\\" in malicious:
        normalized = malicious.replace("\\", "/").encode('utf-8')
        original = malicious.encode('utf-8')
        if normalized != original:
            if data.count(normalized) == 2:  # Windows zipfile normalized separators
                data = data.replace(normalized, original)
            else:  # POSIX zipfile preserves the hostile backslash
                assert data.count(original) == 2, 'ZIP fixture did not preserve the member name'
    return data

class Response:
    def __init__(self, url, content):self.url=url;self.bytes=content;self.pos=0
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def geturl(self):return self.url
    def read(self, size=-1):
        if size<0:size=len(self.bytes)-self.pos
        data=self.bytes[self.pos:self.pos+size]
        self.pos+=len(data)
        return data

class Official:
    def __init__(self, commit=COMMIT): self.calls=[];self.commit=commit
    def __call__(self, req, timeout):
        url=req.full_url
        self.calls.append(url)
        if url==s.COMMIT_ENDPOINT:
            return Response(url,json.dumps({'sha':self.commit}).encode())
        if url==s.ARCHIVE_BASE+self.commit:
            return Response(url,archive(self.commit))
        raise AssertionError(url)

def fake_venv(tmp_path):
    project=tmp_path/'source-project';base=tmp_path/'appdata'
    loc=w.managed_root(project,base=base)
    p=loc/'venv'/'Scripts'/'python.exe'
    p.parent.mkdir(parents=True)
    p.write_bytes(b'fake')
    (loc/'ready.json').write_text(json.dumps({'schema':'sqe.local-python-runtime.v1',
                'python_version':'3.11','source_path_sha256':w._project_digest(project)}))
    return project,base,p


def test_download_pin_reuses_exact_bytes_without_network(tmp_path):
    http=Official()
    msgs=[]
    result=s.acquire_source(tmp_path,msgs.append,opener=http)
    assert len(http.calls)==2
    assert result['commit']==COMMIT and result['reused'] is False
    assert hashlib.sha256(result['archive'].read_bytes()).hexdigest()==result['archive_sha256']
    assert (tmp_path/'pin.json').is_file()
    again=s.acquire_source(tmp_path,msgs.append,opener=lambda *_args,**_kw:pytest.fail('network attempted'))
    assert again['reused'] is True
    assert again['archive_sha256']==result['archive_sha256']
    with __import__('tempfile').TemporaryDirectory() as folder:
        extracted=s.extract_checked(again,Path(folder))
        assert (extracted/'SQDMetal'/'PALACE'/'Eigenmode_Simulation.py').is_file()
    assert len(http.calls)==2


def test_modified_cache_rejected_without_reinstall_or_fallback(tmp_path):
    result=s.acquire_source(tmp_path,lambda *_:None,opener=Official())
    result['archive'].write_bytes(b'tampered')
    with pytest.raises(s.UpstreamSourceError,match='SHA-256'):
        s.acquire_source(tmp_path,lambda *_:None,opener=lambda *_a,**_k:pytest.fail('network fallback'))


def test_explicit_refresh_changes_pin_only_on_success(tmp_path):
    s.acquire_source(tmp_path,lambda *_:None,opener=Official())
    original=(tmp_path/'pin.json').read_bytes()
    with pytest.raises(s.UpstreamSourceError):
        s.acquire_source(tmp_path,lambda *_:None,opener=Official('n'*40),refresh=True)
    assert (tmp_path/'pin.json').read_bytes()==original
    refreshed=s.acquire_source(tmp_path,lambda *_:None,opener=Official('b'*40),refresh=True)
    assert refreshed['commit']=='b'*40 and (tmp_path/'pin.json').read_bytes()!=original


@pytest.mark.parametrize('name', [
 'SQDMetal-'+COMMIT+'/../../evil.py',
 'SQDMetal-'+COMMIT+'/SQDMetal/../evil.py',
 'SQDMetal-'+COMMIT+'/SQDMetal\\evil.py',
 'foreign/'+COMMIT+'/evil.py',
])
def test_unsafe_archive_rejected(name):
    payload = archive(malicious=name)
    with ZipFile(io.BytesIO(payload)) as source:
        # ZipInfo.filename is normalized on Windows; orig_filename retains
        # the decoded original member name from the ZIP central directory.
        # Verify the hostile bytes survived the fixture writer before testing
        # the real validation path, on both Windows and POSIX.
        assert name in [member.orig_filename for member in source.infolist()]
    with pytest.raises(s.UpstreamSourceError,match='unsafe|normalized'):
        s._check_zip(payload,COMMIT)


def test_windows_zipfile_normalization_cannot_bypass_validator(monkeypatch):
    """Simulate Windows filename normalization using the public ZipFile API.

    zipfile private internals vary across Python versions. We emulate only
    the public ZipInfo.filename/orig_filename behavior and verify that the
    validator inspects the original path as well as the normalized one.
    """
    import zipfile
    name = f'SQDMetal-{COMMIT}/SQDMetal\\evil.py'
    payload = archive(malicious=name)
    actual_infolist = zipfile.ZipFile.infolist

    def windows_infolist(reader):
        infos = actual_infolist(reader)
        for info in infos:
            info.filename = info.filename.replace('\\', '/')
        return infos

    with monkeypatch.context() as patched:
        patched.setattr(zipfile.ZipFile, 'infolist', windows_infolist)
        with ZipFile(io.BytesIO(payload)) as source:
            entry = next(info for info in source.infolist() if info.orig_filename == name)
            assert entry.filename != entry.orig_filename
        with pytest.raises(s.UpstreamSourceError, match='unsafe'):
            s._check_zip(payload, COMMIT)


def test_null_byte_in_raw_member_name_rejected():
    """ZIP parsers may strip a NUL from the exposed normalized filename."""
    placeholder = f'SQDMetal-{COMMIT}/SQDMetal/evil~.py'
    payload = archive(malicious=placeholder)
    original = placeholder.encode('utf-8')
    dangerous = placeholder.replace('~', '\x00').encode('utf-8')
    assert payload.count(original) == 2
    payload = payload.replace(original, dangerous)
    with ZipFile(io.BytesIO(payload)) as source:
        assert any('\x00' in entry.orig_filename for entry in source.infolist())
    with pytest.raises(s.UpstreamSourceError, match='unsafe'):
        s._check_zip(payload, COMMIT)


def test_symlink_rejected():
    from zipfile import ZipInfo
    buf=io.BytesIO()
    with ZipFile(buf,'w') as z:
        for name, text in [(f'SQDMetal-{COMMIT}/pyproject.toml','[project]\nname="SQDMetal"'),
                          (f'SQDMetal-{COMMIT}/SQDMetal/PALACE/Eigenmode_Simulation.py','native')]:
            z.writestr(name,text)
        link=ZipInfo(f'SQDMetal-{COMMIT}/link')
        link.create_system=3
        link.external_attr=(0o120777 << 16)
        z.writestr(link,'../../evil')
    with pytest.raises(s.UpstreamSourceError,match='link'):
        s._check_zip(buf.getvalue(),COMMIT)


def test_missing_required_file_rejected():
    with pytest.raises(s.UpstreamSourceError,match='required'):
        s._check_zip(archive(drop='pyproject.toml'),COMMIT)


def test_redirect_to_other_host_rejected():
    def bad(req,timeout):return Response('https://evil.example.com/zip',b'a')
    with pytest.raises(s.UpstreamSourceError,match='redirected'):
        s._current_commit(bad)


def test_invalid_git_api_commit_rejected():
    def bad(req,timeout):return Response(s.COMMIT_ENDPOINT,b'{"sha":"HEAD"}')
    with pytest.raises(s.UpstreamSourceError,match='valid immutable Git SHA'):
        s._current_commit(bad)


def test_automatic_source_uses_managed_python_and_reports_exact_pin(tmp_path,monkeypatch):
    project,base,py=fake_venv(tmp_path)
    http=Official()
    monkeypatch.setattr(w,'acquire_source',lambda cache,notify,refresh=False:
                        s.acquire_source(cache,notify,opener=http,refresh=refresh))
    commands=[]
    def run(args,**kwargs):
        commands.append((args,kwargs))
        assert kwargs['shell'] is False
        return SimpleNamespace(returncode=0,stdout='pip ok',stderr='')
    result=w.install_selected(project,['sqdmetal'],lambda *_:None,base=base,run=run)
    assert result['groups']['sqdmetal']['status']=='INSTALLED_UNQUALIFIED'
    assert COMMIT in result['groups']['sqdmetal']['message']
    assert len(commands)==1 and commands[0][0][0]==str(py)
    assert commands[0][0][-1].endswith('SQDMetal-'+COMMIT)
    assert not Path(commands[0][0][-1]).exists(), 'temporary third-party source not retained'
    assert len(http.calls)==2
    result2=w.install_selected(project,['sqdmetal'],lambda *_:None,base=base,run=run)
    assert result2['groups']['sqdmetal']['status']=='INSTALLED_UNQUALIFIED'
    assert len(http.calls)==2,'saved pin must avoid silent upstream updates'


def test_failed_remote_acquisition_aborts_before_other_group_install(tmp_path,monkeypatch):
    project,base,_=fake_venv(tmp_path)
    monkeypatch.setattr(w,'acquire_source',lambda *_a,**_k:(_ for _ in ()).throw(s.UpstreamSourceError('TLS failed')))
    with pytest.raises(s.UpstreamSourceError,match='TLS failed'):
        w.install_selected(project,['gmsh','sqdmetal'],lambda *_:None,base=base,
                run=lambda *_a,**_k:pytest.fail('no pip before official source validation'))


def test_local_option_never_uses_network(tmp_path, monkeypatch):
    project,base,_=fake_venv(tmp_path)
    folder=tmp_path/'local-source'
    (folder/'SQDMetal'/'PALACE').mkdir(parents=True)
    (folder/'SQDMetal'/'PALACE'/'Eigenmode_Simulation.py').write_text('fixture')
    (folder/'pyproject.toml').write_text('[project]\nname="SQDMetal"')
    monkeypatch.setattr(w,'acquire_source',lambda *_a,**_k:pytest.fail('network in offline mode'))
    result=w.install_selected(project,['sqdmetal'],lambda *_:None,base=base,
          sqdmetal_source=folder,run=lambda *_a,**_k:SimpleNamespace(returncode=0,stdout='',stderr=''))
    assert result['groups']['sqdmetal']['status']=='INSTALLED_UNQUALIFIED'
    assert 'local source' in result['groups']['sqdmetal']['message']


def test_corrupt_pin_refuses_implicit_update(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path/'pin.json').write_text('{"not":"valid"}',encoding='utf-8')
    with pytest.raises(s.UpstreamSourceError, match='pin is invalid'):
        s.acquire_source(tmp_path,lambda *_:None,opener=lambda *_a,**_k:pytest.fail('unexpected network'))
