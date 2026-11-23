"""CSV / Excel row readers shared by every import."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from backend.core.exceptions import ValidationFailed

MAX_ROWS = 200_000


def read_rows(content: bytes, filename: str) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header = [str(h or "").strip().lower().replace(" ", "_") for h in next(it)]
        except StopIteration as exc:
            raise ValidationFailed("The file is empty") from exc
        rows = []
        for r in it:
            if not any(c not in (None, "") for c in r):
                continue
            rows.append({h: (v.date() if isinstance(v, datetime) else v) for h, v in zip(header, r) if h})
    elif name.endswith((".csv", ".txt")) or not name:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        rows = [{(k or "").strip().lower().replace(" ", "_"): (v.strip() if isinstance(v, str) else v)
                 for k, v in r.items() if k} for r in reader]
        rows = [r for r in rows if any(v not in (None, "") for v in r.values())]
    else:
        raise ValidationFailed("Upload a .csv or .xlsx file")
    if len(rows) > MAX_ROWS:
        raise ValidationFailed(f"Too many rows (maximum {MAX_ROWS})")
    if not rows:
        raise ValidationFailed("No data rows found")
    return rows


def as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise ValidationFailed(f"Unrecognised date '{s}'")
