"""Inactivity timer used by the auto-lock feature."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class AutoLockService(QObject):
    timeout = Signal()

    def __init__(self, minutes: int = 5, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._minutes = max(0, int(minutes))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.timeout.emit)

    @property
    def minutes(self) -> int:
        return self._minutes

    def set_minutes(self, minutes: int) -> None:
        self._minutes = max(0, int(minutes))
        self.reset()

    def start(self) -> None:
        self.reset()

    def stop(self) -> None:
        self._timer.stop()

    def reset(self) -> None:
        if self._minutes <= 0:
            self._timer.stop()
            return
        self._timer.start(self._minutes * 60 * 1000)

    def is_active(self) -> bool:
        return self._minutes > 0
