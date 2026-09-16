"""KubeDeck SVG icon helpers.

Icons are stored under assets/icons and rendered with Qt's SVG renderer.
The helpers below preserve the public API used by the existing application.
"""

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QPushButton

try:
    from themes import T
except Exception:
    T = {
        "TEXT_PRIMARY": "#E8EAF0",
        "TEXT_DIM": "#A7ACB8",
        "ACCENT": "#A855F7",
    }

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def _to_qcolor(value, fallback="#E8EAF0") -> QColor:
    """Convert a color string/QColor into a valid QColor."""
    if isinstance(value, QColor):
        return QColor(value)

    color = QColor(str(value if value is not None else fallback))
    if not color.isValid():
        color = QColor(fallback)

    return color


def icon_path(name: str) -> str:
    """Return the absolute path to an SVG icon."""
    name = str(name or "").strip()

    if not name:
        return ""

    if name.lower().endswith(".svg"):
        filename = name
    else:
        filename = f"{name}.svg"

    return str(ICON_DIR / filename)


def icon(
    name: str,
    color: Optional[str] = None,
    size: int = 18,
) -> QIcon:
    """Load and optionally tint an SVG icon."""
    size = max(1, int(size))
    path = icon_path(name)

    if not path or not Path(path).is_file():
        return QIcon()

    renderer = QSvgRenderer(path)

    if not renderer.isValid():
        return QIcon()

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)

    try:
        renderer.render(painter)

        if color is not None:
            painter.setCompositionMode(
                QPainter.CompositionMode_SourceIn
            )
            painter.fillRect(
                pixmap.rect(),
                _to_qcolor(color),
            )
    finally:
        painter.end()

    result = QIcon()
    result.addPixmap(pixmap)
    return result


def set_icon(
    widget,
    name: str,
    color: Optional[str] = None,
    size: int = 18,
) -> None:
    """Set an SVG icon on any Qt widget supporting setIcon()."""
    if widget is None:
        return

    qt_icon = icon(
        name,
        color=color,
        size=size,
    )

    widget.setIcon(qt_icon)

    if hasattr(widget, "setIconSize"):
        widget.setIconSize(QSize(size, size))


def icon_pixmap(
    name: str,
    color: Optional[str] = None,
    size: int = 18,
) -> QPixmap:
    """Return a rendered SVG icon as a QPixmap."""
    qt_icon = icon(
        name,
        color=color,
        size=size,
    )

    return qt_icon.pixmap(QSize(size, size))


# ============================================================
# Semantic label mapping
# ============================================================

LABEL_TO_ICON = {
    # Main UI
    "dashboard": "dashboard",
    "home": "home",
    "file manager": "folder",
    "files": "file",
    "settings": "settings",
    "terminal": "terminal",
    "list view": "list",
    "grid view": "grid",
    "security": "security",

    # Infrastructure
    "kubernetes": "kubernetes",
    "pods": "pods",
    "deployments": "deployment",
    "statefulsets": "statefulsets",
    "daemonsets": "daemonsets",
    "hpa": "hpa",
    "services": "services",
    "service": "service",
    "ingress": "ingress",
    "jobs": "jobs",
    "cronjobs": "jobs",
    "storage": "storage",
    "configmaps": "config",
    "secrets": "lock",
    "events": "events",
    "tunnels": "tunnel",
    "tunnel": "tunnel",
    "ftp": "ftp",
    "ftps": "ftp",
    "instance": "instance",
    "server": "server",
    "database": "database",
    "network": "network",
    "docker": "docker",
    "cloud": "cloud",
    "monitor": "monitor",
    "analytics": "chart",

    # Connection
    "connect": "connect",
    "disconnect": "disconnect",
    "switch user": "switch_user",
    "exit sudo": "lock",

    # Actions
    "search": "search",
    "filter": "search",
    "describe": "describe",
    "logs": "logs",
    "log": "log",
    "exec": "exec",
    "exec shell": "exec",
    "delete": "delete",
    "remove": "delete",
    "new folder": "plus",
    "add service": "plus",
    "add a new service": "plus",
    "save": "save",
    "save to vm": "save",
    "refresh": "refresh",
    "clear": "clear",
    "view": "eye",
    "open": "folder",
    "upload": "upload",
    "download": "download",
    "kill port": "stop",
    "select all": "check",

    # Voice / security
    "voice": "mic",
    "speak": "volume_high",
    "mute": "volume_high",
    "locked": "lock",
    "your session is protected": "shield",
    "pin": "key",
    "google web speech": "mic",

    # AI
    "ai": "ai",
    "ops mind": "ai",
    "run with ai": "ai",
    "analyze with ai": "ai",
    "ai troubleshooting": "ai",
    "explain": "ai",

    # File-system locations
    "root": "folder",
    "tmp": "folder",
    "etc": "folder",
    "var": "folder",
    "opt": "folder",
    "srv": "folder",
    "usr/local": "folder",
    "applications": "folder",
    "library": "folder",
    "users": "user",
    "volumes": "database",
    "claims (pvc)": "file",
    "volumes (pv)": "database",

    # Status
    "warnings only": "warning",
}

_LABEL_KEYS = sorted(LABEL_TO_ICON, key=len, reverse=True)


def split_icon_text(text: str):
    """Return (icon_name, cleaned_text) using semantic label matching."""
    if not isinstance(text, str):
        return None, text

    cleaned = text.strip()

    if not cleaned:
        return None, text

    lower = cleaned.lower()

    for key in _LABEL_KEYS:
        if (
            lower == key
            or lower.startswith(key + " ")
            or lower.startswith(key + "…")
            or lower.startswith(key + " (")
            or lower.startswith(key + ":")
        ):
            return LABEL_TO_ICON[key], cleaned

    # Fallback for short labels containing a known semantic phrase.
    for key in _LABEL_KEYS:
        if key in lower and len(cleaned) <= 60:
            return LABEL_TO_ICON[key], cleaned

    return None, cleaned


def apply_text_icon(
    widget,
    text: str,
    size: int = 16,
    color: Optional[str] = None,
):
    """Set widget text and attach a matching SVG icon."""
    name, cleaned = split_icon_text(text)

    if hasattr(widget, "setText"):
        widget.setText(cleaned)

    if name:
        set_icon(
            widget,
            name,
            color=color,
            size=size,
        )

    return cleaned


def icon_button(
    text: str,
    parent=None,
    size: int = 16,
):
    """Create a QPushButton with a semantic SVG icon."""
    button = QPushButton(parent) if parent is not None else QPushButton()

    apply_text_icon(
        button,
        text,
        size=size,
    )

    return button


def add_icon_tab(
    tab_widget,
    widget,
    text: str,
    size: int = 16,
):
    """Add a tab with an SVG icon when a semantic icon exists."""
    name, cleaned = split_icon_text(text)

    if name:
        return tab_widget.addTab(
            widget,
            icon(name, size=size),
            cleaned,
        )

    return tab_widget.addTab(
        widget,
        cleaned,
    )


# Compatibility aliases
get_icon = icon
load_icon = icon


__all__ = [
    "ICON_DIR",
    "LABEL_TO_ICON",
    "icon_path",
    "icon",
    "set_icon",
    "icon_pixmap",
    "split_icon_text",
    "apply_text_icon",
    "icon_button",
    "add_icon_tab",
    "get_icon",
    "load_icon",
]
