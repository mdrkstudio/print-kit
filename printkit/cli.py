from __future__ import annotations
import argparse
import csv
import html
import json
import re
import sys
import textwrap
import zipfile
from itertools import islice
from collections import defaultdict
from pathlib import Path


def load_guests(path: Path, sheet: str | None = None) -> list[dict[str, str]]:
    if path.stat().st_size > 10_000_000:
        raise ValueError("Размер входного файла должен быть не больше 10 МБ")
    suffix = path.suffix.lower()
    if suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(rows, dict):
            rows = rows.get("guests")
        if not isinstance(rows, list):
            raise ValueError("JSON: ожидается массив объектов name/table или объект guests")
    elif suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as file:
            sample = file.read(4096); file.seek(0)
            try: dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error: dialect = csv.excel
            reader = csv.DictReader(file, dialect=dialect)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)):
                raise ValueError("CSV: повторяются заголовки столбцов")
            rows = list(islice(reader, 1001))
    elif suffix == ".xlsx":
        try: from openpyxl import load_workbook
        except ImportError as exc: raise ValueError('Для XLSX установите пакет: pip install ".[xlsx]"') from exc
        book = load_workbook(path, read_only=True, data_only=True)
        try:
            if sheet and sheet not in book.sheetnames: raise ValueError("Лист не найден: " + sheet)
            values = (book[sheet] if sheet else book.active).iter_rows(values_only=True)
            header = [str(v or "").strip() for v in next(values, ())]
            if len(header) != len(set(header)): raise ValueError("XLSX: повторяются заголовки")
            rows = [dict(zip(header, row)) for row in islice(values, 1001)]
        finally: book.close()
    else:
        raise ValueError("Поддерживаются CSV, JSON и XLSX")
    if len(rows) > 1000: raise ValueError("Максимум 1000 гостей за один запуск")
    result = []; seen = set()
    for index, row in enumerate(rows, 2):
        if not isinstance(row, dict): raise ValueError(f"Строка {index}: ожидается объект")
        if not any(v is not None and str(v).strip() for v in row.values()): continue
        if None in row: raise ValueError(f"Строка {index}: лишние поля CSV")
        normalized = {str(k).strip().lower(): v for k,v in row.items()}
        name = normalized.get("name", normalized.get("имя", ""))
        table = normalized.get("table", normalized.get("стол", ""))
        name = re.sub(r"\s+", " ", str(name or "")).strip()
        table = re.sub(r"\s+", " ", str(table if table is not None else "")).strip()
        if not name or not table: raise ValueError(f"Строка {index}: нужны name и table")
        if len(name) > 100 or len(table) > 30: raise ValueError(f"Строка {index}: слишком длинное имя или название стола")
        if (name.casefold(), table.casefold()) in seen: raise ValueError(f"Строка {index}: повтор гостя за тем же столом")
        seen.add((name.casefold(),table.casefold()));result.append({"name":name,"table":table})
    if not result: raise ValueError("Список гостей пуст")
    return result


def name_lines(name: str) -> list[str]:
    # Wrap full names without dropping words or guessing surnames.
    return textwrap.wrap(name, width=22, break_long_words=True, break_on_hyphens=False)


def card_svg(guest: dict[str,str], title: str) -> str:
    lines = name_lines(guest["name"])
    size = min(6.0, 24 / max(1, len(lines)))
    texts = "".join(f'<tspan x="45" dy="{size*1.25 if i else 0}">{html.escape(line)}</tspan>' for i,line in enumerate(lines))
    y = 29 - (len(lines)-1)*size*.6
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="90mm" height="55mm" viewBox="0 0 90 55"><title>{html.escape(guest['name'])}</title><rect width="90" height="55" fill="white"/><rect x="3" y="3" width="84" height="49" rx="2" fill="none" stroke="#394c46" stroke-width=".3"/><path d="M38 12h14" stroke="#879b91" stroke-width=".4"/><text x="45" y="{y}" text-anchor="middle" font-family="Georgia,serif" font-size="{size}" fill="#203c33">{texts}</text><text x="45" y="45" text-anchor="middle" font-family="sans-serif" font-size="3" fill="#55695f">{html.escape('Стол '+guest['table'])}</text></svg>'''


def table_svg(table: str) -> str:
    size = min(28, 85 / max(1, len(table)) * 1.5)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="90mm" height="120mm" viewBox="0 0 90 120"><title>{html.escape('Стол '+table)}</title><rect width="90" height="120" fill="white"/><rect x="4" y="4" width="82" height="112" rx="2" fill="none" stroke="#394c46" stroke-width=".4"/><text x="45" y="40" text-anchor="middle" font-family="sans-serif" font-size="5" fill="#55695f">СТОЛ</text><text x="45" y="75" text-anchor="middle" font-family="Georgia,serif" font-size="{size}" fill="#203c33">{html.escape(table)}</text></svg>'''


def document(title: str, body: str, css: str = "") -> str:
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>@page{{size:A4;margin:12mm}}*{{box-sizing:border-box}}body{{margin:0;background:#eee;color:#203c33;font-family:Georgia,serif}}.sheet{{background:#fff;margin:12mm auto;padding:10mm;width:210mm;min-height:297mm;break-after:page}}.sheet:last-child{{break-after:auto}}h1{{font-size:26pt;margin:0 0 8mm}}h2{{font-size:18pt;margin:0 0 4mm}}p{{margin:0 0 3mm}}.controls{{text-align:center;padding:15px;font:14px sans-serif}}button{{padding:10px 18px;cursor:pointer}}.cards{{display:grid;grid-template-columns:90mm 90mm;gap:6mm}}.cards img{{width:90mm;height:55mm}}.tables{{display:grid;grid-template-columns:90mm 90mm;gap:8mm}}.tables img{{width:90mm;height:120mm}}.seat{{border-bottom:1px solid #d8e0dc;padding:3mm 0;font-size:14pt;overflow-wrap:anywhere}}@media print{{body{{background:white}}.sheet{{width:auto;min-height:0;padding:0;margin:0}}.controls{{display:none}}}}{css}</style></head><body><div class="controls"><button onclick="window.print()">Печать / сохранить PDF</button><p>Формат A4, масштаб 100%, колонтитулы выключены</p></div>{body}</body></html>'''


def chunks(items, count):
    return [items[i:i+count] for i in range(0,len(items),count)]


def render(guests, output: Path, title: str, mode: str) -> None:
    # Never remove or replace an existing user's directory.
    if output.exists() and any(output.iterdir()): raise ValueError("Папка вывода не пуста. Выберите новую папку")
    tables = sorted({g["table"] for g in guests}, key=lambda s:(not s.isdigit(),int(s) if s.isdigit() else s.casefold()))
    output.mkdir(parents=True, exist_ok=True)
    if mode in ("all","cards"):
        (output/'cards').mkdir(exist_ok=True); images=[]
        for i,g in enumerate(guests,1):
            name=f'cards/{i:04d}.svg';(output/name).write_text(card_svg(g,title),encoding='utf-8');images.append(f'<img src="{name}" alt="{html.escape(g["name"],quote=True)}">')
        body=''.join('<section class="sheet"><div class="cards">'+''.join(page)+'</div></section>' for page in chunks(images,8))
        (output/'cards.html').write_text(document(title+' / карточки',body),encoding='utf-8')
    if mode in ("all","tables"):
        (output/'tables').mkdir(exist_ok=True);images=[]
        for i,table in enumerate(tables,1):
            name=f'tables/{i:03d}.svg';(output/name).write_text(table_svg(table),encoding='utf-8');images.append(f'<img src="{name}" alt="{html.escape(table,quote=True)}">')
        body=''.join('<section class="sheet"><div class="tables">'+''.join(page)+'</div></section>' for page in chunks(images,4))
        (output/'tables.html').write_text(document(title+' / номера столов',body),encoding='utf-8')
    if mode in ("all","seating"):
        grouped=defaultdict(list)
        for g in guests:grouped[g['table']].append(g['name'])
        pages=[]
        for table in tables:
            # Bound both row count and text length so long names get room on A4.
            parts=[];page=[];weight=0
            for name in sorted(grouped[table],key=str.casefold):
                cost=max(1,(len(name)+39)//40)
                if weight+cost>17:parts.append(page);page=[];weight=0
                page.append(name);weight+=cost
            if page:parts.append(page)
            for i,names in enumerate(parts,1):
                rows=''.join('<div class="seat">'+html.escape(n)+'</div>' for n in names)
                pages.append(f'<section class="sheet"><p>{html.escape(title)}</p><h1>Стол {html.escape(table)}</h1><p>{i} / {len(parts)}</p>{rows}</section>')
        (output/'seating.html').write_text(document(title+' / рассадка',''.join(pages)),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps({'title':title,'guests':len(guests),'tables':tables,'format':mode},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main() -> None:
    parser=argparse.ArgumentParser(description="Карточки гостей, номера столов и рассадка для печати")
    parser.add_argument('input',type=Path,help="CSV, JSON или XLSX с полями name/table")
    parser.add_argument('--output',type=Path,default=Path('output'))
    parser.add_argument('--title',default='Мероприятие')
    parser.add_argument('--format',choices=['all','cards','tables','seating'],default='all')
    parser.add_argument('--sheet',help='Название листа XLSX')
    args=parser.parse_args()
    try:
        if not args.title.strip() or len(args.title)>100: raise ValueError("Название: от 1 до 100 символов")
        guests=load_guests(args.input,args.sheet);render(guests,args.output,args.title,args.format)
    except (ValueError,OSError,csv.Error,zipfile.BadZipFile) as exc:
        parser.exit(2,f'Ошибка: {exc}\n')
    print(f'Гостей: {len(guests)}. Столов: {len({g["table"] for g in guests})}. Результат: {args.output}')
