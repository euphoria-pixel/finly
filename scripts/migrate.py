"""Идемпотентная начальная миграция схемы v2."""
from backend.db import migrate
migrate()
print('Schema v2 ready')
