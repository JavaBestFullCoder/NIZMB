import re
from datetime import datetime, date
from config import TZ


def parse_amount(text: str) -> float | None:
    text = text.strip().replace(",", ".").replace(" ", "")
    try:
        amount = float(text)
        if amount <= 0:
            return None
        return round(amount, 2)
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    text = text.strip()
    if text == "0" or text.lower() == "сегодня":
        return datetime.now(TZ).date()
    patterns = [
        (r"^\d{2}\.\d{2}\.\d{4}$", "%d.%m.%Y"),
        (r"^\d{4}-\d{2}-\d{2}$", "%Y-%m-%d"),
    ]
    for pattern, fmt in patterns:
        if re.match(pattern, text):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                return None
    return None


def today_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def format_date(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%d.%m.%Y")


def format_amount(amount: float) -> str:
    if amount >= 0:
        return f"{amount:,.2f}"
    return f"-{abs(amount):,.2f}"


def date_range_str(start: str, end: str) -> str:
    return f"с {format_date(start)} по {format_date(end)}"
