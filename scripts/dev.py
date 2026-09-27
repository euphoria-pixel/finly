"""Единый локальный запуск: .venv/bin/python scripts/dev.py"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent.parent
children=[]
try:
    subprocess.run([sys.executable,'-m','scripts.seed'],cwd=ROOT,check=True)
    children.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8000','--reload','--reload-dir','backend'],cwd=ROOT))
    children.append(subprocess.Popen(['npm','run','dev'],cwd=ROOT/'frontend'))
    print('\nСтипендия: http://127.0.0.1:3000\nAPI: http://127.0.0.1:8000/docs\nCtrl+C — остановить\n',flush=True)
    while all(p.poll() is None for p in children):time.sleep(.5)
finally:
    for p in children:
        if p.poll() is None:p.send_signal(signal.SIGINT)
    for p in children:
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill()
