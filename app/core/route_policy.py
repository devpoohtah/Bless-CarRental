"""Route policy table: every /admin route + method -> "staff" or "admin".
If a route is missing from this table, the route policy test will fail.
"""

from typing import Literal

Role = Literal["staff", "admin"]

# Route policy: (method, path) -> required role
# Staff can access: dashboard, bookings (list, detail, create, status, payments, calendar, licenses view), cars/tours list, push register
# Admin only: pricing, cars/tours add/edit/delete, license delete

ROUTE_POLICY: dict[tuple[str, str], Role] = {
    # admin.py
    ("GET", "/admin"): "staff",
    ("GET", "/admin/dashboard"): "staff",

    # admin_bookings.py
    ("GET", "/admin/bookings"): "staff",
    ("GET", "/admin/pending-count"): "staff",
    ("GET", "/admin/bookings/new"): "staff",
    ("POST", "/admin/bookings/new"): "staff",
    ("GET", "/admin/bookings/{booking_id}"): "staff",
    ("GET", "/admin/bookings/{booking_id}/license/front"): "staff",
    ("GET", "/admin/bookings/{booking_id}/license/back"): "staff",
    ("GET", "/admin/bookings/{booking_id}/license"): "staff",
    ("POST", "/admin/bookings/{booking_id}/license/delete"): "admin",
    ("POST", "/admin/bookings/{booking_id}/status"): "staff",
    ("POST", "/admin/bookings/{booking_id}/payment"): "staff",
    ("POST", "/admin/bookings/{booking_id}/downpayment"): "staff",
    ("POST", "/admin/bookings/{booking_id}/payment/record"): "staff",
    ("POST", "/admin/bookings/{booking_id}/additional-payment"): "staff",
    ("GET", "/admin/calendar"): "staff",

    # admin_services.py
    ("GET", "/admin/services"): "staff",
    ("GET", "/admin/services/cars"): "staff",
    ("GET", "/admin/services/cars/new"): "admin",
    ("POST", "/admin/services/cars/new"): "admin",
    ("GET", "/admin/services/cars/{car_id}/edit"): "admin",
    ("POST", "/admin/services/cars/{car_id}/edit"): "admin",
    ("POST", "/admin/services/cars/{car_id}/delete"): "admin",
    ("GET", "/admin/services/tours"): "staff",
    ("GET", "/admin/services/tours/new"): "admin",
    ("POST", "/admin/services/tours/new"): "admin",
    ("GET", "/admin/services/tours/{tour_id}/edit"): "admin",
    ("POST", "/admin/services/tours/{tour_id}/edit"): "admin",
    ("POST", "/admin/services/tours/{tour_id}/delete"): "admin",

    # admin_pricing.py
    ("GET", "/admin/pricing"): "admin",
    ("POST", "/admin/pricing"): "admin",

    # admin_push.py
    ("POST", "/admin/push/register"): "staff",
}


def get_route_role(method: str, path: str) -> Role | None:
    """Look up the required role for a route, normalizing path parameters."""
    # Try exact match first
    key = (method, path)
    if key in ROUTE_POLICY:
        return ROUTE_POLICY[key]

    # Try matching with path parameters (e.g., {booking_id} -> any value)
    for (m, p), role in ROUTE_POLICY.items():
        if m != method:
            continue
        # Convert policy path to regex
        import re
        pattern = "^" + re.escape(p).replace(r"\{[^}]+\}", "[^/]+") + "$"
        if re.match(pattern, path):
            return role
    return None