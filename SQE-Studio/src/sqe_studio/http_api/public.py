"""Public; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ASSETS
from .common import ApiError
from sqe_studio import __version__
import hmac
from ..web_assets import read_asset
def assets(self,request):
    path=request.path
    target='index.html' if path=='/' else path[1:]
    return self.send_bytes(read_asset(target),200,ASSETS[target])


def status(self,request):
    return self.send_json({'version':__version__,'setup_required':not self.app.store.has_account(),
                           'local_only':True,'service':'ready'})


def setup(self,request):
    obj=self.json_body()
    key=self.app.setup_file.read_text(encoding='ascii') if self.app.setup_file.is_file() else ''
    supplied=obj.get('setup_token','')
    if not isinstance(supplied,str) or len(supplied)>128 or not key or not hmac.compare_digest(supplied,key):
        raise ApiError('Invalid first-run setup token',403)
    self.app.store.setup(obj.get('email'),obj.get('password'))
    self.app.setup_file.unlink(missing_ok=True)
    return self.send_json({'ok':True})


def login(self,request):
    obj=self.json_body()
    if not self.app.login_allowed():raise ApiError('Too many login failures; retry after five minutes',429)
    session=self.app.store.login(obj.get('email'),obj.get('password'))
    self.app.login_result(bool(session))
    if not session:raise ApiError('Invalid credentials',401)
    token,csrf=session
    return self.send_json({'ok':True,'csrf':csrf},200,{'Set-Cookie':f'sqe_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})

