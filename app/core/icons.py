"""Inline SVG icons for Jinja templates.

Most paths come from Lucide (https://lucide.dev, ISC license). Lucide no longer ships
brand icons, so the Facebook glyph is a plain SVG path in the same stroke style.
Add an icon by pasting its inner SVG markup into ICONS; use it in a template with
{{ icon("name", "size-5") }}.
"""

from markupsafe import Markup, escape

ICONS: dict[str, str] = {
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/> <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "panel-left-close": (
        '<rect width="18" height="18" x="3" y="3" rx="2"/> <path d="M9 3v18"/> <path d="m16 15-3-3 3-3"/>'
    ),
    "panel-left-open": (
        '<rect width="18" height="18" x="3" y="3" rx="2"/> <path d="M9 3v18"/> <path d="m14 9 3 3-3 3"/>'
    ),
    "log-out": (
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/> <path d="m16 17 5-5-5-5"/> <path d="M21 12H9"/>'
    ),
    "calendar": (
        '<path d="M8 2v4"/> <path d="M16 2v4"/> <rect width="18" height="18" x="3" y="4" rx="2"/> <path d="M3 10h18"/>'
    ),
    "clipboard-list": (
        '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/> <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/> <path d="M12 11h4"/> <path d="M12 16h4"/> <path d="M8 11h.01"/> <path d="M8 16h.01"/>'
    ),
    "chevron-left": (
        '<path d="m15 18-6-6 6-6"/>'
    ),
    "chevron-right": (
        '<path d="m9 18 6-6-6-6"/>'
    ),
    "layout-dashboard": (
        '<rect width="7" height="9" x="3" y="3" rx="1"/> <rect width="7" height="5" x="14" y="3" rx="1"/> <rect width="7" height="9" x="14" y="12" rx="1"/> <rect width="7" height="5" x="3" y="16" rx="1"/>'
    ),
    "plus": (
        '<path d="M5 12h14"/> <path d="M12 5v14"/>'
    ),
    "menu": (
        '<path d="M4 5h16"/> <path d="M4 12h16"/> <path d="M4 19h16"/>'
    ),
    "x": (
        '<path d="M18 6 6 18"/> <path d="m6 6 12 12"/>'
    ),
    "phone": (
        '<path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"/>'
    ),
    "map-pin": (
        '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/> <circle cx="12" cy="10" r="3"/>'
    ),
    "mail": (
        '<path d="m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7"/> <rect x="2" y="4" width="20" height="16" rx="2"/>'
    ),
    "message-circle": (
        '<path d="M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719"/>'
    ),
    "arrow-right": (
        '<path d="M5 12h14"/> <path d="m12 5 7 7-7 7"/>'
    ),
    "arrow-up-right": (
        '<path d="M7 7h10v10"/> <path d="M7 17 17 7"/>'
    ),
    "clock": (
        '<circle cx="12" cy="12" r="10"/> <path d="M12 6v6l4 2"/>'
    ),
    "tag": (
        '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/> <circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>'
    ),
    "users": (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/> <path d="M16 3.128a4 4 0 0 1 0 7.744"/> <path d="M22 21v-2a4 4 0 0 0-3-3.87"/> <circle cx="9" cy="7" r="4"/>'
    ),
    "cog": (
        '<path d="M11 10.27 7 3.34"/> <path d="m11 13.73-4 6.93"/> <path d="M12 22v-2"/> <path d="M12 2v2"/> <path d="M14 12h8"/> <path d="m17 20.66-1-1.73"/> <path d="m17 3.34-1 1.73"/> <path d="M2 12h2"/> <path d="m20.66 17-1.73-1"/> <path d="m20.66 7-1.73 1"/> <path d="m3.34 17 1.73-1"/> <path d="m3.34 7 1.73 1"/> <circle cx="12" cy="12" r="2"/> <circle cx="12" cy="12" r="8"/>'
    ),
    "car-front": (
        '<path d="m21 8-2 2-1.5-3.7A2 2 0 0 0 15.646 5H8.4a2 2 0 0 0-1.903 1.257L5 10 3 8"/> <path d="M7 14h.01"/> <path d="M17 14h.01"/> <rect width="18" height="8" x="3" y="10" rx="2"/> <path d="M5 18v2"/> <path d="M19 18v2"/>'
    ),
    "compass": (
        '<circle cx="12" cy="12" r="10"/> <path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z"/>'
    ),
    "tree-palm": (
        '<path d="M13 8c0-2.76-2.46-5-5.5-5S2 5.24 2 8h2l1-1 1 1h4"/> <path d="M13 7.14A5.82 5.82 0 0 1 16.5 6c3.04 0 5.5 2.24 5.5 5h-3l-1-1-1 1h-3"/> <path d="M5.89 9.71c-2.15 2.15-2.3 5.47-.35 7.43l4.24-4.25.7-.7.71-.71 2.12-2.12c-1.95-1.96-5.27-1.8-7.42.35"/> <path d="M11 15.5c.5 2.5-.17 4.5-1 6.5h4c2-5.5-.5-12-1-14"/>'
    ),
    "shield-check": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/> <path d="m9 12 2 2 4-4"/>'
    ),
    "headset": (
        '<path d="M3 11h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Zm0 0a9 9 0 1 1 18 0m0 0v5a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3Z"/> <path d="M21 16v2a4 4 0 0 1-4 4h-5"/>'
    ),
    "wallet": (
        '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/> <path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>'
    ),
    "camera": (
        '<path d="M13.997 4a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7H20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1.997a2 2 0 0 0 1.759-1.048l.489-.904A2 2 0 0 1 10.004 4z"/> <circle cx="12" cy="13" r="3"/>'
    ),
    "star": (
        '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>'
    ),
    "quote": (
        '<path d="M16 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z"/> <path d="M5 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z"/>'
    ),
    "chevron-down": (
        '<path d="m6 9 6 6 6-6"/>'
    ),
    "circle-check": (
        '<circle cx="12" cy="12" r="10"/> <path d="m16 9-5.5 5.5L8 12"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="10"/> <path d="M12 16v-4"/> <path d="M12 8h.01"/>'
    ),
    "route": (
        '<path d="M9 5h8.5a1 1 0 010 7h-11a1 1 0 000 7H15"/> <circle cx="18" cy="19" r="3"/> <circle cx="6" cy="5" r="3"/>'
    ),
    "luggage": (
        '<path d="M6 20a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2"/> <path d="M8 18V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v14"/> <path d="M10 20h4"/> <circle cx="16" cy="20" r="2"/> <circle cx="8" cy="20" r="2"/>'
    ),
    "user": (
        '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/> <circle cx="12" cy="7" r="4"/>'
    ),
    "badge-check": (
        '<path d="M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z"/> <path d="m16 9-5.5 5.5L8 12"/>'
    ),
    "map": (
        '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/> <path d="M15 5.764v15"/> <path d="M9 3.236v15"/>'
    ),
    "facebook": (
        '<path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/>'
    ),
}

_SVG_ATTRS = (
    'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="{width}" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true" focusable="false"'
)


def icon(name: str, css_class: str = "size-5", stroke_width: float = 2) -> Markup:
    """Return an inline, decorative SVG. Unknown names fail loudly instead of rendering blank."""
    try:
        body = ICONS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown icon {name!r}. Add it to app/core/icons.py") from exc
    attrs = _SVG_ATTRS.format(width=stroke_width)
    return Markup(f'<svg class="{escape(css_class)}" {attrs}>{body}</svg>')
