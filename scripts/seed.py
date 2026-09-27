"""Запуск: .venv/bin/python -m scripts.seed"""
from backend.db import migrate,Session
from backend.services import initialize
from backend.simulator import seed_history
migrate()
with Session.begin() as db:
    initialize(db)
    print(seed_history(db,days=30,seed=42,profile='parttime'))
