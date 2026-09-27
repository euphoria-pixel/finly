import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, Integer, Boolean, JSON, Text, UniqueConstraint, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, synonym

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('APP_DATA_DIR', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
USER = 'local-demo'

def now():
    return datetime.now(timezone.utc).isoformat()

def uid():
    return str(uuid4())

class Base(DeclarativeBase):
    pass

class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(default=USER)
    source_type: Mapped[str]
    name: Mapped[str]
    currency: Mapped[str] = mapped_column(default='RUB')
    balance_minor: Mapped[int | None]
    balance_at: Mapped[str | None]
    is_demo: Mapped[bool] = mapped_column(default=True)

class Transaction(Base):
    __tablename__ = 'transactions'
    __table_args__ = (UniqueConstraint('user_id', 'source_type', 'account_id', 'external_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    external_id: Mapped[str]
    source_transaction_id = synonym("external_id")
    user_id: Mapped[str] = mapped_column(default=USER)
    account_id: Mapped[str]
    source_type: Mapped[str]
    source_name: Mapped[str]
    occurred_at: Mapped[str]
    posted_at: Mapped[str | None]
    amount_minor: Mapped[int]
    currency: Mapped[str]
    direction: Mapped[str]
    description: Mapped[str] = mapped_column(Text)
    mcc: Mapped[str | None]
    merchant_name: Mapped[str | None]
    bank_category: Mapped[str | None]
    user_category: Mapped[str | None]
    status: Mapped[str]
    is_demo: Mapped[bool]
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)

class FeatureFlags(Base):
    __tablename__ = 'feature_flags'
    user_id: Mapped[str] = mapped_column(String, primary_key=True, default=USER)
    demo_pro: Mapped[bool] = mapped_column(default=False)

class DataSource(Base):
    __tablename__ = 'data_sources'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(default=USER)
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default='idle')
    config: Mapped[dict] = mapped_column(JSON, default=dict)

class SyncState(Base):
    __tablename__ = 'sync_states'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(default=USER)
    last_success: Mapped[str | None]
    error: Mapped[str | None]
    cursor: Mapped[str | None]
    raw_response: Mapped[dict] = mapped_column(JSON, default=dict)

class ImportJob(Base):
    __tablename__ = 'import_jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(default=USER)
    filename: Mapped[str]
    path: Mapped[str]
    status: Mapped[str] = mapped_column(default='uploaded')
    cleaned_text: Mapped[str | None] = mapped_column(Text)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None]
    is_demo: Mapped[bool] = mapped_column(default=True)
    account_id: Mapped[str] = mapped_column(default='manual-demo')
    created_at: Mapped[str] = mapped_column(default=now)

class BudgetSettings(Base):
    __tablename__ = 'budget_settings'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(default=USER)
    data: Mapped[dict] = mapped_column(JSON)

class RecurringPayment(Base):
    __tablename__ = 'recurring_payments'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(default=USER)
    scope: Mapped[str]
    name: Mapped[str]
    amount_minor: Mapped[int]
    due_date: Mapped[str]
    paid: Mapped[bool] = mapped_column(default=False)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(default=USER)
    dedupe_key: Mapped[str] = mapped_column(unique=True)
    scope: Mapped[str]
    kind: Mapped[str]
    title: Mapped[str]
    message: Mapped[str]
    is_demo: Mapped[bool] = mapped_column(default=True)
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=now)

class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(default=USER)
    type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)

class Migration(Base):
    __tablename__ = 'schema_migrations'
    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[str] = mapped_column(default=now)

engine = create_engine(os.getenv('DATABASE_URL', f'sqlite:///{DATA / "finance.db"}'),
                       connect_args={'check_same_thread': False} if os.getenv('DATABASE_URL', 'sqlite').startswith('sqlite') else {})
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def sqlite_setup(connection, _):
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA busy_timeout=10000')
Session = sessionmaker(engine, expire_on_commit=False)

def migrate():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        columns={c['name'] for c in inspect(conn).get_columns('transactions')}
        if 'mcc' not in columns:conn.execute(text('ALTER TABLE transactions ADD COLUMN mcc VARCHAR'))
    with Session.begin() as db:
        if not db.get(Migration, 2):db.add(Migration(version=2))
        if not db.get(Migration, 1):
            db.add(Migration(version=1))

def public(obj):
    result = {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in ('raw_payload','path','user_id','raw_response')}

    if isinstance(obj, Transaction):result['source_transaction_id']=obj.external_id
    return result
