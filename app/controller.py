"""Application flow: setup, unlock, main window, locking and restore."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from app import config
from app.database.database import Database
from app.exceptions import PasswordManagerError, VaultError
from app.security.key_manager import KeyManager
from app.services.backup_service import BackupService
from app.services.clipboard_service import ClipboardService
from app.services.password_service import PasswordService
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow
from app.ui.widgets import MessageDialog, show_toast

logger = logging.getLogger(__name__)


class ApplicationController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._vault_path = config.vault_path()
        self._clipboard = ClipboardService(app.clipboard(), self)
        self._login: LoginWindow | None = None
        self._main: MainWindow | None = None
        self._shutting_down = False
        self._build_services()
        app.aboutToQuit.connect(self._shutdown)

    def _build_services(self) -> None:
        self._db = Database(self._vault_path)
        self._keys = KeyManager(self._db)
        self._service = PasswordService(self._db, self._keys)
        self._backups = BackupService(self._db)

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        if self._vault_path.exists():
            info = Database.inspect_vault(self._vault_path)
            if not info.valid:
                MessageDialog.show_error(
                    None,
                    "Хранилище повреждено",
                    "Не удалось открыть файл хранилища.\n\n"
                    f"{info.message}\n\n"
                    "Файл расположен здесь:\n"
                    f"{self._vault_path}\n\n"
                    "Восстановите его из резервной копии или обратитесь к сохранённой копии данных.",
                )
                self._app.quit()
                return
            self._show_login(setup=False)
        else:
            self._show_login(setup=True)

    def _show_login(self, setup: bool, notice: str = "") -> None:
        self._dispose_main()
        if self._login is not None:
            try:
                self._login.close_silently()
                self._login.deleteLater()
            except RuntimeError:
                pass
        login = LoginWindow(setup, self._create_vault, self._unlock_vault, notice)
        login.authenticated.connect(self._on_authenticated)
        login.closed.connect(self._app.quit)
        self._login = login
        login.show()
        login.raise_()
        login.activateWindow()

    # ------------------------------------------------------------------ auth
    def _create_vault(self, master_password: str) -> None:
        self._keys.create_vault(master_password)

    def _unlock_vault(self, master_password: str) -> None:
        self._keys.unlock(master_password)

    def _on_authenticated(self) -> None:
        try:
            self._service.load()
        except (PasswordManagerError, VaultError) as exc:
            logger.error("Vault loaded with error: %s", type(exc).__name__)
            self._keys.lock()
            if self._login is not None:
                self._login.close_silently()
                self._login.deleteLater()
                self._login = None
            MessageDialog.show_error(None, "Не удалось загрузить данные", str(exc))
            self._show_login(setup=False)
            return

        if self._login is not None:
            self._login.close_silently()
            self._login.deleteLater()
            self._login = None
        self._open_main()

    # ------------------------------------------------------------------ main
    def _open_main(self) -> None:
        self._dispose_main()
        main = MainWindow(
            self._vault_path,
            self._keys,
            self._service,
            self._backups,
            self._clipboard,
        )
        main.lock_requested.connect(self.lock)
        main.close_requested.connect(self._app.quit)
        main.restore_requested.connect(self._restore_backup)
        self._main = main
        main.show()
        main.raise_()
        main.activateWindow()
        if self._service.corrupt_records:
            show_toast(
                main,
                f"Повреждено записей: {self._service.corrupt_records}. Они пропущены.",
                "warning",
                6000,
            )
            self._service.corrupt_records = 0

    # ------------------------------------------------------------------ lock
    def lock(self) -> None:
        if not self._keys.unlocked:
            return
        self._dispose_main()
        self._service.clear()
        self._keys.lock()
        self._clipboard.clear_if_ours()
        self._show_login(setup=False)

    def _dispose_main(self) -> None:
        main = self._main
        self._main = None
        if main is None:
            return
        try:
            main.prepare_lock()
            main.force_close()
            main.deleteLater()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ restore
    def _restore_backup(self, backup_path: str) -> None:
        self._dispose_main()
        self._service.clear()
        self._keys.close()
        self._db.close()
        try:
            BackupService.restore_backup(backup_path, self._vault_path, safety_copy=True)
        except Exception as exc:
            logger.error("Backup restore failed: %s", type(exc).__name__)
            self._build_services()
            MessageDialog.show_error(
                None,
                "Не удалось восстановить хранилище",
                f"{exc}\n\nТекущее хранилище не изменено.",
            )
            self._show_login(setup=False)
            return

        self._build_services()
        self._show_login(
            setup=False,
            notice="Хранилище восстановлено. Введите мастер-пароль резервной копии.",
        )

    # ------------------------------------------------------------------ shutdown
    def _shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self._clipboard.clear_if_ours()
        except Exception:
            pass
        self._service.clear()
        self._keys.close()
