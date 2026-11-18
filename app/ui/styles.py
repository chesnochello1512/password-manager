"""Dark visual theme: palette, generated QSS assets and stylesheet."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication

BACKGROUND = "#0E1015"
BACKGROUND_ALT = "#11141B"
SURFACE = "#161A22"
SURFACE_HOVER = "#1C212B"
SURFACE_ACTIVE = "#222937"
BORDER = "#262C38"
BORDER_STRONG = "#333B4B"
TEXT = "#E9EDF5"
TEXT_SECONDARY = "#9DA8BC"
TEXT_MUTED = "#6F7B91"
ACCENT = "#6D8BFF"
ACCENT_HOVER = "#85A2FF"
ACCENT_PRESSED = "#5B79E8"
ACCENT_TEXT = "#0A1020"
SUCCESS = "#3ED598"
DANGER = "#FF6B7A"
WARNING = "#F2B84B"
CHIP = "#1F2740"

AVATAR_COLORS = (
    ("#2B3A63", "#9DB6FF"),
    ("#1F3D34", "#7FE0B4"),
    ("#432B3F", "#F0A6D8"),
    ("#44361F", "#F0C97F"),
    ("#2C3650", "#A9C3FF"),
    ("#3E2930", "#FFA9B4"),
)

_QSS = """
* {
    font-family: "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
    outline: none;
}
QWidget {
    color: #E9EDF5;
    font-size: 13px;
}
QMainWindow, QDialog {
    background: transparent;
}
QLabel {
    background: transparent;
}
QLabel#Caption {
    color: #9DA8BC;
    font-size: 12px;
    font-weight: 600;
}
QLabel#Muted {
    color: #6F7B91;
    font-size: 12px;
}
QLabel#MutedSmall {
    color: #6F7B91;
    font-size: 11px;
}
QLabel#Heading {
    color: #E9EDF5;
    font-size: 24px;
    font-weight: 600;
}
QLabel#DialogTitle {
    color: #E9EDF5;
    font-size: 16px;
    font-weight: 600;
}
QLabel#AppName {
    color: #E9EDF5;
    font-size: 14px;
    font-weight: 600;
}
QLabel#PaneTitle {
    color: #E9EDF5;
    font-size: 18px;
    font-weight: 600;
}
QLabel#CardTitle {
    color: #E9EDF5;
    font-size: 13px;
    font-weight: 600;
}
QLabel#CardSubtitle {
    color: #8B97AB;
    font-size: 11px;
}
QLabel#Error {
    color: #FF6B7A;
    font-size: 12px;
}
QLabel#Success {
    color: #3ED598;
    font-size: 12px;
}
QLabel#FieldCaption {
    color: #7C879C;
    font-size: 11px;
    font-weight: 600;
}
QLabel#FieldValue {
    color: #E9EDF5;
    font-size: 13px;
}
QLabel#SectionTitle {
    color: #B9C3D4;
    font-size: 12px;
    font-weight: 600;
}
QLabel#Chip {
    background: rgba(109, 139, 255, 0.14);
    color: #9DB2FF;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#CountBadge {
    background: rgba(255, 255, 255, 0.06);
    color: #8B97AB;
    border-radius: 8px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
}
QLabel#IconBadge {
    background: rgba(109, 139, 255, 0.14);
    border-radius: 12px;
    padding: 5px;
}

QFrame#AppRoot {
    background: #0E1015;
    border: 1px solid #262C38;
    border-radius: 14px;
}
QFrame#AppRoot[maximized="true"] {
    border: none;
    border-radius: 0;
}
QFrame#AppRoot[maximized="true"] QFrame#TitleBar {
    border-top-left-radius: 0;
    border-top-right-radius: 0;
}
QFrame#LoginSurface {
    background: #131720;
    border: 1px solid #272E3C;
    border-radius: 18px;
}
QFrame#DialogSurface {
    background: #151922;
    border: 1px solid #2A3140;
    border-radius: 16px;
}
QFrame#TitleBar {
    background: #11141B;
    border-top-left-radius: 13px;
    border-top-right-radius: 13px;
    border-bottom: 1px solid #222834;
}
QFrame#Sidebar {
    background: #11141B;
    border-right: 1px solid #222834;
}
QFrame#ListPane {
    background: #0E1015;
}
QFrame#DetailPane {
    background: #0E1015;
}
QFrame#Divider {
    background: #222834;
}
QFrame#Card {
    background: #141821;
    border: 1px solid #222937;
    border-radius: 12px;
}
QFrame#RecordCard {
    background: #141821;
    border: 1px solid transparent;
    border-radius: 11px;
}
QFrame#RecordCard:hover {
    background: #1A1F2A;
    border-color: #2B3342;
}
QFrame#RecordCard[selected="true"] {
    background: #202839;
    border-color: #45598F;
}
QFrame#FieldRow {
    background: #141821;
    border: 1px solid #222937;
    border-radius: 10px;
}
QFrame#SectionCard {
    background: #141821;
    border: 1px solid #222937;
    border-radius: 12px;
}

QFrame#SidebarItem {
    background: transparent;
    border-radius: 9px;
}
QFrame#SidebarItem[hovered="true"] {
    background: #181D26;
}
QFrame#SidebarItem[selected="true"] {
    background: rgba(109, 139, 255, 0.13);
}
QLabel#SidebarText {
    color: #B6C0D2;
    font-size: 13px;
}
QLabel#SidebarText[selected="true"] {
    color: #9DB2FF;
    font-weight: 600;
}
QLabel#SidebarSection {
    color: #5F6B80;
    font-size: 10px;
    font-weight: 700;
    padding-left: 10px;
}

QPushButton {
    background: #1A1F29;
    color: #E9EDF5;
    border: 1px solid #2B3342;
    border-radius: 9px;
    padding: 8px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background: #212734;
    border-color: #384153;
}
QPushButton:pressed {
    background: #171C25;
}
QPushButton:disabled {
    color: #5C677B;
    background: #161A22;
    border-color: #232936;
}
QPushButton#Primary {
    background: #6D8BFF;
    color: #0A1020;
    border: 1px solid #6D8BFF;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background: #85A2FF;
    border-color: #85A2FF;
}
QPushButton#Primary:pressed {
    background: #5B79E8;
}
QPushButton#Primary:disabled {
    background: #2D3A63;
    border-color: #2D3A63;
    color: #7F8AA3;
}
QPushButton#Danger {
    background: rgba(255, 107, 122, 0.10);
    color: #FF8A96;
    border: 1px solid rgba(255, 107, 122, 0.30);
}
QPushButton#Danger:hover {
    background: rgba(255, 107, 122, 0.16);
    border-color: rgba(255, 107, 122, 0.55);
}
QPushButton#Danger:disabled {
    color: #7A4A52;
    border-color: #3A2A30;
    background: transparent;
}
QPushButton#Ghost {
    background: transparent;
    border: 1px solid transparent;
    color: #B6C0D2;
}
QPushButton#Ghost:hover {
    background: #1A1F29;
    color: #FFFFFF;
}
QPushButton#IconButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 5px;
}
QPushButton#IconButton:hover {
    background: #1D232E;
}
QPushButton#IconButton:pressed {
    background: #171C25;
}
QPushButton#WindowButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px;
}
QPushButton#WindowButton:hover {
    background: #212734;
}
QPushButton#CloseWindow {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px;
}
QPushButton#CloseWindow:hover {
    background: #C2404F;
}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
    background: #10141B;
    color: #E9EDF5;
    border: 1px solid #2A3240;
    border-radius: 9px;
    padding: 9px 12px;
    selection-background-color: #4D67CC;
    selection-color: #FFFFFF;
}
QLineEdit:hover, QTextEdit:hover, QSpinBox:hover {
    border-color: #364054;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
    border: 1px solid #6D8BFF;
    background: #121722;
}
QLineEdit:disabled, QTextEdit:disabled {
    color: #6F7B91;
    background: #141821;
}
QLineEdit#SearchInput {
    padding-left: 10px;
    border-radius: 10px;
    background: #171C25;
    border: 1px solid #252C39;
}
QLineEdit#SearchInput:focus {
    background: #181E29;
    border-color: #3C4C82;
}
QLineEdit#PasswordDisplay {
    font-size: 15px;
    font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace;
    letter-spacing: 1px;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 18px;
    border: none;
    background: transparent;
}
QSpinBox::up-arrow {
    image: url(__CHEVRON_UP__);
    width: 9px;
    height: 9px;
}
QSpinBox::down-arrow {
    image: url(__CHEVRON_DOWN__);
    width: 9px;
    height: 9px;
}

QTextEdit#NotesInput {
    padding: 10px 12px;
}

QCheckBox {
    spacing: 9px;
    color: #C7D0DF;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #394355;
    background: #10141B;
}
QCheckBox::indicator:hover {
    border-color: #6D8BFF;
}
QCheckBox::indicator:checked {
    background: #6D8BFF;
    border-color: #6D8BFF;
    image: url(__CHECK__);
}

QComboBox {
    background: #10141B;
    color: #E9EDF5;
    border: 1px solid #2A3240;
    border-radius: 9px;
    padding: 8px 34px 8px 12px;
    min-height: 18px;
}
QComboBox:hover {
    border-color: #364054;
}
QComboBox:focus {
    border-color: #6D8BFF;
}
QComboBox::drop-down {
    width: 30px;
    border: none;
}
QComboBox::down-arrow {
    image: url(__CHEVRON_DOWN__);
    width: 12px;
    height: 12px;
}
QComboBox QAbstractItemView {
    background: #171C25;
    color: #E9EDF5;
    border: 1px solid #2F3848;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #263047;
    selection-color: #FFFFFF;
    outline: none;
}

QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 3px 2px;
}
QScrollBar::handle:vertical {
    background: #2C3444;
    min-height: 30px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #3A455A;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px 3px;
}
QScrollBar::handle:horizontal {
    background: #2C3444;
    min-width: 30px;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #252C39;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #6D8BFF;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: #E9EDF5;
    border: 2px solid #6D8BFF;
}
QSlider::handle:horizontal:hover {
    background: #FFFFFF;
}

QProgressBar {
    background: #1A1F29;
    border: none;
    border-radius: 2px;
    max-height: 4px;
}
QProgressBar::chunk {
    background: #6D8BFF;
    border-radius: 2px;
}

QToolTip {
    background-color: #202633;
    color: #E9EDF5;
    border: 1px solid #343D4F;
    border-radius: 6px;
    padding: 6px 8px;
}

QFrame#Toast {
    background: #1E2532;
    border: 1px solid #354055;
    border-radius: 10px;
}
QFrame#Toast[kind="success"] {
    border-color: rgba(62, 213, 152, 0.45);
}
QFrame#Toast[kind="error"] {
    border-color: rgba(255, 107, 122, 0.55);
}
QFrame#Toast[kind="warning"] {
    border-color: rgba(242, 184, 75, 0.55);
}
QLabel#ToastText {
    color: #DDE4F0;
    font-size: 12px;
}

QFrame#DropShadowFrame {
    background: transparent;
}
QFrame#CategoryRow {
    background: #12161E;
    border: 1px solid #232A37;
    border-radius: 9px;
}
"""


def _asset_dir() -> Path:
    # Use a fixed, short location without application-name spaces.  Paths are
    # additionally quoted in QSS so user profiles containing spaces work.
    path = Path(tempfile.gettempdir()) / "password-manager-theme-v1"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path(tempfile.gettempdir())
    return path


def _save_check(path: Path) -> None:
    image = QImage(20, 20, QImage.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(ACCENT_TEXT), 2.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(
        QPolygonF([QPointF(5, 10.5), QPointF(8.5, 14), QPointF(15, 6.5)])
    )
    painter.end()
    image.save(str(path), "PNG")


def _save_chevron(path: Path, color: str, up: bool = False) -> None:
    image = QImage(16, 16, QImage.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if up:
        points = [QPointF(3.5, 10), QPointF(8, 5.5), QPointF(12.5, 10)]
    else:
        points = [QPointF(3.5, 6), QPointF(8, 10.5), QPointF(12.5, 6)]
    painter.drawPolyline(QPolygonF(points))
    painter.end()
    image.save(str(path), "PNG")


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    assets = _asset_dir()
    check = assets / "check.png"
    chevron_down = assets / "chevron-down.png"
    chevron_up = assets / "chevron-up.png"
    try:
        if not check.exists():
            _save_check(check)
        if not chevron_down.exists():
            _save_chevron(chevron_down, TEXT_SECONDARY)
        if not chevron_up.exists():
            _save_chevron(chevron_up, TEXT_SECONDARY, up=True)
    except OSError:
        pass

    def url(path: Path) -> str:
        return '"' + str(path).replace("\\", "/") + '"'

    qss = (
        _QSS.replace("__CHECK__", url(check))
        .replace("__CHEVRON_DOWN__", url(chevron_down))
        .replace("__CHEVRON_UP__", url(chevron_up))
    )
    app.setStyleSheet(qss)
