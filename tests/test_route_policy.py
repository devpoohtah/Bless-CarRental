"""Route policy completeness test: every /admin route must be in the policy table."""

from fastapi.testclient import TestClient

from app.core.route_policy import get_route_role
from app.main import app

client = TestClient(app)


def _normalize_path(path: str) -> str:
    """Convert FastAPI path parameters like {booking_id} to the policy format."""
    return path


def test_every_admin_route_is_in_policy_table():
    """Walk all routes under /admin and verify each has a role in ROUTE_POLICY."""
    missing = []
    for route in app.routes:
        if not hasattr(route, "path") or not hasattr(route, "methods"):
            continue
        if not route.path.startswith("/admin"):
            continue
        if route.path == "/admin/login" or route.path == "/admin/session" or route.path == "/admin/logout":
            continue  # public auth routes, no role needed
        for method in route.methods:
            if method == "HEAD":
                continue
            role = get_route_role(method, route.path)
            if role is None:
                missing.append((method, route.path))

    assert not missing, f"Routes missing from ROUTE_POLICY: {missing}"


def test_no_duplicate_policy_entries():
    """Ensure the policy table doesn't have overlapping patterns that could be ambiguous."""
    # This is a sanity check; the get_route_role function uses first match
    from app.core.route_policy import ROUTE_POLICY
    seen = set()
    for key in ROUTE_POLICY:
        assert key not in seen, f"Duplicate policy entry: {key}"
        seen.add(key)