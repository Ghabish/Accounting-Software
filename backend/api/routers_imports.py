"""Data import API (CSV / Excel) and opening balances."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from backend.api.deps import DB, CompanyId, CurrentActor
from backend.api.serialize import jsonable
from backend.core.exceptions import NotFound
from backend.imports import service as svc
from backend.imports.parsers import read_rows

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.get("/templates/{name}")
def template(name: str, actor: CurrentActor):
    cols = svc.TEMPLATES.get(name)
    if cols is None:
        raise NotFound("Unknown template")
    return Response(",".join(cols) + "\n", media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}_template.csv"'})


@router.post("/{kind}")
async def run_import(kind: str, db: DB, actor: CurrentActor, company_id: CompanyId, file: UploadFile = File(...),
                     cutover_date: date | None = Form(None)):
    actor.require("import.run")
    rows = read_rows(await file.read(), file.filename or "")
    if kind == "gl-opening":
        je, diff = svc.import_gl_opening(db, actor, company_id, rows, cutover_date or date.today())
        result = {"journal_id": je.id, "number": je.number, "carried_to_clearing": diff}
    elif kind == "supplier-opening":
        docs = svc.import_supplier_opening(db, actor, company_id, rows, cutover_date or date.today())
        result = {"documents": len(docs)}
    elif kind == "customer-opening":
        docs = svc.import_customer_opening(db, actor, company_id, rows, cutover_date or date.today())
        result = {"documents": len(docs)}
    elif kind == "suppliers":
        result = {"created": svc.import_suppliers(db, actor, rows)}
    elif kind == "customers":
        result = {"created": svc.import_customers(db, actor, rows)}
    elif kind == "accounts":
        result = {"created": svc.import_accounts(db, actor, rows)}
    elif kind == "journals":
        result = {"journals": svc.import_journals(db, actor, company_id, rows)}
    else:
        raise NotFound("Unknown import type")
    db.commit()
    return jsonable(result)


@router.get("/opening/status")
def opening_status(db: DB, actor: CurrentActor, company_id: CompanyId, cutover_date: date):
    actor.require("opening.manage")
    return jsonable(svc.opening_status(db, company_id, cutover_date))
