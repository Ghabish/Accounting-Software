"""Professional Excel / CSV / PDF rendering for any report payload."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi.responses import JSONResponse, Response, StreamingResponse

from backend.api.serialize import jsonable

BRAND = "1F2A44"
ACCENT = "C8102E"


def _num(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def _fname(report: dict, ext: str) -> str:
    base = "".join(c if c.isalnum() else "_" for c in report.get("title", "report"))[:60].strip("_")
    return f"{base}_{datetime.now().strftime('%Y%m%d_%H%M')}.{ext}"


def to_xlsx(reports: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="999999")
    for rep in reports:
        ws = wb.create_sheet(title=("".join(c for c in rep.get("sheet") or rep["title"] if c not in "[]:*?/\\"))[:31])
        cols = rep["columns"]
        ws.append([rep.get("company", "")])
        ws["A1"].font = Font(bold=True, size=14, color=BRAND)
        ws.append([rep["title"]])
        ws["A2"].font = Font(bold=True, size=12)
        ws.append([rep.get("subtitle", "")])
        ws["A3"].font = Font(italic=True, color="555555")
        ws.append([f"Generated {datetime.now().strftime('%d %b %Y %H:%M')} - figures derived from the posted general ledger"])
        ws["A4"].font = Font(size=8, color="888888")
        ws.append([])
        ws.append([c["label"] for c in cols])
        hdr = ws.max_row
        for i in range(1, len(cols) + 1):
            cell = ws.cell(row=hdr, column=i)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=BRAND)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for r in rep["rows"]:
            vals = []
            for c in cols:
                v = r.get(c["key"])
                if c["key"] == "label":
                    v = ("    " * int(r.get("level", 0) or 0)) + str(v or "")
                vals.append(_num(v) if c["type"] in ("money", "int", "pct", "number") else jsonable(v))
            ws.append(vals)
            rr = ws.max_row
            style = r.get("style")
            for i, c in enumerate(cols, start=1):
                cell = ws.cell(row=rr, column=i)
                if c["type"] == "money":
                    cell.number_format = '#,##0.00;(#,##0.00);"-"'
                elif c["type"] == "pct":
                    cell.number_format = '0.0"%"'
                elif c["type"] == "int":
                    cell.number_format = "#,##0"
                if style in ("header", "total", "grand", "subtotal"):
                    cell.font = Font(bold=True, color=BRAND if style == "header" else "000000")
                if style in ("total", "grand"):
                    cell.border = Border(top=thin, bottom=Side(style="double" if style == "grand" else "thin"))
                if style == "grand":
                    cell.fill = PatternFill("solid", fgColor="EEF1F6")
                if r.get("abnormal"):
                    cell.font = Font(color=ACCENT)
        for i, c in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(i)].width = 48 if c["key"] == "label" else (16 if c["type"] != "text" else 22)
        ws.freeze_panes = ws.cell(row=hdr + 1, column=2)
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv(report: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([report.get("company", "")])
    w.writerow([report["title"]])
    w.writerow([report.get("subtitle", "")])
    w.writerow([c["label"] for c in report["columns"]])
    for r in report["rows"]:
        out = []
        for c in report["columns"]:
            v = r.get(c["key"])
            if c["key"] == "label":
                v = ("  " * int(r.get("level", 0) or 0)) + str(v or "")
            out.append("" if v is None else jsonable(v))
        w.writerow(out)
    return buf.getvalue().encode("utf-8-sig")


def _fmt(v: Any, typ: str) -> str:
    if v is None or v == "":
        return ""
    if typ == "money":
        d = Decimal(str(v))
        s = f"{abs(d):,.2f}"
        return f"({s})" if d < 0 else ("-" if d == 0 else s)
    if typ == "pct":
        return f"{Decimal(str(v)):.1f}%"
    if typ == "int":
        return f"{int(Decimal(str(v))):,}"
    return str(jsonable(v))


def to_pdf(reports: list[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=reports[0]["title"], author="Universal Cinemas Finance")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=colors.HexColor("#" + BRAND), fontSize=15, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceAfter=2)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.HexColor("#555555"))
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=7.5, leading=9)

    def on_page(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(12 * mm, 8 * mm, f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}  |  Derived from the posted general ledger")
        canvas.drawRightString(page[0] - 12 * mm, 8 * mm, f"Page {d.page}")
        canvas.restoreState()

    story = []
    for n, rep in enumerate(reports):
        if n:
            story.append(PageBreak())
        story += [Paragraph(rep.get("company", ""), h1), Paragraph(rep["title"], h2),
                  Paragraph(rep.get("subtitle", ""), small), Spacer(1, 4 * mm)]
        cols = rep["columns"]
        data = [[Paragraph(f"<b>{c['label']}</b>", cell) for c in cols]]
        styles = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + BRAND)),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F8FA")])]
        for i, r in enumerate(rep["rows"], start=1):
            line = []
            for c in cols:
                v = r.get(c["key"])
                if c["key"] == "label":
                    txt = ("&nbsp;" * 4 * int(r.get("level", 0) or 0)) + str(v or "").replace("&", "&amp;").replace("<", "&lt;")
                    st = r.get("style")
                    line.append(Paragraph(f"<b>{txt}</b>" if st in ("header", "total", "grand", "subtotal") else txt, cell))
                elif c["type"] == "text":
                    line.append(Paragraph(str(jsonable(v) or "").replace("&", "&amp;").replace("<", "&lt;")[:120], cell))
                else:
                    line.append(_fmt(v, c["type"]))
            data.append(line)
            st = r.get("style")
            if st in ("total", "grand", "subtotal"):
                styles.append(("FONTNAME", (1, i), (-1, i), "Helvetica-Bold"))
                styles.append(("LINEABOVE", (1, i), (-1, i), 0.5, colors.grey))
            if st == "grand":
                styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E8ECF3")))
                styles.append(("LINEBELOW", (1, i), (-1, i), 1, colors.black))
        avail = page[0] - 24 * mm
        n_other = max(len(cols) - 1, 1)
        first = min(avail * 0.38, avail - n_other * 18 * mm) if len(cols) > 2 else avail * 0.6
        widths = [first] + [(avail - first) / n_other] * n_other
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle(styles))
        story.append(t)
        meta = rep.get("meta") or {}
        notes = []
        if "balanced" in meta and meta["balanced"] is not None:
            notes.append("Check: " + ("BALANCED" if meta["balanced"] else f"NOT BALANCED (difference {meta.get('difference')})"))
        if "reconciles" in meta:
            notes.append("Cash reconciliation: " + ("agrees to balance sheet cash" if meta["reconciles"] else f"DIFFERENCE {meta.get('difference')}"))
        if notes:
            story += [Spacer(1, 3 * mm), Paragraph(" | ".join(notes), small)]
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def respond(report: dict | list[dict], fmt: str | None):
    reports = report if isinstance(report, list) else [report]
    fmt = (fmt or "json").lower()
    if fmt == "json":
        return JSONResponse(jsonable(report))
    if fmt == "xlsx":
        return Response(to_xlsx(reports), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{_fname(reports[0], "xlsx")}"'})
    if fmt == "csv":
        return Response(to_csv(reports[0]), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{_fname(reports[0], "csv")}"'})
    if fmt == "pdf":
        return StreamingResponse(io.BytesIO(to_pdf(reports)), media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{_fname(reports[0], "pdf")}"'})
    return JSONResponse(status_code=400, content={"error": "bad_format", "message": "format must be json, xlsx, csv or pdf"})
