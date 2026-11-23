"""FastAPI dependencies: DB session, authenticated actor, permission checks, company context."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.authentication.models import User
from backend.authentication.security import decode_token
from backend.core.actor import Actor, actor_for
from backend.core.exceptions import AuthenticationFailed, NotFound
from backend.database.session import get_db
from backend.masters.models import Company

bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def get_actor(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Actor:
    if creds is None or not creds.credentials:
        raise AuthenticationFailed("Not authenticated")
    try:
        payload = decode_token(creds.credentials)
    except Exception as exc:  # expired / invalid signature
        raise AuthenticationFailed("Session expired or invalid; please sign in again") from exc
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active or payload.get("ver") != user.token_version:
        raise AuthenticationFailed("Session is no longer valid; please sign in again")
    return actor_for(user)


CurrentActor = Annotated[Actor, Depends(get_actor)]


def require(*perms: str):
    def _dep(actor: CurrentActor) -> Actor:
        actor.require(*perms)
        return actor
    return Depends(_dep)


def get_company_id(db: DB, actor: CurrentActor,
                   x_company_id: Annotated[int | None, Header()] = None) -> int:
    cid = x_company_id or getattr(actor.user, "default_company_id", None)
    if cid is None:
        cid = db.scalar(select(Company.id).where(Company.is_active.is_(True)).order_by(Company.id))
    if cid is None or db.get(Company, cid) is None:
        raise NotFound("Company not found")
    return int(cid)


CompanyId = Annotated[int, Depends(get_company_id)]


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
