# Миграции приложения

Команда: `.venv/bin/python -m scripts.migrate` (также выполняется при startup).

* v1: исходные таблицы accounts, transactions, data_sources, sync_states,
  import_jobs, budget_settings, recurring_payments, notifications, events.
* v2: nullable `transactions.mcc`, таблица `feature_flags` с demo_pro=false;
  существующие записи и внешние ID сохраняются. Для обратной совместимости
  физическая колонка `external_id` остаётся; ORM-синоним и публичное API-поле
  `source_transaction_id` дают требуемое имя без пересоздания истории.
* История применений — schema_migrations. Миграция повторяемая и добавочная.
* Исходный банковский JSON хранится в transactions.raw_payload и
  sync_states.raw_response, отдельно от нормализованных столбцов; наружу не выдаётся.
* Уникальность: user_id + source_type + account_id + external_id. Исходная
  пользовательская категория не перезаписывается повторной синхронизацией.

Это локальная SQLite-схема. Автоматических destructive down-миграций нет.
База PostgreSQL учебного банка независима; seed применяется один раз для клиента.
