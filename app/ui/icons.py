"""Inline SVG icon set.  No external image files are required."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui.styles import TEXT_MUTED, TEXT_SECONDARY

_STROKE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)
_FILLED = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="{color}" stroke="{color}" stroke-width="1.2" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

_ICONS: dict[str, tuple[str, bool]] = {
    "search": ('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/>', False),
    "plus": ('<path d="M12 5v14M5 12h14"/>', False),
    "settings": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 '
        '1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06'
        'a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.88 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09'
        'a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06'
        'a1.7 1.7 0 0 0 1.88.34h.01a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 '
        '1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.88v.01'
        'a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/>'
    , False),
    "sliders": (
        '<path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h10M18 18h2"/>'
        '<circle cx="16" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>'
    , False),
    "lock": ('<rect x="4" y="10" width="16" height="11" rx="2.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>', False),
    "unlock": (
        '<rect x="4" y="10" width="16" height="11" rx="2.5"/><path d="M8 10V7a4 4 0 0 1 7.4-2.1"/>'
    , False),
    "search_off": ('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6M8 11h6"/>', False),
    "eye": ('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>', False),
    "eye-off": (
        '<path d="M17.94 17.94A10.5 10.5 0 0 1 12 19c-6.5 0-10-7-10-7a18.5 18.5 0 0 1 5.06-5.94'
        'M9.9 4.24A9.8 9.8 0 0 1 12 4c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.16 3.19"/>'
        '<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/>'
    , False),
    "copy": (
        '<rect x="9" y="9" width="12" height="12" rx="2"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'
    , False),
    "edit": ('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>', False),
    "trash": (
        '<path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/>'
        '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>'
    , False),
    "star": (
        '<path d="M12 2.6l2.95 5.98 6.6.96-4.78 4.66 1.13 6.58L12 17.68l-5.9 3.1 1.13-6.58L2.45 9.54l6.6-.96z"/>'
    , False),
    "star-filled": (
        '<path d="M12 2.6l2.95 5.98 6.6.96-4.78 4.66 1.13 6.58L12 17.68l-5.9 3.1 1.13-6.58L2.45 9.54l6.6-.96z"/>'
    , True),
    "grid": (
        '<rect x="3" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="3" width="7" height="7" rx="1.6"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1.6"/><rect x="14" y="14" width="7" height="7" rx="1.6"/>'
    , False),
    "users": (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    , False),
    "gamepad": (
        '<rect x="2" y="6" width="20" height="12" rx="4"/><path d="M6 12h4M8 10v4"/>'
        '<circle cx="15" cy="11" r="1.1"/><circle cx="18" cy="13" r="1.1"/>'
    , False),
    "briefcase": (
        '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<path d="M2 13h20"/>'
    , False),
    "mail": ('<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 7l10 7 10-7"/>', False),
    "banks": ('<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h4"/>', False),
    "key": (
        '<circle cx="7.5" cy="15.5" r="3.5"/><path d="M10.2 12.8L20 3M17 6l2 2M14 9l2 2"/>'
    , False),
    "shield": (
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9.5 11.5l1.8 1.8 3.4-3.6"/>'
    , False),
    "download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/>'
        '<path d="M12 15V3"/>'
    , False),
    "upload": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/>'
        '<path d="M12 3v12"/>'
    , False),
    "check": ('<path d="M20 6L9 17l-5-5"/>', False),
    "x": ('<path d="M18 6L6 18M6 6l12 12"/>', False),
    "minus": ('<path d="M5 12h14"/>', False),
    "square": ('<rect x="5" y="5" width="14" height="14" rx="2"/>', False),
    "restore": (
        '<rect x="3" y="8" width="13" height="13" rx="2"/>'
        '<path d="M8 8V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-3"/>'
    , False),
    "chevron-down": ('<path d="M6 9l6 6 6-6"/>', False),
    "globe": (
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'
        '<path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"/>'
    , False),
    "info": ('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>', False),
    "warning": ('<path d="M12 3l10 18H2z"/><path d="M12 9v5M12 17h.01"/>', False),
    "clock": ('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', False),
    "calendar": (
        '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>'
    , False),
    "database": (
        '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>'
        '<path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'
    , False),
    "refresh": ('<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>', False),
    "logo": (
        '<path d="M12 2l8 3v7c0 5.3-3.4 8.9-8 10-4.6-1.1-8-4.7-8-10V5z"/>'
        '<circle cx="12" cy="11" r="2.2"/><path d="M12 13.2V16"/>'
    , False),
    "folder": (
        '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
    , False),
}

CATEGORY_ICONS = {
    "social": "users",
    "games": "gamepad",
    "work": "briefcase",
    "email": "mail",
    "banks": "banks",
    "other": "grid",
}

_cache: dict[tuple[str, str, int], QIcon] = {}


def category_icon_id(category_id: str) -> str:
    return CATEGORY_ICONS.get(category_id, "folder")


def svg_bytes(name: str, color: str = TEXT_SECONDARY) -> QByteArray:
    body, filled = _ICONS.get(name, _ICONS["info"])
    template = _FILLED if filled else _STROKE
    return QByteArray(template.format(color=color, body=body).encode("utf-8"))


def icon(name: str, color: str = TEXT_SECONDARY, size: int = 20) -> QIcon:
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    scale = 2
    renderer = QSvgRenderer(svg_bytes(name, color))
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    result = QIcon(pixmap)
    _cache[key] = result
    return result


def pixmap(name: str, color: str = TEXT_MUTED, size: int = 18) -> QPixmap:
    return icon(name, color, size).pixmap(size, size)


def avatar_icon(title: str) -> str:
    """Return the first meaningful letter of a record title."""

    clean = (title or "").strip()
    return clean[0].upper() if clean else "?"
