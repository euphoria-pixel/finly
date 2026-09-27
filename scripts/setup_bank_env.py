"""Add local-only bank settings without overwriting existing application secrets."""
from pathlib import Path
import secrets
path=Path(__file__).resolve().parent.parent/'.env'
current=path.read_text() if path.exists() else ''
values={'BIAB_DB_PASSWORD':secrets.token_hex(24),'BIAB_SECRET_KEY':secrets.token_hex(32),'BIAB_USERNAME':'demo-student','BIAB_PASSWORD':'password','BIAB_BASE_URL':'http://127.0.0.1:8080'}
with path.open('a') as f:
    for key,value in values.items():
        if not any(line.startswith(key+'=') for line in current.splitlines()):f.write('\n'+key+'='+value+'\n')
path.chmod(0o600)
print('Local bank environment ready; existing keys preserved.')
