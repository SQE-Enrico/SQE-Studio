"""Session; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from .common import COOKIE_CLEAR

def me(self,request):
    user=request.user
    return self.send_json({'authenticated':True,'csrf':user['csrf']})


def logout(self,request):
    self.app.store.logout(self.token())
    return self.send_json({'ok':True},200,{'Set-Cookie':COOKIE_CLEAR})


def password(self,request):
    uid=request.uid
    obj=self.json_body()
    if set(obj)!={'current_password','new_password'}:
        raise ApiError('Password change requires current_password and new_password',422)
    if not self.app.store.change_password(uid,obj['current_password'],obj['new_password']):
        raise ApiError('Current password is invalid',401)
    return self.send_json({'ok':True,'reauthentication_required':True},200,{'Set-Cookie':COOKIE_CLEAR})

