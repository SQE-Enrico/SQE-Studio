"""Shared HTTP limits and errors; no request dispatch or science."""
import re
from pathlib import Path
from ..web_assets import ASSETS

STATIC=Path(__file__).resolve().parents[1]/'web'
COOKIE_CLEAR='sqe_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
MAX_JSON=256*1024
MAX_RESULT_JSON=8*1024*1024
HEX_ID=re.compile(r'[0-9a-f]{32}\Z')

class ApiError(Exception):
    def __init__(self,message,status=400):
        self.message,self.status=message,status
