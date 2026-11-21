"""Main three-pane vault window."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.models import PasswordRecord, display_timestamp
from app.security.key_manager import KeyManager
from app.services.backup_service import BackupService
from app.services.clipboard_service import ClipboardService
from app.services.password_service import PasswordService
from app.services.session_service import AutoLockService
from app.ui import icons
from app.ui.async_utils import TaskRunner
from app.ui.category_dialog import CategoryDialog
from app.ui.generator_dialog import GeneratorDialog
from app.ui.password_dialog import PasswordDialog
from app.ui.settings_window import SettingsPage
from app.ui.styles import ACCENT, DANGER, TEXT_MUTED, TEXT_SECONDARY, WARNING
from app.ui.widgets import (
    Avatar,
    Chip,
    ConfirmDialog,
    DragHeader,
    EmptyState,
    FieldRow,
    IconButton,
    PrimaryButton,
    RecordCard,
    SearchInput,
    SidebarItem,
    make_button,
    make_label,
    show_toast,
)

logger = logging.getLogger(__name__)


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                _clear_layout(child)


class MainWindow(QWidget):
    lock_requested = Signal()
    close_requested = Signal()
    restore_requested = Signal(str)

    def __init__(
        self,
        vault_path: Path,
        key_manager: KeyManager,
        service: PasswordService,
        backup_service: BackupService,
        clipboard: ClipboardService,
        runner: TaskRunner | None = None,
    ) -> None:
        super().__init__(None)
        self._vault_path = vault_path
        self._keys = key_manager
        self._service = service
        self._backups = backup_service
        self._clipboard = clipboard
        self._runner = runner
        self._selected_id: str | None = None
        self._current_record: PasswordRecord | None = None
        self._filter = "all"
        self._settings_open = False
        self._allow_close = False
        self._password_visible = False
        self._cards: dict[str, RecordCard] = {}
        self._category_items: dict[str, SidebarItem] = {}
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setSingleShot(True)
        self._reveal_timer.timeout.connect(self._hide_password)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self.refresh)

        self.setWindowTitle(config.APP_NAME)
        self.setWindowIcon(icons.icon("logo", ACCENT, 32))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1120, 700)
        self.resize(1320, 820)
        self.setMouseTracking(True)

        self._build()
        self._build_shortcuts()

        self._autolock = AutoLockService(service.settings.auto_lock_minutes, self)
        self._autolock.timeout.connect(self._on_auto_lock_timeout)
        self._autolock.start()
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

        self.refresh()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)
        self.root = QFrame()
        self.root.setObjectName("AppRoot")
        self.root_layout = QVBoxLayout(self.root)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.root_layout.addWidget(self._build_title_bar())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_sidebar())

        self.content_stack = QStackedWidget()
        self.vault_page = QWidget()
        vault_layout = QHBoxLayout(self.vault_page)
        vault_layout.setContentsMargins(0, 0, 0, 0)
        vault_layout.setSpacing(0)
        vault_layout.addWidget(self._build_list_pane())
        vault_layout.addWidget(self._build_detail_pane(), 1)
        self.content_stack.addWidget(self.vault_page)
        self.settings_page = SettingsPage(
            self._service,
            self._backups,
            self._keys,
            self._clipboard,
            self._vault_path,
            runner=self._runner,
        )
        self.settings_page.auto_lock_changed.connect(self._on_auto_lock_changed)
        self.settings_page.lock_requested.connect(self.lock_requested.emit)
        self.settings_page.restore_requested.connect(self.restore_requested.emit)
        self.content_stack.addWidget(self.settings_page)
        body_layout.addWidget(self.content_stack, 1)
        self.root_layout.addWidget(body, 1)

        outer.addWidget(self.root)

    def _build_title_bar(self) -> QWidget:
        bar = DragHeader()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 10, 0)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(icons.pixmap("logo", ACCENT, 24))
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(logo)
        app_name = make_label(config.APP_NAME, "AppName")
        app_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(app_name)
        layout.addSpacing(16)

        self.search = SearchInput()
        self.search.textChanged.connect(self._on_search_changed)
        self.search.setMinimumWidth(260)
        layout.addWidget(self.search, 1)

        self.add_button = PrimaryButton("Добавить", "plus")
        self.add_button.setFixedHeight(36)
        self.add_button.setMinimumWidth(118)
        self.add_button.clicked.connect(self._create_record)
        layout.addWidget(self.add_button)

        generator = IconButton("key", "Генератор паролей", 34, 18)
        generator.clicked.connect(self._open_generator)
        layout.addWidget(generator)

        settings = IconButton("settings", "Настройки", 34, 18)
        settings.clicked.connect(self._show_settings)
        layout.addWidget(settings)

        lock = IconButton("lock", "Заблокировать (Ctrl+L)", 34, 18)
        lock.clicked.connect(self.lock_requested.emit)
        layout.addWidget(lock)

        divider = QFrame()
        divider.setFixedSize(1, 24)
        divider.setStyleSheet("background: #262C38;")
        layout.addSpacing(4)
        layout.addWidget(divider)
        layout.addSpacing(4)

        minimize = IconButton("minus", "Свернуть", 28, 14, object_name="WindowButton")
        minimize.clicked.connect(self.showMinimized)
        layout.addWidget(minimize)
        self.maximize_button = IconButton("square", "Развернуть", 28, 14, object_name="WindowButton")
        self.maximize_button.clicked.connect(self._toggle_maximized)
        layout.addWidget(self.maximize_button)
        close = IconButton("x", "Закрыть", 28, 14, object_name="CloseWindow")
        close.clicked.connect(self.close)
        layout.addWidget(close)
        return bar

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(238)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(3)

        layout.addWidget(self._sidebar_section("БИБЛИОТЕКА"))
        self._all_item = SidebarItem("all", "Все записи", "grid")
        self._all_item.clicked.connect(self._on_sidebar_clicked)
        layout.addWidget(self._all_item)
        self._favorites_item = SidebarItem("favorites", "Избранное", "star")
        self._favorites_item.clicked.connect(self._on_sidebar_clicked)
        layout.addWidget(self._favorites_item)

        layout.addSpacing(14)
        layout.addWidget(self._sidebar_section("КАТЕГОРИИ"))
        self._categories_scroll = QScrollArea()
        self._categories_scroll.setWidgetResizable(True)
        self._categories_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._categories_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._categories_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._categories_scroll.setStyleSheet("background: transparent;")
        categories_widget = QWidget()
        self._categories_layout = QVBoxLayout(categories_widget)
        self._categories_layout.setContentsMargins(0, 0, 0, 0)
        self._categories_layout.setSpacing(3)
        self._categories_scroll.setWidget(categories_widget)
        layout.addWidget(self._categories_scroll)

        self._manage_categories = SidebarItem("manage", "Настроить категории", "sliders")
        self._manage_categories.clicked.connect(self._on_sidebar_clicked)
        layout.addWidget(self._manage_categories)

        layout.addStretch(1)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #222834;")
        layout.addWidget(divider)
        layout.addSpacing(6)

        self._generator_item = SidebarItem("generator", "Генератор паролей", "key")
        self._generator_item.clicked.connect(self._on_sidebar_clicked)
        layout.addWidget(self._generator_item)
        self._settings_item = SidebarItem("settings", "Настройки", "settings")
        self._settings_item.clicked.connect(self._on_sidebar_clicked)
        layout.addWidget(self._settings_item)

        layout.addSpacing(12)
        footer = QHBoxLayout()
        footer.setContentsMargins(10, 0, 0, 0)
        footer.setSpacing(7)
        shield = QLabel()
        shield.setPixmap(icons.pixmap("shield", TEXT_MUTED, 14))
        footer.addWidget(shield)
        footer.addWidget(make_label("Зашифровано локально", "MutedSmall"))
        footer.addStretch(1)
        layout.addLayout(footer)
        version = make_label(f"v{config.APP_VERSION}", "MutedSmall")
        version.setContentsMargins(31, 0, 0, 0)
        layout.addWidget(version)

        self._rebuild_categories()
        return sidebar

    def _sidebar_section(self, text: str) -> QLabel:
        label = make_label(text, "SidebarSection")
        label.setContentsMargins(10, 0, 0, 4)
        return label

    def _build_list_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("ListPane")
        pane.setFixedWidth(360)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 22, 20, 12)
        header_layout.setSpacing(10)
        self.list_title = make_label("Все записи", "PaneTitle")
        header_layout.addWidget(self.list_title)
        header_layout.addStretch(1)
        self.list_count = make_label("0", "Muted")
        header_layout.addWidget(self.list_count)
        layout.addWidget(header)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(14, 4, 14, 16)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.list_scroll.setWidget(self.list_container)
        layout.addWidget(self.list_scroll, 1)
        return pane

    def _build_detail_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("DetailPane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        self.detail_stack = QStackedWidget()
        layout.addWidget(self.detail_stack)

        empty = EmptyState(
            "key",
            "Выберите запись",
            "Слева отображаются сохранённые сервисы. Выберите запись, чтобы увидеть логин, пароль и заметки.",
        )
        self.detail_stack.addWidget(empty)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 26, 32, 32)
        content_layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(14)
        self.detail_avatar = Avatar(54)
        header.addWidget(self.detail_avatar)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(6)
        self.detail_title = make_label("", "")
        self.detail_title.setStyleSheet("font-size: 22px; font-weight: 600;")
        self.detail_title.setWordWrap(True)
        title_layout.addWidget(self.detail_title)
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        self.detail_chip = Chip()
        chip_row.addWidget(self.detail_chip)
        chip_row.addStretch(1)
        title_layout.addLayout(chip_row)
        header.addLayout(title_layout, 1)
        self.favorite_button = IconButton("star", "В избранное", 36, 20)
        self.favorite_button.clicked.connect(self._toggle_favorite)
        header.addWidget(self.favorite_button, 0, Qt.AlignmentFlag.AlignTop)
        content_layout.addLayout(header)

        self._fields_host = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_host)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(8)
        content_layout.addWidget(self._fields_host)

        content_layout.addWidget(make_label("ЗАМЕТКА", "Caption"))
        self.notes_label = make_label("", "", wrap=True)
        self.notes_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.notes_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px;")
        content_layout.addWidget(self.notes_label)

        meta = QHBoxLayout()
        meta.setSpacing(18)
        self.created_label = make_label("", "MutedSmall")
        self.updated_label = make_label("", "MutedSmall")
        meta.addWidget(self.created_label)
        meta.addWidget(self.updated_label)
        meta.addStretch(1)
        content_layout.addLayout(meta)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #222834;")
        content_layout.addWidget(divider)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.edit_button = PrimaryButton("Редактировать", "edit")
        self.edit_button.clicked.connect(self._edit_record)
        actions.addWidget(self.edit_button)
        self.delete_button = make_button("Удалить", "Danger", "trash", DANGER)
        self.delete_button.clicked.connect(self._delete_record)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        content_layout.addLayout(actions)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        self.detail_stack.addWidget(scroll)
        self.detail_stack.setCurrentIndex(0)
        return pane

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._create_record)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.lock_requested.emit)

    # ------------------------------------------------------------------ UI state
    def _rebuild_categories(self) -> None:
        _clear_layout(self._categories_layout)
        self._category_items = {}
        categories = sorted(
            self._service.settings.categories, key=lambda item: (item.order, item.name.casefold())
        )
        _, _, counts = self._service.stats()
        for category in categories:
            item = SidebarItem(
                category.id,
                category.name,
                icons.category_icon_id(category.id),
                counts.get(category.id, 0),
            )
            item.clicked.connect(self._on_sidebar_clicked)
            self._categories_layout.addWidget(item)
            self._category_items[category.id] = item
        height = min(330, max(44, len(categories) * 41 + 4))
        self._categories_scroll.setFixedHeight(height)
        self._update_sidebar_selection()

    def _update_sidebar_selection(self) -> None:
        self._all_item.set_selected(self._filter == "all" and not self._settings_open)
        self._favorites_item.set_selected(
            self._filter == "favorites" and not self._settings_open
        )
        for category_id, item in self._category_items.items():
            item.set_selected(
                self._filter == category_id and not self._settings_open
            )
        self._settings_item.set_selected(self._settings_open)
        total, favorites, counts = self._service.stats()
        self._all_item.set_count(total)
        self._favorites_item.set_count(favorites)
        for category_id, item in self._category_items.items():
            item.set_count(counts.get(category_id, 0))

    def _focus_search(self) -> None:
        self._show_vault_page()
        self.search.setFocus()
        self.search.selectAll()

    def _show_settings(self) -> None:
        self._settings_open = True
        self._hide_password()
        self.content_stack.setCurrentWidget(self.settings_page)
        self._update_sidebar_selection()

    def _show_vault_page(self) -> None:
        self._settings_open = False
        self.content_stack.setCurrentWidget(self.vault_page)
        self._update_sidebar_selection()

    def _on_sidebar_clicked(self, key: str) -> None:
        if key == "manage":
            self._open_categories()
            return
        if key == "generator":
            self._open_generator()
            return
        if key == "settings":
            self._show_settings()
            return
        self._filter = key
        self._show_vault_page()
        self.refresh()

    def _on_search_changed(self, text: str) -> None:
        if text and self._settings_open:
            self._show_vault_page()
        self._search_timer.start()

    # ------------------------------------------------------------------ data refresh
    def refresh(self) -> None:
        if self._settings_open:
            self._update_sidebar_selection()
            return
        search = self.search.text()
        category = self._filter if self._filter not in ("all", "favorites") else None
        records = self._service.list_records(
            search=search,
            category_id=category,
            favorites_only=self._filter == "favorites",
        )
        self._filtered_records = records
        self._update_list_header(len(records))
        self._rebuild_cards(records)

        visible_ids = {record.id for record in records}
        if self._selected_id not in visible_ids:
            self._selected_id = records[0].id if records else None
        for card_id, card in self._cards.items():
            card.set_selected(card_id == self._selected_id)
        self._render_selection()
        self._update_sidebar_selection()

    def _update_list_header(self, count: int) -> None:
        if self._filter == "all":
            title = "Все записи"
        elif self._filter == "favorites":
            title = "Избранное"
        else:
            title = self._service.settings.category_name(self._filter)
        self.list_title.setText(title)
        self.list_count.setText(str(count))

    def _rebuild_cards(self, records: list[PasswordRecord]) -> None:
        _clear_layout(self.list_layout)
        self._cards = {}
        if not records:
            if self.search.text():
                empty = EmptyState(
                    "search_off",
                    "Ничего не найдено",
                    "Попробуйте изменить поисковый запрос или выбрать другую категорию.",
                )
            else:
                empty = EmptyState(
                    "plus",
                    "Здесь пока пусто",
                    "Нажмите «Добавить» в верхней панели, чтобы создать первую запись.",
                )
            self.list_layout.addWidget(empty)
            self.list_layout.addStretch(1)
            return
        for record in records:
            card = RecordCard(
                record,
                self._service.settings.category_name(record.category_id),
            )
            card.clicked.connect(self._select_record)
            card.star_clicked.connect(self._toggle_favorite_by_id)
            card.set_selected(record.id == self._selected_id)
            self.list_layout.addWidget(card)
            self._cards[record.id] = card
        self.list_layout.addStretch(1)

    def _select_record(self, record_id: str) -> None:
        self._selected_id = record_id
        for card_id, card in self._cards.items():
            card.set_selected(card_id == record_id)
        self._render_selection()

    def _render_selection(self) -> None:
        if not self._selected_id:
            self._hide_password()
            self._current_record = None
            _clear_layout(self._fields_layout)
            self.detail_stack.setCurrentIndex(0)
            return
        try:
            record = self._service.get_record(self._selected_id)
        except Exception:
            self._selected_id = None
            self.detail_stack.setCurrentIndex(0)
            return

        self.detail_stack.setCurrentIndex(1)
        self.detail_avatar.set_title(record.title)
        self.detail_title.setText(record.title)
        self.detail_chip.setText(self._service.settings.category_name(record.category_id))
        self.favorite_button.set_icon(
            "star-filled" if record.favorite else "star",
            WARNING if record.favorite else TEXT_MUTED,
        )
        self.favorite_button.setToolTip(
            "Убрать из избранного" if record.favorite else "Добавить в избранное"
        )
        self._hide_password()
        self._rebuild_fields(record)
        self.notes_label.setText(record.notes or "Нет заметки.")
        self.notes_label.setStyleSheet(
            f"color: {TEXT_SECONDARY if record.notes else TEXT_MUTED}; font-size: 13px;"
        )
        self.created_label.setText(f"Создано: {display_timestamp(record.created_at)}")
        self.updated_label.setText(f"Изменено: {display_timestamp(record.updated_at)}")

    def _rebuild_fields(self, record: PasswordRecord) -> None:
        _clear_layout(self._fields_layout)
        self._current_record = record

        login_row = FieldRow("Логин", record.username, monospace=False)
        login_row.copy_requested.connect(self._copy_username)
        self._fields_layout.addWidget(login_row)

        password_row = QFrame()
        password_row.setObjectName("FieldRow")
        row_layout = QHBoxLayout(password_row)
        row_layout.setContentsMargins(14, 10, 10, 10)
        row_layout.setSpacing(10)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(make_label("Пароль", "FieldCaption"))
        self.password_label = make_label("•" * 12)
        self.password_label.setStyleSheet(
            "font-family: 'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', monospace;"
            "font-size: 13px; letter-spacing: 1px;"
        )
        self.password_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_layout.addWidget(self.password_label)
        row_layout.addLayout(text_layout, 1)

        self.reveal_button = IconButton("eye", "Показать пароль", 30, 16)
        self.reveal_button.clicked.connect(self._toggle_password)
        row_layout.addWidget(self.reveal_button)
        copy_password = IconButton("copy", "Копировать пароль", 30, 16)
        copy_password.clicked.connect(self._copy_password)
        row_layout.addWidget(copy_password)
        self._fields_layout.addWidget(password_row)
        self._password_row = password_row

        url_row = FieldRow("Сайт", record.url)
        url_row.copy_requested.connect(self._copy_url)
        self._fields_layout.addWidget(url_row)

    # ------------------------------------------------------------------ clipboard
    def _copy_username(self, value: str) -> None:
        if not value:
            return
        self._clipboard.copy_text(value)
        show_toast(self, "Логин скопирован", "success")

    def _copy_url(self, value: str) -> None:
        if not value:
            return
        self._clipboard.copy_text(value)
        show_toast(self, "Ссылка скопирована", "success")

    def _copy_password(self) -> None:
        record = getattr(self, "_current_record", None)
        if record is None:
            return
        seconds = self._service.settings.clipboard_clear_seconds
        self._clipboard.copy_secret(record.password, seconds)
        if seconds > 0:
            show_toast(
                self,
                f"Пароль скопирован · буфер очистится через {seconds} с",
                "success",
            )
        else:
            show_toast(self, "Пароль скопирован в буфер обмена", "success")

    def _toggle_password(self) -> None:
        record = getattr(self, "_current_record", None)
        if record is None:
            return
        if self._password_visible:
            self._hide_password()
            return
        self._password_visible = True
        self.password_label.setText(record.password)
        self.reveal_button.set_icon("eye-off", ACCENT)
        self.reveal_button.setToolTip("Скрыть пароль")
        self.password_label.update()
        self._password_row.update()
        self._reveal_timer.start(20000)

    def _hide_password(self) -> None:
        self._reveal_timer.stop()
        self._password_visible = False
        if hasattr(self, "password_label"):
            self.password_label.setText("•" * 12)
            self.password_label.update()
        if hasattr(self, "reveal_button"):
            self.reveal_button.set_icon("eye", TEXT_MUTED)
            self.reveal_button.setToolTip("Показать пароль")

    # ------------------------------------------------------------------ record actions
    def _create_record(self) -> None:
        created: list[PasswordRecord] = []

        def save(payload: dict[str, object]) -> None:
            created.append(self._service.create_record(**payload))  # type: ignore[arg-type]

        dialog = PasswordDialog(self._service, self._clipboard, save, parent=self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._rebuild_categories()
        if accepted and created:
            self._show_vault_page()
            self._filter = "all"
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.refresh()
            self._select_record(created[0].id)
            show_toast(self, "Запись добавлена", "success")

    def _edit_record(self) -> None:
        record = getattr(self, "_current_record", None)
        if record is None:
            return

        def save(payload: dict[str, object]) -> None:
            self._service.update_record(record.id, **payload)  # type: ignore[arg-type]

        dialog = PasswordDialog(
            self._service, self._clipboard, save, record=record, parent=self
        )
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._rebuild_categories()
        if accepted:
            updated = self._service.get_record(record.id)
            if (
                self._filter not in ("all", "favorites")
                and updated.category_id != self._filter
            ):
                self._filter = "all"
            self.refresh()
            self._select_record(record.id)
            show_toast(self, "Изменения сохранены", "success")

    def _delete_record(self) -> None:
        record = getattr(self, "_current_record", None)
        if record is None:
            return
        if not ConfirmDialog.ask(
            self,
            "Удалить запись?",
            f"Запись «{record.title}» будет удалена без возможности восстановления.",
            "Удалить",
            danger=True,
        ):
            return
        self._service.delete_record(record.id)
        self._selected_id = None
        self._current_record = None
        self._hide_password()
        self.refresh()
        show_toast(self, "Запись удалена", "success")

    def _toggle_favorite(self) -> None:
        record = getattr(self, "_current_record", None)
        if record is not None:
            self._toggle_favorite_by_id(record.id)

    def _toggle_favorite_by_id(self, record_id: str) -> None:
        try:
            record = self._service.toggle_favorite(record_id)
        except Exception as exc:
            show_toast(self, str(exc), "error")
            return
        self.refresh()
        if record.favorite:
            show_toast(self, "Добавлено в избранное", "success")
        else:
            show_toast(self, "Убрано из избранного", "info")

    def _open_generator(self) -> None:
        dialog = GeneratorDialog(
            self._clipboard,
            self._service.settings.clipboard_clear_seconds,
            select_mode=False,
            parent=self,
        )
        dialog.exec()

    def _open_categories(self) -> None:
        dialog = CategoryDialog(self._service, self)
        dialog.changed.connect(self._on_categories_changed)
        dialog.exec()
        self._on_categories_changed()

    def _on_categories_changed(self) -> None:
        if self._filter not in ("all", "favorites"):
            if self._service.settings.category(self._filter) is None:
                self._filter = "all"
        self._rebuild_categories()
        self.refresh()

    # ------------------------------------------------------------------ settings/autolock
    def _on_auto_lock_changed(self, minutes: int) -> None:
        self._autolock.set_minutes(minutes)
        if minutes:
            show_toast(self, f"Автоблокировка: {minutes} мин", "info")
        else:
            show_toast(self, "Автоблокировка отключена", "warning")

    def _on_auto_lock_timeout(self) -> None:
        self._prepare_dialogs_for_lock()
        self._hide_password()
        self._autolock.stop()
        QTimer.singleShot(0, self.lock_requested.emit)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() in (
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
        ):
            if self.isVisible() and self._autolock.is_active():
                self._autolock.reset()
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ window
    def prepare_lock(self) -> None:
        self._autolock.stop()
        self._reveal_timer.stop()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._prepare_dialogs_for_lock()
        self._selected_id = None
        self._current_record = None
        self._hide_password()
        _clear_layout(self._fields_layout)
        _clear_layout(self.list_layout)
        self._cards = {}
        if hasattr(self, "detail_title"):
            self.detail_title.clear()
            self.notes_label.clear()
            self.created_label.clear()
            self.updated_label.clear()
        self.detail_stack.setCurrentIndex(0)

    def _prepare_dialogs_for_lock(self) -> None:
        """Close dialogs, but let a busy rekey dialog wipe its secrets instead.

        A rekey worker owns the vault connection until it finishes.  Destroying
        its dialog (and therefore its QObject parent chain) mid-operation was the
        root cause of SEC-01, so the dialog stays alive until the runner reports
        the result and rejects itself.
        """

        for widget in QApplication.topLevelWidgets():
            if not isinstance(widget, QDialog) or not widget.isVisible():
                continue
            prepare = getattr(widget, "prepare_for_lock", None)
            is_busy = getattr(widget, "is_busy", False)
            if callable(prepare) and is_busy:
                prepare()
            else:
                widget.reject()

    def force_close(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._allow_close:
            event.accept()
        else:
            event.ignore()
            self.close_requested.emit()

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            maximized = self.isMaximized()
            self.root.setProperty("maximized", maximized)
            self.root.style().unpolish(self.root)
            self.root.style().polish(self.root)
            self.maximize_button.set_icon("restore" if maximized else "square", TEXT_SECONDARY)
            margins = (0, 0, 0, 0) if maximized else (6, 6, 6, 6)
            self.layout().setContentsMargins(*margins)
            if not maximized:
                self._hide_password()

    def _resize_edges(self, position) -> Qt.Edge:
        if self.isMaximized():
            return Qt.Edge(0)
        edge = Qt.Edge(0)
        margin = 8
        x, y = position.x(), position.y()
        if x <= margin:
            edge |= Qt.Edge.LeftEdge
        elif x >= self.width() - margin:
            edge |= Qt.Edge.RightEdge
        if y <= margin:
            edge |= Qt.Edge.TopEdge
        elif y >= self.height() - margin:
            edge |= Qt.Edge.BottomEdge
        return edge

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        edge = self._resize_edges(event.position().toPoint())
        if edge == Qt.Edge.LeftEdge or edge == Qt.Edge.RightEdge:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge == Qt.Edge.TopEdge or edge == Qt.Edge.BottomEdge:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._resize_edges(event.position().toPoint())
            if edge:
                handle = self.windowHandle()
                if handle is not None:
                    handle.startSystemResize(edge)
                    return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self._settings_open:
                self._show_vault_page()
                return
            if self.search.text():
                self.search.clear()
                return
        super().keyPressEvent(event)
