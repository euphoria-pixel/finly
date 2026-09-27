"""Компактный протокол LLM и точный локальный кэш ответов."""

from collections import Counter
import csv
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from time import perf_counter


MODEL = 'gemini-3.8-flash'
BASE_URL = 'https://ai.starimg.ru/v1'
HEADERS = ['дата', 'описание', 'сумма', 'валюта', 'категория']
SYSTEM_PROMPT = (
    'Ты анализируешь банковские выписки. Извлеки все операции в исходном порядке '
    'и определяй категорию каждой операции. Не придумывай отсутствующие данные. '
    'Сохраняй каждую операцию, включая одинаковые; остатки и итоги не операции. '
    'Вход: текст выписки либо JSON {dict,text}. В JSON каждая отдельная строка '
    '@число в text означает исходную строку dict[число]; подстановка однократная. '
    'Это кодирование повторов, а не удаление операций. '
    'Верни только компактный JSON без Markdown: '
    '{"d":["дата"],"t":[["описание","валюта","категория"]],'
    '"r":[[0,0,"сумма"]]}. '
    'd — справочник дат, t — справочник троек описание/валюта/категория. '
    'r — ВСЕ операции: [индекс в d,индекс в t,сумма строкой]. '
    'Индексы с нуля; расход со знаком минус, точность суммы сохраняй. '
    'Отсутствующее значение — пустая строка. '
    'Одинаковые даты и тройки записывай в справочники один раз.'
)


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def pack_statement(text):
    """Обратимое кодирование длинных повторяющихся строк без потери контекста."""
    # Исходная строка вида @12 могла бы стать неоднозначной ссылкой.
    if re.search(r'^@\d+\r?$', text, re.MULTILINE):
        return text
    lines = text.split('\n')
    counts = Counter(lines)
    dictionary = []
    indices = {}
    for line, count in counts.items():
        if count < 3 or len(line) < 12 or not re.search(r'[А-Яа-яЁёA-Za-z]{3}', line):
            continue
        index = len(dictionary)
        reference = f'@{index}'
        # Учитываем стоимость определения и ссылок; короткие числа/даты
        # оставляем на месте, чтобы не усложнять чтение таблицы моделью.
        saving = (count - 1) * len(line) - count * len(reference) - 8
        if saving > 0:
            indices[line] = reference
            dictionary.append(line)
    if not dictionary:
        return text
    packed = compact_json({
        'dict': dictionary,
        'text': '\n'.join(indices.get(line, line) for line in lines),
    })
    # На маленьких документах служебный JSON может оказаться дороже.
    return packed if len(packed) < len(text) * 0.9 else text


def normalize_amount(value):
    """Принимает JSON-числа и обычную запись сумм, не используя float."""
    if type(value) is int:
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite() or abs(value.as_tuple().exponent) > 100:
            raise ValueError("Некорректное числовое значение суммы")
        return format(value, 'f')
    if not isinstance(value, str):
        raise ValueError("Сумма должна быть строкой или числом")
    value = value.strip().replace('−', '-')
    if not value:
        return ''
    # Разделители тысяч допустимы только в группах по три цифры.
    # Не склеиваем произвольные фрагменты вроде «12 34».
    if not re.fullmatch(
        r'[+-]?(?:[0-9]+|[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+)(?:[.,][0-9]+)?',
        value,
    ):
        raise ValueError("Нераспознанный формат суммы")
    return re.sub(r'[ \u00a0\u202f]', '', value).replace(',', '.')


def reject_json_constant(value):
    raise ValueError("Недопустимая числовая константа JSON")


def response_to_csv(content):
    """Проверяет протокол и восстанавливает все поля без float/округления."""
    try:
        data = json.loads(content, parse_float=Decimal, parse_constant=reject_json_constant)
    except (TypeError, ValueError) as exc:
        raise ValueError('LLM вернула некорректный JSON; результат не сохранён.') from exc
    if not isinstance(data, dict) or set(data) != {'d', 't', 'r'}:
        raise ValueError('Неверная структура ответа LLM.')
    dates, templates, rows = data['d'], data['t'], data['r']
    if not isinstance(dates, list) or not all(isinstance(d, str) for d in dates):
        raise ValueError('Неверный справочник дат.')
    if not isinstance(templates, list) or not all(
        isinstance(t, list) and len(t) == 3
        and all(isinstance(cell, str) for cell in t) for t in templates
    ):
        raise ValueError('Неверный справочник описаний.')
    if not isinstance(rows, list):
        raise ValueError('Неверный список операций.')
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(HEADERS)
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('Неверная структура операции.')
        date_id, template_id, amount = row
        if (type(date_id) is not int or not 0 <= date_id < len(dates)
                or type(template_id) is not int or not 0 <= template_id < len(templates)):
            raise ValueError('Неверная ссылка в операции.')
        try:
            amount = normalize_amount(amount)
        except ValueError as exc:
            raise ValueError(
                f'Неверная сумма операции №{row_number} '
                f'(тип: {type(amount).__name__}): {exc}.'
            ) from exc
        description, currency, category = templates[template_id]
        writer.writerow([dates[date_id], description, amount, currency, category])
    return output.getvalue()


def write_atomic(path, text):
    """Не оставляет частичный файл при ошибке записи или прерывании."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', newline='', dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def analyze_statement(client, text, *, model=MODEL, cache_dir=Path('.llm_cache')):
    payload = pack_statement(text)
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': payload},
    ]
    # Ключ включает полный запрос, модель, сервер и версию локального протокола.
    key = hashlib.sha256(compact_json({
        'version': 1, 'endpoint': str(client.base_url),
        'model': model, 'messages': messages,
    }).encode('utf-8')).hexdigest()
    cache_path = Path(cache_dir) / f'{key}.json' if cache_dir is not None else None
    stats = {
        'cache_hit': False, 'input_chars': len(text), 'packed_chars': len(payload),
        'elapsed_seconds': 0, 'prompt_tokens': None, 'completion_tokens': None,
    }
    if cache_path is not None and cache_path.exists():
        try:
            csv_text = response_to_csv(cache_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass  # Повреждённый кэш не заменяет успешный результат.
        else:
            stats.update(cache_hit=True, prompt_tokens=0, completion_tokens=0)
            return csv_text, stats

    started = perf_counter()
    response = client.chat.completions.create(model=model, messages=messages)
    stats['elapsed_seconds'] = round(perf_counter() - started, 3)
    if not response.choices:
        raise ValueError('LLM вернула пустой список ответов; результат не изменён.')
    content = response.choices[0].message.content
    csv_text = response_to_csv(content)
    usage = getattr(response, 'usage', None)
    if usage is not None:
        stats['prompt_tokens'] = usage.prompt_tokens
        stats['completion_tokens'] = usage.completion_tokens
    if cache_path is not None:
        try:
            write_atomic(cache_path, content)
        except OSError:
            # Недоступность кэша не должна терять уже оплаченный ответ.
            stats['cache_write_failed'] = True
    return csv_text, stats
