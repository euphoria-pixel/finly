from datetime import datetime, date, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

Source = Literal['manual_import', 'tbank_sandbox', 'personal_simulator', 'bank_in_a_box']
Scope = Literal['demo', 'personal', 'sandbox', 'combined', 'bank', 'statements']
Status = Literal['pending', 'posted', 'reversed', 'unknown']
Direction = Literal['income', 'expense', 'transfer', 'unknown']
CATEGORIES = ['Продукты', 'Кафе и доставка', 'Транспорт', 'Подписки', 'Связь', 'Развлечения', 'Покупки', 'Здоровье', 'Учёба', 'Доход', 'Переводы', 'Другое']

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')

class TransactionInput(Model):
    external_id: str = Field(min_length=1, max_length=200)
    account_id: str = Field(min_length=1, max_length=120)
    source_type: Source
    source_name: str
    occurred_at: datetime
    posted_at: datetime | None = None
    amount_minor: int = Field(strict=True, ge=-10**14, le=10**14)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    direction: Direction
    description: str = Field(max_length=3000)
    mcc: str | None = Field(default=None, max_length=4)
    merchant_name: str | None = None
    bank_category: str | None = None
    user_category: str | None = None
    status: Status = 'posted'
    is_demo: bool = True
    raw_payload: dict = Field(default_factory=dict)

    @field_validator('occurred_at', 'posted_at')
    @classmethod
    def utc(cls, value):
        if value is None:
            return value
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)

class TransactionPatch(Model):
    user_category: str = Field(min_length=1, max_length=80)

class Purchase(Model):
    amount_minor: int = Field(default=45000, strict=True, gt=0, le=100000000)
    category: str = Field(default='Кафе и доставка', max_length=80)
    merchant: str = Field(default='Кофейня «Перемена»', min_length=1, max_length=120)
    account_id: Literal['sim-main', 'sim-save'] = 'sim-main'
    status: Literal['posted', 'pending'] = 'posted'
    direction: Literal['expense', 'income', 'transfer'] = 'expense'

class SeedRequest(Model):
    days: int = Field(default=30, ge=30, le=90)
    seed: int = Field(default=42, ge=0, le=1000000)
    profile: Literal['scholarship', 'parttime', 'irregular'] = 'parttime'

class StartRequest(Model):
    interval_seconds: int = Field(default=10, ge=2, le=3600)

class Settings(Model):
    reserve_minor: int = Field(default=300000, ge=0, le=10**12)
    next_income_date: date
    expected_income_minor: int = Field(default=1800000, ge=0, le=10**12)
    daily_limit_minor: int | None = Field(default=None, ge=0, le=10**12)
    monthly_limit_minor: int = Field(default=2500000, gt=0, le=10**12)
    starting_balance_minor: int | None = Field(default=None, ge=-10**12, le=10**12)
    balance_at: datetime | None = None
    notifications_enabled: bool = True
    disabled_rules: list[str] = Field(default_factory=list)
    goal_title: str = Field(default='Моя цель',min_length=1,max_length=120)
    goal_deadline: date | None = None
    goal_minor: int = Field(default=5000000, gt=0, le=10**12)
    goal_saved_minor: int = Field(default=800000, ge=0, le=10**12)
    categories: list[str] = Field(default_factory=lambda: CATEGORIES.copy(), max_length=40)

class RecurringInput(Model):
    name: str = Field(min_length=1, max_length=100)
    amount_minor: int = Field(gt=0, le=10**12)
    due_date: date
    paid: bool = False

class ConfirmRow(Model):
    date: str
    description: str = Field(max_length=3000)
    amount: str
    currency: str
    category: str = Field(default='Другое', max_length=80)
    direction: Direction | None = None
    include: bool = True

class ConfirmImport(Model):
    rows: list[ConfirmRow] = Field(max_length=5000)

class ProcessImport(Model):
    approved: bool = False

class ChatRequest(Model):
    message: str = Field(min_length=1, max_length=1000)
    scope: Scope = 'demo'
    use_llm: bool = False

class ChatResponse(Model):
    answer: str
    mode: Literal['llm', 'local']

class ActionResult(BaseModel):
    ok: bool = True
    message: str = ''
    created: int = 0
    updated: int = 0
    duplicates: int = 0

class EventPayload(BaseModel):
    id: int
    type: str
    created_at: str
    payload: dict[str, Any]

def money_minor(value, currency='RUB'):
    # Поддерживаемые валюты имеют 2 знака; для других требуется явная карта.
    precision = {'RUB': 2, 'USD': 2, 'EUR': 2, 'CNY': 2, 'GBP': 2, 'JPY': 0}
    if currency not in precision:
        raise ValueError('Неизвестная точность валюты: ' + currency)
    try:
        amount = Decimal(str(value).replace('\u00a0', '').replace('\u202f','').replace(' ', '').replace(',', '.').replace('−','-'))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Неверная сумма') from exc
    scaled = amount * (10 ** precision[currency])
    if not scaled.is_finite() or scaled != scaled.to_integral_value() or abs(scaled) > 10**14:
        raise ValueError('Некорректная точность или размер суммы')
    return int(scaled)
