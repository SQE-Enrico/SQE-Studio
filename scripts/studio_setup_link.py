"""Administrator-only helper: print the one-use setup URL from the server/container."""
from sqw.studio.auth import Auth
from sqw.studio.db import Store
from sqw.studio.settings import Settings

settings=Settings.from_env()
token=Auth(Store(settings)).setup_token()
print(settings.origin+'/#setup='+token if token else 'Initial administrator setup is already complete.')
