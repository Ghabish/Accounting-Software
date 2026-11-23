"""The acting user with resolved permissions and site scope, passed to every service call."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.exceptions import PermissionDenied


@dataclass(frozen=True)
class Actor:
    user: Any                                  # authentication.models.User (or a stand-in for system jobs)
    permissions: frozenset[str] = field(default_factory=frozenset)
    site_ids: frozenset[int] | None = None     # None = all sites
    role_ids: frozenset[int] = field(default_factory=frozenset)

    @property
    def id(self) -> int | None:
        return getattr(self.user, "id", None)

    @property
    def username(self) -> str:
        return getattr(self.user, "username", "system")

    @property
    def is_superuser(self) -> bool:
        return bool(getattr(self.user, "is_superuser", False))

    def has(self, perm: str) -> bool:
        return self.is_superuser or perm in self.permissions

    def require(self, *perms: str) -> None:
        missing = [p for p in perms if not self.has(p)]
        if missing:
            raise PermissionDenied(f"Missing permission: {', '.join(missing)}", code="missing_permission")

    def can_site(self, site_id: int | None) -> bool:
        return site_id is None or self.site_ids is None or site_id in self.site_ids

    def require_site(self, site_id: int | None) -> None:
        if not self.can_site(site_id):
            raise PermissionDenied("You are not authorised for this site", code="site_denied")


def actor_for(user: Any) -> Actor:
    perms: set[str] = set()
    role_ids: set[int] = set()
    for role in getattr(user, "roles", []) or []:
        role_ids.add(role.id)
        perms.update(p.code for p in role.permissions)
    if getattr(user, "is_superuser", False) or getattr(user, "all_sites", False):
        sites = None
    else:
        sites = frozenset(a.site_id for a in getattr(user, "site_access", []) or [])
    return Actor(user=user, permissions=frozenset(perms), site_ids=sites, role_ids=frozenset(role_ids))
