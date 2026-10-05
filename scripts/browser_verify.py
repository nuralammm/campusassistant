"""Run real browser tests against an isolated synthetic SQLite DB."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import httpx
root=Path(__file__).resolve().parents[1]
python=str(root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))
with tempfile.TemporaryDirectory(prefix='campus-browser-') as temp:
    env=dict(os.environ,DATABASE_URL='sqlite:///'+str(Path(temp)/'browser.db'),DEMO_PASSWORD='browser-synthetic-2026',PORTAL_DEMO_PASSWORD='browser-synthetic-2026',AI_PROVIDER='disabled',PYTHONPATH=str(root/'src'))
    for command in [[python,'-m','alembic','upgrade','head'],[python,'-m','campus_assistant.api.seed'],[python,'-m','campus_assistant.api.seed_portals']]:
        subprocess.run(command,cwd=root,env=env,check=True)
    processes=[subprocess.Popen([python,'-m','uvicorn','campus_assistant.api.main:app','--port','8000'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL),subprocess.Popen(['node','build'],cwd=root/'frontend',env=dict(env,HOST='127.0.0.1',PORT='5173',ORIGIN='http://127.0.0.1:5173'),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)]
    try:
        for url in ['http://127.0.0.1:8000/health','http://127.0.0.1:5173/']:
            for _ in range(60):
                try:
                    if httpx.get(url,trust_env=False).status_code==200:break
                except httpx.ConnectError:pass
                time.sleep(.1)
            else:raise RuntimeError('Service failed to start')
        npm='npx.cmd' if os.name=='nt' else 'npx'
        subprocess.run([npm,'playwright','test','--workers=1'],cwd=root/'frontend',env=env,check=True)
    finally:
        for p in processes:p.terminate();p.wait(timeout=5)
