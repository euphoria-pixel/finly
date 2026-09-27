
import argparse
import os
import re
import pymupdf as fitz

from dotenv import load_dotenv
from openai import OpenAI
from llm_pipeline import BASE_URL, analyze_statement, write_atomic
from natasha import (
    Segmenter,
    NewsEmbedding,
    NewsNERTagger,
    Doc,
)

load_dotenv()

# Локальная модель для распознавания ФИО.
# При первом запуске зависимости и модели должны
# быть заранее установлены на доверенной машине.
segmenter = Segmenter()
emb = NewsEmbedding()
ner_tagger = NewsNERTagger(emb)


# Отдельный поиск нужен, когда NER распознаёт только часть ФИО.
# Границы слова защищают от совпадений внутри названий и идентификаторов.
PATRONYMIC_RE = re.compile(
    r"(?<![\w-])[а-яё]+(?:"
    r"(?:ович|евич|ьич)(?:а|у|ем|е)?"
    r"|(?:овн|евн|ичн|ьиничн)(?:а|ы|е|у|ой|ою)"
    r")(?![\w-])",
    re.IGNORECASE,
)
INITIALS_RE = re.compile(
    r"\b[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
    r"[А-ЯЁ]\.\s*[А-ЯЁ]\."
)


def remove_personal_data(text):
    """
    Локальная очистка извлечённого текста PDF.

    Удаляет:
    - ФИО физических лиц;
    - адрес владельца;
    - телефоны;
    - номера банковских счетов;
    - номера карт;
    - номера договоров.

    Не передаёт данные внешним сервисам.
    """

    # 1. Удаляем строки с персональными
    # сведениями из шапки выписки.

    private_labels = (
        "адрес места жительства",
        "адрес регистрации",
        "владелец счёта",
        "владелец счета",
        "номер лицевого счета",
        "номер лицевого счёта",
        "номер договора",
        "дата заключения договора",
    )

    lines = text.splitlines()
    cleaned_lines = []
    skip_next = False

    for line in lines:
        if skip_next:
            skip_next = False
            continue

        stripped = line.strip()
        lower = stripped.lower()

        if any(label in lower for label in private_labels):
            # Если значение находится на следующей
            # строке, удаляем и её.
            if ":" not in stripped and len(stripped) < 45:
                skip_next = True
            continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 2. Удаляем номера счетов (20 цифр).
    text = re.sub(
        r"(?<!\d)(?:\d[\s-]?){19}\d(?!\d)",
        "[СЧЁТ УДАЛЁН]",
        text
    )

    # 3. Удаляем телефоны РФ.
    text = re.sub(
        r"(?<!\d)(?:\+7|8)[\s()\-]*"
        r"\d{3}[\s()\-]*\d{3}[\s()\-]*"
        r"\d{2}[\s()\-]*\d{2}(?!\d)",
        "[ТЕЛЕФОН УДАЛЁН]",
        text
    )

    # 4. Удаляем полные номера карт.
    text = re.sub(
        r"(?<!\d)(?:\d[\s-]?){15,18}\d(?!\d)",
        "[КАРТА УДАЛЕНА]",
        text
    )

    # 5. Удаляем электронную почту.
    text = re.sub(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "[EMAIL УДАЛЁН]",
        text
    )

    # 6. Удаляем маскированные номера карт.
    text = re.sub(
        r"(?<!\w)\d{4}[\s*+Xx•-]{4,}\d{4}(?!\w)",
        "[КАРТА УДАЛЕНА]",
        text
    )

    # 7. Локальное распознавание ФИО.
    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_ner(ner_tagger)

    spans = [
        (span.start, span.stop)
        for span in doc.spans
        if span.type == "PER"
    ]

    # Независимые правила дополняют NER, а не зависят от того,
    # распознала ли модель имя перед отчеством.
    spans.extend(match.span() for match in PATRONYMIC_RE.finditer(text))
    spans.extend(match.span() for match in INITIALS_RE.finditer(text))

    # Объединяем пересечения и соседние части ФИО, в том числе
    # разделённые переносом строки при извлечении из PDF.
    merged = []
    for start, stop in sorted(spans):
        if merged and (
            start <= merged[-1][1]
            or text[merged[-1][1]:start].isspace()
        ):
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))

    for start, stop in reversed(merged):
        text = text[:start] + "[ФИО УДАЛЕНО]" + text[stop:]

    return text


def extract_and_clean_pdf(path):
    """
    Извлекает текст локально.
    Возвращает только очищенную строку.
    """

    pages = []

    with fitz.open(path) as pdf:
        for page in pdf:
            text = page.get_text("text")

            if not text.strip():
                raise ValueError(
                    "Обнаружена страница без текстового слоя. "
                    "Требуется локальный OCR."
                )

            pages.append(text)

    raw_text = "\n".join(pages)

    cleaned_text = remove_personal_data(raw_text)

    # Проверяем, не остались ли распространённые
    # форматы телефонов и номеров счетов.
    suspicious_patterns = [
        r"(?<!\d)(?:\+7|8)[\s()\-]*"
        r"\d{3}[\s()\-]*\d{3}[\s()\-]*"
        r"\d{2}[\s()\-]*\d{2}(?!\d)",
        r"(?<!\d)\d{20}(?!\d)",
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, cleaned_text):
            raise ValueError(
                "Проверка безопасности не пройдена. "
                "Отправка LLM заблокирована."
            )

    return cleaned_text


# -------------------------------
# ОСНОВНАЯ ПРОГРАММА
# -------------------------------

def main():
    parser = argparse.ArgumentParser(description="Анализ банковской PDF-выписки")
    parser.add_argument("pdf", nargs="?", default="spravka_sber.pdf")
    parser.add_argument("--no-cache", action="store_true", help="Не читать и не писать кэш LLM")
    args = parser.parse_args()
    print("Извлекаю и очищаю PDF локально...")

    text = extract_and_clean_pdf(args.pdf)

    if not text.strip():
        raise ValueError("После очистки не осталось данных.")

    # Сохраняем промежуточный результат
    # для проверки перед отправкой.
    with open(
        "res_clean.txt",
        "w",
        encoding="utf-8"
    ) as f:
        f.write(text)

    print("Предварительная очистка завершена.")
    print("Проверьте res_clean.txt.")

    # ВАЖНО:
    # Автоматическая очистка не гарантирует,
    # что все персональные данные удалены.
    # Для реальных выписок требуется проверка
    # результата перед внешней передачей.

    approval = input(
        "Подтвердите, что файл не содержит "
        "персональных данных (YES): "
    )

    if approval != "YES":
        raise SystemExit("Отправка отменена.")

    client = OpenAI(
        api_key=os.getenv("API_KEY"),
        base_url=BASE_URL
    )

    print("Анализирую очищенные данные...")
    with client:
        csv_text, stats = analyze_statement(
            client, text, cache_dir=None if args.no_cache else ".llm_cache"
        )

    # Записываем только полностью полученный и проверенный ответ.
    write_atomic("result.csv", "\ufeff" + csv_text)
    if stats["cache_hit"]:
        print("Результат из локального кэша: 0 токенов, без запроса к LLM.")
    else:
        print(
            f"Объём текста: {stats['input_chars']} → {stats['packed_chars']} символов. "
            f"Время LLM: {stats['elapsed_seconds']:.1f} с."
        )
        if stats["prompt_tokens"] is not None:
            print(
                f"Токены API: вход {stats['prompt_tokens']}, "
                f"выход {stats['completion_tokens']}."
            )
        if stats.get("cache_write_failed"):
            print("Ответ сохранён в CSV, но записать кэш не удалось.")

    print("Готово: result.csv")


if __name__ == "__main__":
    main()
