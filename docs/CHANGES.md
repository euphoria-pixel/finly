# Изменённые и добавленные файлы

## Backend

* `backend/app.py` — T-API-маршруты удалены; банковский sync/polling,
  server-side Pro, demo reset/replay, история событий, обновлённый assistant.
* `backend/bank_in_a_box.py` — новый адаптер реальных локальных HTTP-запросов.
* `backend/assistant.py` — проверенные объяснения и LLM-выбор разделов.
* `backend/db.py` — MCC, ORM-синоним source_transaction_id, feature_flags, миграция v2.
* `backend/schemas.py` — новый источник, scopes, MCC.
* `backend/services.py` — инициализация банка/тарифа, разделение источников,
  freshness/plan в dashboard, пересчёты/уведомления для банковской истории.
* `backend/connectors.py` — сохранён импорт, удалён старый T-API-коннектор.
* `backend/simulator.py` — DemoTransactionConnector, дополнительные категории,
  идемпотентное воспроизведение.

`main.py`, `llm_pipeline.py`, `charts.py` и `backend/budget.py` переиспользованы
без переписывания.

## Frontend

* `frontend/components/finance-app.tsx` — банк/счета/балансы, тарифы, freshness,
  источники аналитики, сценарий и восстановление, история событий, точный парсинг ввода.
* `frontend/lib/realtime.mjs` — общий обработчик SSE с refetch при переподключении.
* `frontend/app/globals.css` — новые элементы, контраст вторичного текста, клавиатурный фокус.
* `frontend/package-lock.json` — воспроизводимая установка npm.
* `frontend/tsconfig.json`, `frontend/next-env.d.ts` — актуализированы Next.js.
* `frontend/AGENTS.md`, `frontend/CLAUDE.md` — автоматически созданы Next.js dev.

## Инфраструктура, проверки, документация

* `compose.yaml`, `infra/bank/Dockerfile`, `infra/bank/launch.py`,
  `infra/bank/UPSTREAM_REVISION`, `infra/bank/upstream/` — локальный банк,
  неизменённые upstream-исходники и bootstrap временной совместимой копии.
* `scripts/setup_bank_env.py`, `scripts/smoke.py` — локальная конфигурация и live smoke.
* `scripts/dev.py`, `scripts/migrate.py` — запуск с reload, миграция v2.
* `tests/test_backend.py`, `tests/test_bank.py`, `frontend/tests/realtime.test.mjs`.
* `.env.example`, `README.md`, `README_DEMO.md`, `docs/AUDIT.md`,
  `docs/BANK_IN_A_BOX.md`, `docs/MIGRATIONS.md`, `docs/VERIFICATION.md`, `docs/CHANGES.md`.
* В локальный `.env` добавлены параметры стенда без перезаписи прежнего LLM-ключа.
  Секреты не включены в документацию. База проверки — `data/hackathon`.

Git-метаданные в этой рабочей директории недоступны (`git status`: not a git repository),
поэтому commit/diff не создавались; изменения записаны непосредственно в рабочие файлы.
