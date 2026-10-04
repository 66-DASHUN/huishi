from __future__ import annotations


MANAGEMENT_ROLES = frozenset({"admin", "super_admin", "operator", "support", "viewer"})
ALL_ROLES = MANAGEMENT_ROLES | frozenset({"user"})

ROLE_PERMISSIONS = {
    "admin": frozenset({"*"}),
    "super_admin": frozenset({"*"}),
    "operator": frozenset(
        {
            "admin.view",
            "operations.view",
            "providers.view",
            "providers.update",
            "billing.view",
            "billing.update",
            "packages.view",
            "packages.update",
            "invites.view",
            "invites.update",
            "records.view",
        }
    ),
    "support": frozenset(
        {
            "admin.view",
            "users.view",
            "users.points.adjust",
            "users.login_failures.reset",
            "records.view",
        }
    ),
    "viewer": frozenset(
        {
            "admin.view",
            "operations.view",
            "users.view",
            "records.view",
            "audit.view",
        }
    ),
    "user": frozenset(),
}


def has_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(str(role or "").strip(), frozenset())
    return "*" in permissions or permission in permissions
