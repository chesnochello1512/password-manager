"""Small helpers for running expensive work (Argon2id) off the UI thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _TaskSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self._function = function
        self.signals = _TaskSignals()

    def run(self) -> None:  # pragma: no cover - thread body
        try:
            result = self._function()
        except Exception as exc:  # noqa: BLE001 - forwarded to the UI thread
            self.signals.failed.emit(exc)
        else:
            self.signals.succeeded.emit(result)


class TaskRunner(QObject):
    """Runs one background task at a time and reports on the UI thread."""

    succeeded = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._task: _Task | None = None
        self._pool = QThreadPool.globalInstance()

    @property
    def busy(self) -> bool:
        return self._busy

    def run(self, function: Callable[[], Any]) -> bool:
        if self._busy:
            return False
        self._busy = True
        task = _Task(function)
        task.signals.succeeded.connect(self._on_success)
        task.signals.failed.connect(self._on_failure)
        self._task = task
        self._pool.start(task)
        return True

    def _on_success(self, result: object) -> None:
        self._finish()
        self.succeeded.emit(result)

    def _on_failure(self, error: object) -> None:
        self._finish()
        self.failed.emit(error)

    def _finish(self) -> None:
        self._busy = False
        self._task = None
        self.finished.emit()
