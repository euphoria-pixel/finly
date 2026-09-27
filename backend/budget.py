"""Детерминированные расчёты: все суммы в минимальных единицах валюты."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def day(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).date()


def calculate(transactions, accounts, settings, recurring, *, today=None, period_days=30):
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=period_days - 1)
    previous_start = start - timedelta(days=period_days)
    posted = [t for t in transactions if t['status'] == 'posted' and day(t['occurred_at']) <= today]
    selected = [t for t in posted if day(t['occurred_at']) >= start]
    totals = defaultdict(lambda: {'income_minor': 0, 'expense_minor': 0})
    categories = defaultdict(int)
    daily = { (start + timedelta(days=i)).isoformat(): 0 for i in range(period_days)}
    monthly = defaultdict(lambda: {'income_minor': 0, 'expense_minor': 0})
    def expense(t):
        # Возврат: положительная сумма с direction=expense уменьшает расходы.
        return -t['amount_minor'] if t['direction'] == 'expense' else 0
    for t in selected:
        if t['direction'] == 'income':
            totals[t['currency']]['income_minor'] += t['amount_minor']
        totals[t['currency']]['expense_minor'] += expense(t)
        if t['currency'] == 'RUB':
            categories[t.get('user_category') or t.get('bank_category') or 'Другое'] += expense(t)
            daily[day(t['occurred_at']).isoformat()] += expense(t)
    rub = [t for t in posted if t['currency'] == 'RUB']
    for t in rub:
        month = day(t['occurred_at']).strftime('%Y-%m')
        monthly[month]['expense_minor'] += expense(t)
        if t['direction'] == 'income':
            monthly[month]['income_minor'] += t['amount_minor']
    previous = sum(expense(t) for t in rub if previous_start <= day(t['occurred_at']) < start)
    this_expense = totals['RUB']['expense_minor']
    week_expense = sum(expense(t) for t in rub if day(t['occurred_at']) >= today - timedelta(days=6))
    today_expense = sum(expense(t) for t in rub if day(t['occurred_at']) == today)
    month_expense = sum(expense(t) for t in rub if day(t['occurred_at']).replace(day=1) == today.replace(day=1))
    balance = settings.get('starting_balance_minor')
    balance_source = 'Введённый остаток и известные операции'
    if balance is not None:
        asof = settings.get('balance_at') or today.isoformat()
        balance += sum(t['amount_minor'] for t in rub if t['occurred_at'] > asof)
    else:
        rub_accounts = [a for a in accounts if a['currency'] == 'RUB']
        if rub_accounts and all(a['balance_minor'] is not None and a['balance_at'] for a in rub_accounts):
            balance = sum(a['balance_minor'] + sum(t['amount_minor'] for t in rub
                if t['account_id'] == a['id'] and t['occurred_at'] > a['balance_at']) for a in rub_accounts)
        balance_source = 'Остатки выбранных счетов и проведённые операции' if balance is not None else 'Баланс неизвестен'
    next_date = datetime.fromisoformat(settings['next_income_date']).date()
    days = max(0, (next_date - today).days)
    due = [r for r in recurring if not r['paid'] and datetime.fromisoformat(r['due_date']).date() <= next_date]
    obligations = sum(r['amount_minor'] for r in due)
    pending = sum(max(0, -t['amount_minor']) for t in transactions
                  if t['status'] == 'pending' and t['currency'] == 'RUB')
    available = None if balance is None else balance - obligations - settings['reserve_minor'] - pending
    safe_daily = None if available is None else max(0, available // max(1, days))
    if safe_daily is not None and settings.get('daily_limit_minor') is not None:
        safe_daily = min(safe_daily, settings['daily_limit_minor'])
    elif safe_daily is None:
        safe_daily = settings.get('daily_limit_minor')
    # Не выдаём прогноз при отсутствии истории; дни без покупок входят в темп.
    history_days = min(30, (today - min(day(t['occurred_at']) for t in rub)).days + 1) if rub else 0
    past30 = [t for t in rub if day(t['occurred_at']) >= today - timedelta(days=29)]
    # Подписки, явно помеченные как регулярные, учитываются будущими платежами.
    variable_expense = sum(expense(t) for t in past30 if not t.get('raw_payload', {}).get('recurring'))
    pace = max(0, variable_expense // max(1, history_days)) if history_days else None
    forecast = None if balance is None or pace is None or not days else balance - obligations - pending - pace * days
    return {
        'period_days': period_days, 'totals_by_currency': dict(totals),
        'income_minor': totals['RUB']['income_minor'], 'expense_minor': this_expense,
        'today_expense_minor': today_expense, 'week_expense_minor': week_expense,
        'month_expense_minor': month_expense, 'previous_expense_minor': previous,
        'change_minor': this_expense - previous,
        'balance_minor': balance, 'balance_source': balance_source,
        'available_minor': available, 'deficit_minor': max(0, -(available or 0)),
        'days_remaining': days, 'daily_limit_minor': safe_daily,
        'forecast_minor': forecast, 'pace_minor': pace, 'history_days': history_days,
        'obligations_minor': obligations, 'pending_minor': pending,
        'reserve_minor': settings['reserve_minor'], 'next_income_date': next_date.isoformat(),
        'expected_income_minor': settings['expected_income_minor'],
        'monthly_limit_minor': settings['monthly_limit_minor'],
        'goal_progress_percent': min(100, settings['goal_saved_minor'] * 100 // settings['goal_minor']),
        'categories': [{'name': k, 'amount_minor': v} for k,v in sorted(categories.items(), key=lambda x: -x[1]) if v],
        'daily': [{'date': k, 'amount_minor': v} for k,v in daily.items()],
        'monthly': [{'month': k, **v} for k,v in sorted(monthly.items())][-6:],
        'recurring': due,
        'largest': sorted([t for t in selected if t['direction']=='expense' and t['amount_minor']<0 and t['currency']=='RUB'], key=lambda t:t['amount_minor'])[:5],
        'assumptions': [
            'Расчёт в RUB. Другие валюты показаны отдельно, без конвертации.',
            'Прогноз до поступления: ожидаемый доход ещё не включён в остаток.',
            'Темп — средние чистые расходы за доступную историю, не более 30 дней.',
            'Переводы исключены из доходов и расходов; холды уменьшают доступный бюджет.',
            'Обязательные платежи задаются вручную; помечайте оплаченные, чтобы избежать двойного учёта.',
            'Прогноз является оценкой; неполная история снижает его точность.',
        ],
    }
