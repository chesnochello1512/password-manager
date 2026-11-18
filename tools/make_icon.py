"""Generate assets/icon.ico and assets/icon.png from the inline SVG logo."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ui.icons import svg_bytes  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#7E99FF"))
    gradient.setColorAt(1.0, QColor("#4C67E0"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    radius = size * 0.23
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    renderer = QSvgRenderer(QByteArray(svg_bytes("logo", "#0B1020")))
    side = size * 0.62
    offset = (size - side) / 2
    renderer.render(painter, QRectF(offset, offset, side, side))
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(buffer.data())


def build_ico(images: dict[int, bytes]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))
    entries = b""
    payload = b""
    offset = 6 + 16 * len(images)
    for size, data in sorted(images.items()):
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", width, height, 0, 0, 1, 32, len(data), offset + len(payload)
        )
        payload += data
    return header + entries + payload


def main() -> int:
    app = QApplication.instance() or QApplication([])
    del app
    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    pngs: dict[int, bytes] = {}
    for size in SIZES:
        pngs[size] = png_bytes(render(size))
    (assets / "icon.png").write_bytes(pngs[256])
    (assets / "icon.ico").write_bytes(build_ico(pngs))
    print("assets/icon.png and assets/icon.ico created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
