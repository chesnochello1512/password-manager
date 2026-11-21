from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.controller import ApplicationController  # noqa: E402
from app.database.database import Database  # noqa: E402
from app.exceptions import StorageError, VaultReopenError  # noqa: E402
from app.ui.async_utils import TaskRunner  # noqa: E402
from app.ui.settings_window import ChangePasswordDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Password Manager Lifecycle Tests")
    yield app


def wait_until(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class FakeApplication:
    def __init__(self) -> None:
        self.quit_called = False

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture()
def controller(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PM_DATA_DIR", str(tmp_path))
    controller = ApplicationController(qapp)
    controller._create_vault("Master-Password!42")
    controller._on_authenticated()
    assert controller._main is not None
    yield controller
    try:
        qapp.aboutToQuit.disconnect(controller._shutdown)
    except (RuntimeError, TypeError):
        pass
    try:
        controller._dispose_main()
        if controller._login is not None:
            controller._login.close_silently()
            controller._login.deleteLater()
            controller._login = None
        controller._shutdown()
        controller.deleteLater()
        qapp.processEvents()
    except RuntimeError:
        pass


def start_blocked_rekey(controller: ApplicationController) -> tuple[threading.Event, threading.Event]:
    started = threading.Event()
    release = threading.Event()
    original = controller._keys.change_master_password

    def slow_change(current: str, new: str) -> None:
        started.set()
        assert release.wait(15)
        original(current, new)

    assert controller._runner.run(
        lambda: slow_change("Master-Password!42", "New-Master-Password!99")
    )
    assert started.wait(10)
    return started, release


def test_lock_is_deferred_until_rekey_finishes(controller) -> None:
    controller._service.create_record(title="Example", password="secret")
    _, release = start_blocked_rekey(controller)

    controller.lock()

    assert controller._pending_lock is True
    assert controller._keys.unlocked is True
    assert controller._main is not None
    assert controller._main.isHidden() is True

    release.set()
    assert wait_until(
        lambda: controller._pending_lock is False and controller._keys.unlocked is False
    )
    assert controller._main is None
    assert controller._login is not None

    controller._unlock_vault("New-Master-Password!99")
    assert controller._keys.unlocked is True


def test_quit_is_deferred_until_rekey_finishes(controller) -> None:
    fake = FakeApplication()
    controller._app = fake  # type: ignore[assignment]
    _, release = start_blocked_rekey(controller)

    controller._request_quit()

    assert controller._pending_quit is True
    assert fake.quit_called is False
    assert controller._main is not None
    assert controller._main.isHidden() is True

    release.set()
    assert wait_until(lambda: fake.quit_called and controller._pending_quit is False)
    assert controller._keys.unlocked is True


def test_committed_rekey_failure_forces_lock(controller, monkeypatch) -> None:
    original_connect = Database.connect
    vault_path = controller._vault_path

    def failing_connect(self) -> None:
        if self.path == vault_path and self._conn is None:
            raise StorageError("cannot reopen")
        original_connect(self)

    monkeypatch.setattr(Database, "connect", failing_connect)
    assert controller._runner.run(
        lambda: controller._keys.change_master_password(
            "Master-Password!42", "New-Master-Password!99"
        )
    )

    assert wait_until(lambda: controller._keys.unlocked is False)
    assert controller._login is not None
    assert controller._main is None


def test_task_runner_reports_result_before_finished(qapp) -> None:
    runner = TaskRunner()
    events: list[str] = []
    runner.succeeded.connect(lambda _result: events.append("succeeded"))
    runner.finished.connect(lambda: events.append("finished"))

    assert runner.run(lambda: 42)
    assert wait_until(lambda: events == ["succeeded", "finished"], timeout=5.0)
    runner.shutdown()


def test_change_password_dialog_cannot_be_closed_while_rekeying(qapp, vault) -> None:
    runner = TaskRunner()
    started = threading.Event()
    release = threading.Event()
    original = vault.keys.change_master_password

    def slow_change(current: str, new: str) -> None:
        started.set()
        assert release.wait(15)
        original(current, new)

    vault.keys.change_master_password = slow_change  # type: ignore[method-assign]
    dialog = ChangePasswordDialog(vault.keys, runner=runner)
    dialog.show()
    dialog.current_input.setText(vault.password)
    dialog.new_input.setText("New-Master-Password!99")
    dialog.confirm_input.setText("New-Master-Password!99")
    dialog._submit()
    assert started.wait(10)
    assert dialog.is_busy is True
    assert dialog.cancel_button.isEnabled() is False
    assert dialog.close_button.isEnabled() is False

    dialog.reject()
    dialog.close()
    assert dialog.isVisible() is True

    dialog.prepare_for_lock()
    assert dialog.current_input.text() == ""
    assert dialog.new_input.text() == ""
    assert dialog.isHidden() is True

    release.set()
    assert wait_until(lambda: runner.busy is False and dialog.lock_requested)
    assert dialog.result() == ChangePasswordDialog.DialogCode.Rejected
    dialog.deleteLater()
    runner.shutdown()


def test_vault_reopen_error_is_reported_after_commit(vault, monkeypatch) -> None:
    original_connect = Database.connect
    vault_path = vault.path
    failing = {"enabled": True}

    def failing_connect(self) -> None:
        if failing["enabled"] and self.path == vault_path and self._conn is None:
            raise StorageError("cannot reopen")
        original_connect(self)

    monkeypatch.setattr(Database, "connect", failing_connect)

    with pytest.raises(VaultReopenError) as error:
        vault.keys.change_master_password(vault.password, "New-Master-Password!99")
    assert getattr(error.value, "committed", False) is True
    failing["enabled"] = False

    # The file has already been replaced, so the new password must work.
    fresh = SimpleNamespace(db=Database(vault.path))
    from app.security.key_manager import KeyManager

    fresh_keys = KeyManager(fresh.db)
    from app.exceptions import InvalidMasterPasswordError

    with pytest.raises(InvalidMasterPasswordError):
        fresh_keys.unlock(vault.password)
    fresh_keys.unlock("New-Master-Password!99")
    assert fresh_keys.unlocked is True
    fresh_keys.close()
