import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from config import REPORTS_DIR
from database import get_all_objects_transactions, get_hq_transactions, get_objects, get_object_transactions, get_object_balance_before, get_object, get_hq_balance_before, EXPENSE_TYPES
from utils import format_date, format_amount, today_str, TZ

THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=14)

TYPE_NAMES = {
    "income": "Приход",
    "expense": "Расход",
    "director_expense": "Расход Директора",
    "supplier_payment": "Оплата Поставщика",
    "transfer_out": "Перевод в офис",
    "transfer_in": "Перевод из объекта",
}


def _style_header(ws, row: int, cols: int):
    for col in range(1, cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER


def _auto_width(ws, cols: int, min_width: int = 12, max_width: int = 40):
    for col in range(1, cols + 1):
        max_len = min_width
        for r in ws.iter_rows(min_col=col, max_col=col, values_only=False):
            for cell in r:
                if cell.value:
                    max_len = max(max_len, min(len(str(cell.value)), max_width))
        ws.column_dimensions[get_column_letter(col)].width = max_len + 2


def _add_title(ws, title: str, cols: int):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=cols)
    cell = ws.cell(row=1, column=1, value=title)
    cell.font = TITLE_FONT
    cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 30


def _write_transactions(ws, transactions, start_row: int, headers: list[str]):
    for col_idx, h in enumerate(headers, 1):
        ws.cell(row=start_row, column=col_idx, value=h)
    _style_header(ws, start_row, len(headers))
    row = start_row + 1

    for t in transactions:
        ws.cell(row=row, column=1, value=format_date(t["transaction_date"])).border = THIN_BORDER
        ws.cell(row=row, column=2, value=TYPE_NAMES.get(t["type"], t["type"])).border = THIN_BORDER
        amount_val = -t["amount"] if t["type"] in EXPENSE_TYPES else t["amount"]
        ws.cell(row=row, column=3, value=format_amount(amount_val)).border = THIN_BORDER
        if t["type"] in EXPENSE_TYPES:
            ws.cell(row=row, column=3).font = Font(color="FF0000")
        elif t["type"] in ("income", "transfer_in"):
            ws.cell(row=row, column=3).font = Font(color="008000")
        ws.cell(row=row, column=4, value=t.get("reason", "") or "").border = THIN_BORDER
        ws.cell(row=row, column=5, value=t.get("user_name", "") or "").border = THIN_BORDER
        ws.cell(row=row, column=6, value=t.get("object_name", "") or "").border = THIN_BORDER
        row += 1
    return row


def _balance_as_of(object_id: int, transactions: list[dict], date_str: str, opening: float) -> float:
    """Calculate balance including all transactions up to and including date_str."""
    bal = opening
    for t in transactions:
        if t["transaction_date"] > date_str:
            break
        if t["type"] == "income":
            bal += t["amount"]
        elif t["type"] in EXPENSE_TYPES:
            bal -= t["amount"]
    return bal


# --- General report: one sheet per object ---

async def generate_all_objects_report(start_date: str, end_date: str) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"Общий_отчет_{start_date}_по_{end_date}_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(REPORTS_DIR, filename)

    wb = Workbook()
    wb.remove(wb.active)
    objects = await get_objects()
    headers = ["Дата", "Тип операции", "Сумма", "Причина", "Сотрудник", "Объект"]
    total_income = 0.0
    total_expense = 0.0
    total_transfer = 0.0

    for obj in objects:
        ws = wb.create_sheet(title=obj["name"][:31])
        txns = await get_object_transactions(obj["id"], start_date, end_date)
        opening = await get_object_balance_before(obj["id"], start_date)
        closing = _balance_as_of(obj["id"], txns, end_date, opening)

        title = f"«{obj['name']}» {format_date(start_date)} — {format_date(end_date)}"
        _add_title(ws, title, len(headers))

        ws.cell(row=3, column=1, value="Остаток на начало:").font = Font(bold=True)
        ws.cell(row=3, column=2, value=format_amount(opening)).border = THIN_BORDER
        _write_transactions(ws, txns, 5, headers)

        last_row = ws.max_row + 1
        ws.cell(row=last_row, column=1, value="Остаток на конец:").font = Font(bold=True)
        ws.cell(row=last_row, column=2, value=format_amount(closing)).border = THIN_BORDER

        _auto_width(ws, len(headers))
        total_income += sum(t["amount"] for t in txns if t["type"] == "income")
        total_expense += sum(t["amount"] for t in txns if t["type"] == "expense")
        total_transfer += sum(t["amount"] for t in txns if t["type"] == "transfer_out")

    # HQ sheet
    hq_headers = ["Дата", "Тип операции", "Сумма", "Причина", "Сотрудник", "Источник"]
    ws_hq = wb.create_sheet(title="Головной офис")
    hq_txns = await get_hq_transactions(start_date, end_date)
    hq_opening = await get_hq_balance_before(start_date)
    hq_closing = hq_opening
    for t in hq_txns:
        if t["type"] == "transfer_in":
            hq_closing += t["amount"]
        elif t["type"] in EXPENSE_TYPES:
            hq_closing -= t["amount"]

    _add_title(ws_hq, f"Головной офис {format_date(start_date)} — {format_date(end_date)}", len(hq_headers))
    ws_hq.cell(row=3, column=1, value="Остаток на начало:").font = Font(bold=True)
    ws_hq.cell(row=3, column=2, value=format_amount(hq_opening)).border = THIN_BORDER

    hq_data_row = 5
    for col_idx, h in enumerate(hq_headers, 1):
        ws_hq.cell(row=hq_data_row, column=col_idx, value=h)
    _style_header(ws_hq, hq_data_row, len(hq_headers))
    r = hq_data_row + 1
    for t in hq_txns:
        ws_hq.cell(row=r, column=1, value=format_date(t["transaction_date"])).border = THIN_BORDER
        ws_hq.cell(row=r, column=2, value=TYPE_NAMES.get(t["type"], t["type"])).border = THIN_BORDER
        amount_val = -t["amount"] if t["type"] in EXPENSE_TYPES else t["amount"]
        ws_hq.cell(row=r, column=3, value=format_amount(amount_val)).border = THIN_BORDER
        if t["type"] in EXPENSE_TYPES:
            ws_hq.cell(row=r, column=3).font = Font(color="FF0000")
        elif t["type"] == "transfer_in":
            ws_hq.cell(row=r, column=3).font = Font(color="008000")
        ws_hq.cell(row=r, column=4, value=t.get("reason", "") or "").border = THIN_BORDER
        ws_hq.cell(row=r, column=5, value=t.get("user_name", "") or "").border = THIN_BORDER
        ws_hq.cell(row=r, column=6, value=t.get("source_object_name", "") or "").border = THIN_BORDER
        r += 1

    last_row = ws_hq.max_row + 1
    ws_hq.cell(row=last_row, column=1, value="Остаток на конец:").font = Font(bold=True)
    ws_hq.cell(row=last_row, column=2, value=format_amount(hq_closing)).border = THIN_BORDER
    _auto_width(ws_hq, len(hq_headers))

    # Summary sheet
    ws = wb.create_sheet(title="Сводка")
    _add_title(ws, f"Сводка {format_date(start_date)} — {format_date(end_date)}", 2)
    ws.cell(row=3, column=1, value="Показатель").font = Font(bold=True)
    ws.cell(row=3, column=2, value="Сумма").font = Font(bold=True)
    _style_header(ws, 3, 2)
    ws.cell(row=4, column=1, value="Всего приход").border = THIN_BORDER
    ws.cell(row=4, column=2, value=format_amount(total_income)).border = THIN_BORDER
    ws.cell(row=5, column=1, value="Всего расход").border = THIN_BORDER
    ws.cell(row=5, column=2, value=format_amount(total_expense)).border = THIN_BORDER
    ws.cell(row=6, column=1, value="Всего переводов в офис").border = THIN_BORDER
    ws.cell(row=6, column=2, value=format_amount(total_transfer)).border = THIN_BORDER

    _auto_width(ws, 2)
    wb.save(filepath)
    return filepath


# --- Single object report ---

async def generate_object_report(object_id: int, object_name: str, start_date: str, end_date: str) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"Отчет_{object_name}_{start_date}_по_{end_date}_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(REPORTS_DIR, filename)

    txns = await get_object_transactions(object_id, start_date, end_date)
    opening = await get_object_balance_before(object_id, start_date)
    closing = _balance_as_of(object_id, txns, end_date, opening)

    wb = Workbook()
    ws = wb.active
    ws.title = object_name[:31]

    headers = ["Дата", "Тип операции", "Сумма", "Причина", "Сотрудник"]
    _add_title(ws, f"«{object_name}» {format_date(start_date)} — {format_date(end_date)}", len(headers))

    ws.cell(row=3, column=1, value="Остаток на начало периода:").font = Font(bold=True)
    ws.cell(row=3, column=2, value=format_amount(opening)).border = THIN_BORDER

    _write_transactions(ws, txns, 5, headers[:5])

    last_row = ws.max_row + 1
    ws.cell(row=last_row, column=1, value="Остаток на конец периода:").font = Font(bold=True)
    ws.cell(row=last_row, column=2, value=format_amount(closing)).border = THIN_BORDER

    _auto_width(ws, len(headers))
    wb.save(filepath)
    return filepath


# --- Daily report ---

async def generate_daily_report(object_id: int, object_name: str, date_str: str | None = None) -> str:
    if date_str is None:
        date_str = today_str()
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"Дневной_{object_name}_{date_str}_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(REPORTS_DIR, filename)

    from database import get_daily_summary

    summary = await get_daily_summary(object_id, date_str)
    txns = await get_object_transactions(object_id, date_str, date_str)
    headers = ["Дата", "Тип операции", "Сумма", "Причина", "Сотрудник"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Дневной отчет"
    _add_title(ws, f"Дневной отчет «{object_name}» за {format_date(date_str)}", len(headers))

    ws.cell(row=3, column=1, value="Остаток на начало дня:").font = Font(bold=True)
    ws.cell(row=3, column=2, value=format_amount(summary["opening"])).border = THIN_BORDER

    _write_transactions(ws, txns, 5, headers)

    r = ws.max_row + 1
    ws.cell(row=r, column=1, value="Итого приход:").font = Font(bold=True)
    ws.cell(row=r, column=2, value=format_amount(summary["income"])).border = THIN_BORDER
    r += 1
    ws.cell(row=r, column=1, value="Итого расход:").font = Font(bold=True)
    ws.cell(row=r, column=2, value=format_amount(summary["expense"])).border = THIN_BORDER
    r += 1
    ws.cell(row=r, column=1, value="Перевод в офис:").font = Font(bold=True)
    ws.cell(row=r, column=2, value=format_amount(summary["transfer_out"])).border = THIN_BORDER
    r += 1
    ws.cell(row=r, column=1, value="Остаток на конец дня:").font = Font(bold=True)
    ws.cell(row=r, column=2, value=format_amount(summary["closing"])).border = THIN_BORDER

    _auto_width(ws, len(headers))
    wb.save(filepath)
    return filepath


# --- Text summary for Telegram ---

async def generate_object_report_text(object_id: int, object_name: str, start_date: str, end_date: str) -> str:
    txns = await get_object_transactions(object_id, start_date, end_date)
    opening = await get_object_balance_before(object_id, start_date)
    closing = _balance_as_of(object_id, txns, end_date, opening)
    total_income = sum(t["amount"] for t in txns if t["type"] == "income")
    total_expense = sum(t["amount"] for t in txns if t["type"] in ("expense", "transfer_out"))

    return (
        f"📅 {format_date(start_date)} — {format_date(end_date)}\n"
        f"🔵 Остаток на начало: {format_amount(opening)} сум\n"
        f"🟢 Всего приход: +{format_amount(total_income)} сум\n"
        f"🔴 Всего расход: -{format_amount(total_expense)} сум\n"
        f"🏁 Остаток на конец: {format_amount(closing)} сум"
    )
