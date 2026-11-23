from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api.deps import DB, CurrentActor
from backend.authentication import service
from backend.authentication.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/login")
def login(body: LoginIn, db: DB):
    return service.login(db, body.username, body.password)


@router.get("/me")
def me(actor: CurrentActor, db: DB):
    return service.profile(db.get(User, actor.id))


@router.post("/change-password")
def change_password(body: PasswordIn, actor: CurrentActor, db: DB):
    service.change_password(db, actor, body.current_password, body.new_password)
    db.commit()
    return {"ok": True, "message": "Password changed. Please sign in again."}


@router.post("/logout-all")
def logout_all(actor: CurrentActor, db: DB):
    service.logout_all(db, actor)
    db.commit()
    return {"ok": True}
