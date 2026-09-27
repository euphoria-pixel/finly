"""LLM selects explanations; every displayed fact and amount is rendered locally."""
import json
import os

def rub(value):
    if value is None:return 'неизвестно'
    sign='−' if value<0 else ''
    whole,fraction=divmod(abs(value),100)
    return sign+f'{whole:,}'.replace(',',' ')+f',{fraction:02d} ₽'

def explanations(d):
    return {
        'budget':f"До следующего поступления {d['days_remaining']} дн. Доступно: {rub(d['available_minor'])}. Дневной лимит: {rub(d['daily_limit_minor'])}.",
        'forecast':f"Прогноз остатка перед поступлением: {rub(d['forecast_minor'])}. "+('При текущем темпе денег может не хватить.' if d['forecast_minor'] is not None and d['forecast_minor']<0 else 'Это оценка по известной истории, не гарантия.'),
        'categories':'Расходы за выбранный период: '+rub(d['expense_minor'])+'. '+('; '.join(x['name']+': '+rub(x['amount_minor']) for x in d['categories'][:3]) or 'Операций пока нет.'),
        'change':'Изменение расходов относительно предыдущего периода: '+rub(d['change_minor'])+'. После покупки уменьшаются доступные средства и их доля на каждый оставшийся день.',
        'payments':'Ожидаемые обязательные платежи: '+rub(d['obligations_minor'])+'. '+('; '.join(r['name']+': '+rub(r['amount_minor']) for r in d['recurring']) or 'Не заданы.'),
        'unknown':'Баланс неизвестен. Укажите остаток или подключите учебный банк.' if d['balance_minor'] is None else 'Известный остаток: '+rub(d['balance_minor'])+'. Резерв: '+rub(d['reserve_minor'])+'.',
    }

def select_explanations(question, facts):
    from openai import OpenAI
    from llm_pipeline import BASE_URL,MODEL
    with OpenAI(api_key=os.getenv('API_KEY'),base_url=os.getenv('LLM_BASE_URL',BASE_URL),timeout=20,max_retries=0) as client:
        response=client.chat.completions.create(model=os.getenv('LLM_MODEL',MODEL),messages=[
            {'role':'system','content':'Выбери 1–4 подходящих раздела для вопроса о бюджете. Верни только JSON {"sections":[...]}. Допустимые ключи: budget,forecast,categories,change,payments,unknown. Не вычисляй суммы и не генерируй финансовые факты.'},
            {'role':'user','content':json.dumps({'question':question,'facts':facts},ensure_ascii=False)}])
    content=(response.choices[0].message.content or '').strip()
    if content.startswith('```') and content.endswith('```'):
        content=content.split('\n',1)[1].rsplit('```',1)[0].strip()
    result=json.loads(content)
    keys=result['sections']
    if not isinstance(keys,list) or not 1<=len(keys)<=4 or any(k not in ('budget','forecast','categories','change','payments','unknown') for k in keys):raise ValueError('Invalid explanation selection')
    return list(dict.fromkeys(keys))
