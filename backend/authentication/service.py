"""Login, password management and user administration."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.audit.service import record
from backend.authentication.models import Role, User, UserSiteAccess
from backend.authentication.security import (
    create_access_token, hash_password, validate_password_strength, verify_password,
)
from backend.config import get_settings
from backend.core.actor import Actor, actor_for
from backend.core.exceptions import AuthenticationFailed, Conflict, NotFound, ValidationFailed
from backend.database.base import utcnow


_ip_failures: dict[str, list] = {}


def _ip_blocked(ip: str | None) -> bool:
    """Per-IP throttle against password spraying (single process; add proxy rate limiting for multi-worker)."""
    if not ip:
        return False
    s = get_settings()
    cutoff = utcnow() - timedelta(minutes=s.login_ip_window_minutes)
    hits = [t for t in _ip_failures.get(ip, []) if t > cutoff]
    _ip_failures[ip] = hits
    return len(hits) >= s.login_ip_max_failures


def _ip_fail(ip: str | None) -> None:
    if ip:
        _ip_failures.setdefault(ip, []).append(utcnow())


def login(db: Session, username: str, password: str) -> dict:
    from backend.audit.service import request_context
    s = get_settings()
    ip = request_context.get().get("ip")
    if _ip_blocked(ip):
        raise AuthenticationFailed("Too many failed sign-in attempts from this address; try again later", code="ip_throttled")
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    now = utcnow()
    if user is None:
        _ip_fail(ip)
        record(db, None, "auth.login_failed", "user", None, notes=f"unknown user {username[:60]}")
        db.commit()
        raise AuthenticationFailed("Invalid username or password")
    if user.locked_until and user.locked_until.replace(tzinfo=now.tzinfo) > now:
        raise AuthenticationFailed("Account temporarily locked after repeated failed sign-ins; try again later",
                                   code="account_locked")
    if not user.is_active or not verify_password(password, user.password_hash):
        _ip_fail(ip)
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= s.max_failed_logins:
            user.locked_until = now + timedelta(minutes=s.lockout_minutes)
            user.failed_logins = 0
        record(db, user, "auth.login_failed", "user", user.id)
        db.commit()
        raise AuthenticationFailed("Invalid username or password")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    token, exp = create_access_token(user.id, user.token_version)
    record(db, user, "auth.login", "user", user.id)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat(), "user": profile(user)}


def profile(user: User) -> dict:
    a = actor_for(user)
    return {
        "id": user.id, "username": user.username, "full_name": user.full_name, "email": user.email,
        "is_superuser": user.is_superuser, "all_sites": a.site_ids is None,
        "site_ids": sorted(a.site_ids) if a.site_ids is not None else None,
        "roles": [r.code for r in user.roles], "permissions": sorted(a.permissions),
        "must_change_password": user.must_change_password, "default_company_id": user.default_company_id,
    }


def change_password(db: Session, actor: Actor, current: str, new: str) -> None:
    user = db.get(User, actor.id)
    if not verify_password(current, user.password_hash):
        raise ValidationFailed("Current password is incorrect")
    problems = validate_password_strength(new)
    if problems:
        raise ValidationFailed("Password must contain " + ", ".join(problems))
    user.password_hash = hash_password(new)
    user.must_change_password = False
    user.token_version += 1
    record(db, actor, "auth.password_changed", "user", user.id)


def logout_all(db: Session, actor: Actor) -> None:
    user = db.get(User, actor.id)
    user.token_version += 1
    record(db, actor, "auth.logout_all", "user", user.id)


def save_user(db: Session, actor: Actor, data: dict, user_id: int | None = None) -> User:
    actor.require("admin.users")
    if user_id:
        user = db.get(User, user_id)
        if user is None:
            raise NotFound("User not found")
        old = {"roles": [r.code for r in user.roles], "is_active": user.is_active, "all_sites": user.all_sites,
               "sites": [s.site_id for s in user.site_access]}
    else:
        if db.scalar(select(User.id).where(func.lower(User.username) == data["username"].lower())):
            raise Conflict("Username already exists")
        if not data.get("password"):
            raise ValidationFailed("Password is required for a new user")
        user = User(username=data["username"], full_name=data["full_name"], password_hash="!")
        db.add(user)
        old = None
    for f in ("full_name", "email", "is_active", "all_sites", "default_company_id"):
        if f in data and data[f] is not None:
            setattr(user, f, data[f])
    if data.get("password"):
        problems = validate_password_strength(data["password"])
        if problems:
            raise ValidationFailed("Password must contain " + ", ".join(problems))
        user.password_hash = hash_password(data["password"])
        user.must_change_password = bool(data.get("must_change_password", True))
        user.token_version = (user.token_version or 1) + 1
    if "role_codes" in data and data["role_codes"] is not None:
        roles = db.scalars(select(Role).where(Role.code.in_(data["role_codes"]))).all()
        if len(roles) != len(set(data["role_codes"])):
            raise ValidationFailed("Unknown role code")
        user.roles = list(roles)
    if "site_ids" in data and data["site_ids"] is not None:
        user.site_access = [UserSiteAccess(site_id=sid) for sid in data["site_ids"]]
    if user.id == actor.id and data.get("is_active") is False:
        raise ValidationFailed("You cannot deactivate yourself")
    db.flush()
    record(db, actor, "user.update" if old else "user.create", "user", user.id, old,
           {"username": user.username, "roles": [r.code for r in user.roles], "is_active": user.is_active,
            "all_sites": user.all_sites, "sites": [s.site_id for s in user.site_access]})
    return user
