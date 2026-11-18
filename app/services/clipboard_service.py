"""Clipboard handling with ownership-aware automatic clearing."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QClipboard, QGuiApplication


class ClipboardService(QObject):
    """Copies text and clears secrets after a timeout.

    Only a SHA-256 digest of the copied secret is retained.  The clipboard is
    cleared exclusively when it still contains that secret.
    """

    copied = Signal(str)
    cleared = Signal()

    def __init__(self, clipboard: QClipboard | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._clipboard = clipboard or QGuiApplication.clipboard()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._clear_if_unchanged)
        self._secret_digest: str | None = None
        self._clear_after = 30

    @property
    def clear_after(self) -> int:
        return self._clear_after

    def set_clear_after(self, seconds: int) -> None:
        self._clear_after = max(0, int(seconds))

    def copy_text(self, text: str) -> None:
        """Copy non-secret text; cancels ownership of any previous secret."""

        self._timer.stop()
        self._secret_digest = None
        self._clipboard.setText(text)
        self.copied.emit(text)

    def copy_secret(self, text: str, clear_after: int | None = None) -> None:
        seconds = self._clear_after if clear_after is None else int(clear_after)
        self._timer.stop()
        self._clipboard.setText(text)
        self._secret_digest = self._digest(text)
        self._clear_after = seconds
        if seconds > 0:
            self._timer.start(seconds * 1000)
        self.copied.emit(text)

    def clear_if_ours(self) -> bool:
        self._timer.stop()
        digest = self._secret_digest
        self._secret_digest = None
        if not digest:
            return False
        if self._digest(self._clipboard.text()) == digest:
            self._clipboard.clear()
            self.cleared.emit()
            return True
        return False

    def _clear_if_unchanged(self) -> None:
        self.clear_if_ours()

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
