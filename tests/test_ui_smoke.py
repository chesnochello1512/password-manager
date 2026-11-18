from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from app.database.database import Database  # noqa: E402
from app.security.key_manager import KeyManager  # noqa: E402
from app.services.backup_service import BackupService  # noqa: E402
from app.services.clipboard_service import ClipboardService  # noqa: E402
from app.ui.category_dialog import CategoryDialog  # noqa: E402
from app.ui.generator_dialog import GeneratorDialog  # noqa: E402
from app.ui.login_window import LoginWindow  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.password_dialog import PasswordDialog  # noqa: E402
from app.ui.settings_window import ChangePasswordDialog, SettingsPage  # noqa: E402
from app.ui.styles import apply_theme  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Password Manager Tests")
    apply_theme(app)
    yield app


def wait_until(predicate, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture()
def main_window(qapp, vault):
    service = vault.service
    service.create_record(
        title="GitHub", username="octocat", password="GitHub-Secret!42",
        url="https://github.com", category_id="work", notes="Developer account", favorite=True,
    )
    service.create_record(
        title="Steam", username="player", password="Steam-Secret!7",
        url="https://store.steampowered.com", category_id="games",
    )
    service.create_record(
        title="Telegram", username="@user", password="Telegram-Secret!9",
        url="https://web.telegram.org", category_id="social",
    )
    clipboard = ClipboardService(QGuiApplication.clipboard())
    window = MainWindow(
        vault.path, vault.keys, service, BackupService(vault.db), clipboard
    )
    window.show()
    qapp.processEvents()
    yield window, service, clipboard
    window.force_close()
    qapp.processEvents()


def test_main_window_lists_records(main_window) -> None:
    window, service, _ = main_window
    assert len(window._cards) == 3
    assert window.list_title.text() == "Все записи"
    window._filter = "favorites"
    window.refresh()
    assert len(window._cards) == 1
    window._filter = "work"
    window.refresh()
    assert len(window._cards) == 1
    window._filter = "all"
    window.refresh()
    window.search.setText("steam")
    window.refresh()
    assert len(window._cards) == 1


def test_reveal_and_copy_password(main_window) -> None:
    window, service, clipboard = main_window
    record = service.list_records(search="GitHub")[0]
    window._select_record(record.id)
    assert window._current_record is not None
    assert "•" in window.password_label.text()
    window._toggle_password()
    assert window.password_label.text() == "GitHub-Secret!42"
    window._toggle_password()
    assert "•" in window.password_label.text()

    window._copy_password()
    assert QGuiApplication.clipboard().text() == "GitHub-Secret!42"
    clipboard.clear_if_ours()
    assert QGuiApplication.clipboard().text() == ""


def test_password_dialog_defaults_and_validation(qapp, vault) -> None:
    saved: list[dict[str, object]] = []
    dialog = PasswordDialog(
        vault.service,
        ClipboardService(QGuiApplication.clipboard()),
        saved.append,
        parent=None,
    )
    assert dialog.category_combo.currentData() == "other"
    dialog._save()
    assert not dialog.result() == QDialog.DialogCode.Accepted
    assert not dialog.error.isHidden()

    dialog.title_input.setText("Example")
    dialog.password_input.setText("Example-Secret!1")
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert saved and saved[0]["title"] == "Example"
    assert saved[0]["password"] == "Example-Secret!1"
    dialog.close()


def test_category_dialog_adds_category(qapp, vault) -> None:
    dialog = CategoryDialog(vault.service)
    dialog.new_name.setText("Облачные сервисы")
    dialog._add()
    assert vault.service.settings.category_name(
        next(
            category.id
            for category in vault.service.settings.categories
            if category.name == "Облачные сервисы"
        )
    ) == "Облачные сервисы"
    dialog.close()


def test_generator_dialog(qapp) -> None:
    clipboard = ClipboardService(QGuiApplication.clipboard())
    dialog = GeneratorDialog(clipboard, clear_after=30, select_mode=True)
    assert len(dialog.preview.text()) == 20
    dialog.length_spin.setValue(32)
    assert len(dialog.preview.text()) == 32
    dialog._copy()
    assert QGuiApplication.clipboard().text() == dialog.preview.text()
    clipboard.clear_if_ours()
    dialog.close()


def test_settings_page_updates_services(qapp, vault) -> None:
    clipboard = ClipboardService(QGuiApplication.clipboard())
    page = SettingsPage(
        vault.service,
        BackupService(vault.db),
        vault.keys,
        clipboard,
        vault.path,
    )
    auto_index = page.auto_lock_combo.findData(10)
    page.auto_lock_combo.setCurrentIndex(auto_index)
    assert vault.service.settings.auto_lock_minutes == 10
    clip_index = page.clipboard_combo.findData(60)
    page.clipboard_combo.setCurrentIndex(clip_index)
    assert vault.service.settings.clipboard_clear_seconds == 60
    assert clipboard.clear_after == 60
    page.close()


def test_login_setup_unlock_and_wrong_password(qapp, tmp_path) -> None:
    path = tmp_path / "login-vault.db"
    database = Database(path)
    keys = KeyManager(database)
    authenticated: list[bool] = []

    setup = LoginWindow(True, keys.create_vault, keys.unlock)
    setup.authenticated.connect(lambda: authenticated.append(True))
    setup.show()
    setup.password.setText("Master-Password!42")
    setup.confirm.setText("Master-Password!42")
    setup._submit()
    assert wait_until(lambda: bool(authenticated))
    assert keys.unlocked
    setup.close()

    keys.lock()
    wrong = LoginWindow(False, keys.create_vault, keys.unlock)
    wrong.show()
    wrong.password.setText("Wrong-Password")
    wrong._submit()
    assert wait_until(lambda: not wrong.error.isHidden() and "Неверный" in wrong.error.text())
    assert not keys.unlocked
    wrong.password.setText("Master-Password!42")
    wrong._submit()
    assert wait_until(lambda: keys.unlocked)
    wrong.close()
    keys.close()


def test_master_password_validation(qapp, tmp_path) -> None:
    path = tmp_path / "short-vault.db"
    database = Database(path)
    keys = KeyManager(database)
    login = LoginWindow(True, keys.create_vault, keys.unlock)
    login.password.setText("short")
    login.confirm.setText("short")
    login._submit()
    qapp.processEvents()
    assert not login.error.isHidden()
    assert not keys.unlocked
    assert password_guidance(login.error.text())
    login.close()


def password_guidance(text: str) -> bool:
    return "не менее" in text.lower()


def test_clipboard_clears_only_its_own_secret(qapp) -> None:
    clipboard = ClipboardService(QGuiApplication.clipboard())
    clipboard.copy_secret("Secret-From-App", 30)
    assert QGuiApplication.clipboard().text() == "Secret-From-App"
    assert clipboard.clear_if_ours() is True
    assert QGuiApplication.clipboard().text() == ""

    clipboard.copy_secret("Another-Secret", 30)
    QGuiApplication.clipboard().setText("user content")
    assert clipboard.clear_if_ours() is False
    assert QGuiApplication.clipboard().text() == "user content"
    QGuiApplication.clipboard().clear()


def test_auto_lock_setting_and_timeout(main_window, qapp) -> None:
    window, _, _ = main_window
    fired: list[bool] = []
    window.lock_requested.connect(lambda: fired.append(True))
    window._on_auto_lock_changed(10)
    assert window._autolock.minutes == 10
    window._on_auto_lock_timeout()
    qapp.processEvents()
    assert fired


def test_change_password_dialog_reencrypts(qapp, vault) -> None:
    from app.exceptions import InvalidMasterPasswordError

    dialog = ChangePasswordDialog(vault.keys)
    dialog.current_input.setText(vault.password)
    dialog.new_input.setText("New-Master-Password!99")
    dialog.confirm_input.setText("New-Master-Password!99")
    dialog._submit()
    assert wait_until(
        lambda: dialog.result() == QDialog.DialogCode.Accepted,
        timeout=20.0,
    )
    vault.keys.lock()
    with pytest.raises(InvalidMasterPasswordError):
        vault.keys.unlock(vault.password)
    vault.keys.unlock("New-Master-Password!99")
    assert vault.keys.unlocked
    dialog.close()
