"""Создаёт исключительно синтетическую выписку для проверки PDF → LLM."""
from pathlib import Path
import pymupdf
ROOT=Path(__file__).resolve().parent.parent
font=Path('/usr/share/fonts/TTF/DejaVuSans.ttf')
if not font.exists():
    raise SystemExit('Для генерации нужен DejaVuSans.ttf; готовый PDF находится в fixtures.')
doc=pymupdf.open()
page=doc.new_page(width=595,height=842)
page.insert_font(fontname='Demo',fontfile=str(font))
page.draw_rect(pymupdf.Rect(35,35,560,115),color=None,fill=(.45,.38,.85))
page.insert_text((55,70),'СТИПЕНДИЯ · ДЕМО-ВЫПИСКА',fontname='Demo',fontsize=18,color=(1,1,1))
page.insert_text((55,94),'Синтетические данные. Реальных счетов и клиентов нет.',fontname='Demo',fontsize=9,color=(1,1,1))
lines=[
 'Период: 25.09.2026 — 26.09.2026',
 'Все суммы в RUB. Минус — расход, плюс — поступление.',
 '',
 'Дата             Описание                         Сумма        Валюта',
 '25.09.2026       Демо-кафе Перемена                -290.00      RUB',
 '25.09.2026       Городской транспорт               -60.00       RUB',
 '26.09.2026       Тестовая стипендия                 +8000.00    RUB',
 '',
 'Всего операций: 3. Баланс счёта не предоставлен.',
 'Документ предназначен только для демонстрации приложения.',
]
page.insert_text((45,155),'\n'.join(lines),fontname='Demo',fontsize=10,lineheight=2)
path=ROOT/'fixtures/demo-statement.pdf'
doc.save(path)
print(path)
