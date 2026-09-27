"""Строит диаграммы расходов по категориям из result.csv.

Запуск: python charts.py
Зависимости: pip install pandas matplotlib
"""
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

INPUT = Path(__file__).with_name('result.csv')
OUTPUT = Path(__file__).parent


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f'Не найден {INPUT}. Положите result.csv рядом с charts.py')

    # sep=None распознаёт запятую или точку с запятой.
    df = pd.read_csv(INPUT, encoding='utf-8-sig', sep=None, engine='python')
    df.columns = df.columns.str.strip().str.lower()
    required = {'категория', 'сумма'}
    if not required.issubset(df.columns):
        raise ValueError(f'В CSV нужны столбцы: {", ".join(sorted(required))}. Найдены: {list(df.columns)}')

    # Поддержка чисел вида -1500,50 и -1 500.50.
    amounts = (df['сумма'].astype(str)
               .str.replace('\u00a0', '', regex=False)
               .str.replace(' ', '', regex=False)
               .str.replace(',', '.', regex=False))
    df['сумма'] = pd.to_numeric(amounts, errors='coerce')
    df['категория'] = df['категория'].fillna('Без категории').astype(str).str.strip()
    df.loc[df['категория'].eq(''), 'категория'] = 'Без категории'

    # В этой выписке отрицательные суммы — расходы.
    expenses = df.loc[df['сумма'] < 0].copy()
    if expenses.empty:
        raise ValueError('Нет отрицательных сумм (расходов). Проверьте формат CSV.')
    expenses['сумма'] = expenses['сумма'].abs()
    totals = expenses.groupby('категория')['сумма'].sum().sort_values(ascending=False)

    # Кириллица в подписях.
    plt.rcParams['font.family'] = 'DejaVu Sans'

    fig, ax = plt.subplots(figsize=(9, 7))
    ax.pie(totals.values, labels=totals.index, autopct='%1.1f%%', startangle=90)
    ax.set_title('Распределение расходов по категориям')
    ax.axis('equal')
    fig.tight_layout()
    fig.savefig(OUTPUT / 'expenses_pie.png', dpi=200, bbox_inches='tight')
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, max(5, len(totals) * 0.55)))
    totals.sort_values().plot.barh(ax=ax)
    ax.set_title('Расходы по категориям')
    ax.set_xlabel('Сумма расходов (в валюте выписки)')
    ax.set_ylabel('Категория')
    fig.tight_layout()
    fig.savefig(OUTPUT / 'expenses_bar.png', dpi=200, bbox_inches='tight')
    plt.close(fig)

    print('Готово: expenses_pie.png и expenses_bar.png')


if __name__ == '__main__':
    main()
