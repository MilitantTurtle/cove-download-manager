"""Dialogs in the cove-screen-recorder visual idiom: dialog title, optional
subtitle, sections / form rows, accent OK / ghost Cancel.
"""
from __future__ import annotations

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .clipboard import extract_urls
from .config import CATEGORY_NAMES, CONNECTION_CHOICES, ScheduleWindow, Settings
from .speed_limit import (
    SPEED_LIMIT_UNITS,
    configure_speed_spin,
    speed_value_to_kbps,
)


def _make_buttons(parent: QDialog, ok_text: str = "Save") -> QDialogButtonBox:
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    ok = bb.button(QDialogButtonBox.Ok)
    ok.setText(ok_text)
    ok.setProperty("kind", "accent")
    bb.accepted.connect(parent.accept)
    bb.rejected.connect(parent.reject)
    return bb


def _title_block(layout: QVBoxLayout, title: str, subtitle: str | None = None) -> None:
    t = QLabel(title)
    t.setObjectName("dialogTitle")
    layout.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("dialogSubtitle")
        layout.addWidget(s)


def _make_connections_combo(current: int) -> QComboBox:
    """IDM-style connections dropdown (1, 2, 4, 8, 16, 24, 32)."""
    combo = QComboBox()
    for n in CONNECTION_CHOICES:
        combo.addItem(str(n), n)
    closest = min(CONNECTION_CHOICES, key=lambda v: abs(v - current))
    combo.setCurrentIndex(CONNECTION_CHOICES.index(closest))
    return combo


def _time_format(use_24h: bool) -> str:
    return "HH:mm" if use_24h else "hh:mm AP"


class AddDownloadDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add download")
        self.setMinimumWidth(560)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        _title_block(layout, "Add download", "Paste one or more URLs, one per line.")

        self.urls = QPlainTextEdit()
        self.urls.setPlaceholderText("https://example.com/file.zip")
        self.urls.setMinimumHeight(140)
        layout.addWidget(self.urls)

        form = QFormLayout()
        form.setSpacing(10)
        self.dir_edit = QLineEdit(settings.download_dir)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit, 1)
        row.addWidget(browse)
        form.addRow("Save to", row)
        layout.addLayout(form)

        self.convert_mp3 = QCheckBox("Convert to MP3 after download")
        self.convert_mp3.setChecked(False)
        layout.addWidget(self.convert_mp3)

        layout.addWidget(_make_buttons(self, ok_text="Add"))

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Save downloads to", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)

    def get_urls(self) -> list[str]:
        text = self.urls.toPlainText()
        urls = extract_urls(text)
        if urls:
            return urls
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def get_dir(self) -> str:
        return self.dir_edit.text().strip() or self.settings.download_dir

    def get_convert_mp3(self) -> bool:
        return self.convert_mp3.isChecked()


class ClipboardBatchDialog(QDialog):
    def __init__(self, urls: list[str], settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add from clipboard")
        self.setMinimumWidth(560)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        _title_block(
            layout,
            "Add from clipboard",
            f"Found {len(urls)} URL(s). Pick which to queue.",
        )

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        for u in urls:
            item = QListWidgetItem(u)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)

        form = QFormLayout()
        form.setSpacing(10)
        self.dir_edit = QLineEdit(settings.download_dir)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit, 1)
        row.addWidget(browse)
        form.addRow("Save to", row)
        layout.addLayout(form)

        controls = QHBoxLayout()
        select_all = QPushButton("Select all")
        none_btn = QPushButton("Select none")
        select_all.clicked.connect(lambda: self._set_all(True))
        none_btn.clicked.connect(lambda: self._set_all(False))
        controls.addWidget(select_all)
        controls.addWidget(none_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        layout.addWidget(_make_buttons(self, ok_text="Queue"))

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Save downloads to", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)

    def _set_all(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def selected(self) -> list[str]:
        out: list[str] = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.text())
        return out

    def get_dir(self) -> str:
        return self.dir_edit.text().strip() or self.settings.download_dir


_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class SchedulerDialog(QDialog):
    def __init__(self, window: ScheduleWindow, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule")
        self.setMinimumWidth(440)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        _title_block(layout, "Schedule", "Restrict downloads to a daily time window.")

        self.enabled = QCheckBox("Enable scheduled window")
        self.enabled.setChecked(window.enabled)
        layout.addWidget(self.enabled)

        form = QFormLayout()
        form.setSpacing(10)
        fmt = _time_format(settings.time_format_24h)
        self.start = QTimeEdit(QTime(window.start_hour, window.start_minute))
        self.start.setDisplayFormat(fmt)
        self.end = QTimeEdit(QTime(window.end_hour, window.end_minute))
        self.end.setDisplayFormat(fmt)
        form.addRow("Start", self.start)
        form.addRow("End", self.end)
        layout.addLayout(form)

        # Time format toggle.
        self.use_24h = QCheckBox("24-hour format")
        self.use_24h.setChecked(settings.time_format_24h)
        self.use_24h.toggled.connect(self._on_format_toggled)
        layout.addWidget(self.use_24h)

        days_group = QGroupBox("Days")
        grid = QGridLayout(days_group)
        grid.setSpacing(8)
        self._day_boxes: list[QCheckBox] = []
        for i, name in enumerate(_DAYS):
            box = QCheckBox(name)
            box.setChecked(i in window.days)
            self._day_boxes.append(box)
            grid.addWidget(box, i // 4, i % 4)
        layout.addWidget(days_group)

        hint = QLabel("If End is on or before Start, the window wraps past midnight.")
        hint.setProperty("role", "muted")
        layout.addWidget(hint)

        layout.addWidget(_make_buttons(self, ok_text="Save"))

    def _on_format_toggled(self, checked: bool) -> None:
        fmt = _time_format(checked)
        self.start.setDisplayFormat(fmt)
        self.end.setDisplayFormat(fmt)

    def result_window(self) -> ScheduleWindow:
        return ScheduleWindow(
            enabled=self.enabled.isChecked(),
            start_hour=self.start.time().hour(),
            start_minute=self.start.time().minute(),
            end_hour=self.end.time().hour(),
            end_minute=self.end.time().minute(),
            days=[i for i, b in enumerate(self._day_boxes) if b.isChecked()],
        )

    def use_24h_format(self) -> bool:
        return self.use_24h.isChecked()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(540)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        _title_block(layout, "Settings", "Defaults applied to new downloads.")

        # The settings form is taller than the usable desktop on many laptop
        # and scaled displays. Keep the title and action buttons visible while
        # allowing the form itself to shrink and scroll.
        self.settings_scroll = QScrollArea(self)
        self.settings_scroll.setObjectName("settingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.dir_edit = QLineEdit(settings.download_dir)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit, 1)
        row.addWidget(browse)
        form.addRow("Default download folder", row)

        self.connections = _make_connections_combo(settings.connections_per_server)
        form.addRow("Connections per file", self.connections)

        self.max_concurrent = QSpinBox()
        self.max_concurrent.setRange(1, 16)
        self.max_concurrent.setValue(settings.max_concurrent)
        form.addRow("Concurrent downloads", self.max_concurrent)

        speed_row = QHBoxLayout()
        self.speed_limit = QDoubleSpinBox()
        self.speed_unit = QComboBox()
        self.speed_unit.addItems(SPEED_LIMIT_UNITS)
        self.speed_unit.setCurrentText(settings.speed_limit_unit)
        self._speed_display_unit = settings.speed_limit_unit
        self._speed_limit_kbps = settings.overall_speed_limit_kbps
        configure_speed_spin(
            self.speed_limit,
            settings.speed_limit_unit,
            settings.overall_speed_limit_kbps,
        )
        self.speed_limit.valueChanged.connect(self._on_speed_value_changed)
        self.speed_unit.currentTextChanged.connect(self._on_speed_unit_changed)
        speed_row.addWidget(self.speed_limit, 1)
        speed_row.addWidget(self.speed_unit)
        form.addRow("Global speed limit", speed_row)

        self.speed_enabled = QCheckBox("Enable speed limiter")
        self.speed_enabled.setChecked(settings.speed_limiter_enabled)
        form.addRow("", self.speed_enabled)

        self.use_24h = QCheckBox("24-hour clock in scheduler")
        self.use_24h.setChecked(settings.time_format_24h)
        form.addRow("Time format", self.use_24h)

        self.auto_update = QCheckBox("Check for updates on startup")
        self.auto_update.setChecked(settings.auto_update_check)
        self.auto_update.setToolTip(
            "When enabled, Cove pings GitHub Releases on launch and prompts "
            "you if a newer version is available. Updates are never installed "
            "silently - you'll always be asked first."
        )
        form.addRow("Updates", self.auto_update)

        self.smart_segments = QCheckBox("Auto-tune connections based on server support")
        self.smart_segments.setChecked(settings.intelligent_segments)
        self.smart_segments.setToolTip(
            "Probes the server before downloading to check Range header support "
            "and adjusts the number of connections based on file size."
        )
        form.addRow("Smart segments", self.smart_segments)

        self.notify_complete = QCheckBox("Notify when a download completes")
        self.notify_complete.setChecked(settings.notify_on_complete)
        form.addRow("Notifications", self.notify_complete)

        self.notify_error = QCheckBox("Notify when a download fails")
        self.notify_error.setChecked(settings.notify_on_error)
        form.addRow("", self.notify_error)

        scroll_layout.addLayout(form)

        # Proxy
        proxy_group = QGroupBox("Proxy")
        proxy_lay = QFormLayout(proxy_group)
        proxy_lay.setSpacing(8)
        self.proxy_type = QComboBox()
        for label, val in [("None", "none"), ("HTTP", "http"),
                           ("HTTPS", "https"), ("SOCKS5", "socks5")]:
            self.proxy_type.addItem(label, val)
        idx = self.proxy_type.findData(settings.proxy_type)
        if idx >= 0:
            self.proxy_type.setCurrentIndex(idx)
        self.proxy_type.currentIndexChanged.connect(self._on_proxy_type_changed)
        proxy_lay.addRow("Type", self.proxy_type)
        self.proxy_host = QLineEdit(settings.proxy_host)
        self.proxy_host.setPlaceholderText("proxy.example.com")
        proxy_lay.addRow("Host", self.proxy_host)
        self.proxy_port = QSpinBox()
        self.proxy_port.setRange(0, 65535)
        self.proxy_port.setSpecialValueText("Default")
        self.proxy_port.setValue(settings.proxy_port)
        proxy_lay.addRow("Port", self.proxy_port)
        self.proxy_user = QLineEdit(settings.proxy_username)
        self.proxy_user.setPlaceholderText("Optional")
        proxy_lay.addRow("Username", self.proxy_user)
        self.proxy_pass = QLineEdit(settings.proxy_password)
        self.proxy_pass.setPlaceholderText("Optional")
        self.proxy_pass.setEchoMode(QLineEdit.Password)
        proxy_lay.addRow("Password", self.proxy_pass)
        self.proxy_note = QLabel("Restart Cove to apply proxy changes.")
        self.proxy_note.setProperty("role", "muted")
        proxy_lay.addRow(self.proxy_note)
        scroll_layout.addWidget(proxy_group)
        self._on_proxy_type_changed()

        # Category folders
        cat_group = QGroupBox("Category folders")
        cat_lay = QFormLayout(cat_group)
        cat_lay.setSpacing(8)
        self._cat_edits: dict[str, QLineEdit] = {}
        for name in CATEGORY_NAMES:
            current = getattr(settings.category_dirs, name, "")
            edit = QLineEdit(current)
            edit.setPlaceholderText(f"Use default download folder")
            btn = QPushButton("Browse")
            btn.clicked.connect(lambda _=False, e=edit, n=name: self._browse_category(e, n))
            row_h = QHBoxLayout()
            row_h.addWidget(edit, 1)
            row_h.addWidget(btn)
            cat_lay.addRow(name, row_h)
            self._cat_edits[name] = edit
        self.auto_sort = QCheckBox("Create category subfolders automatically")
        self.auto_sort.setChecked(settings.auto_sort_by_category)
        self.auto_sort.setToolTip(
            "When enabled and a category folder is not set, Cove creates a "
            "subfolder under the default download folder (e.g. Downloads/Videos)."
        )
        cat_lay.addRow(self.auto_sort)
        cat_note = QLabel("Leave blank to use the default download folder.")
        cat_note.setProperty("role", "muted")
        cat_lay.addRow(cat_note)
        scroll_layout.addWidget(cat_group)

        self.settings_scroll.setWidget(scroll_content)
        layout.addWidget(self.settings_scroll, 1)

        # Keep a direct reference to the button box rather than fishing it
        # back out of the layout by index (which breaks if layout order
        # changes). Route Save through _on_accept instead of the default.
        bb = _make_buttons(self, ok_text="Save")
        layout.addWidget(bb)
        bb.accepted.disconnect()
        bb.accepted.connect(self._on_accept)

        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(900, max(540, available.width() - 80))
            height = min(
                720,
                max(self.minimumSizeHint().height(), available.height() - 80),
            )
            self.resize(width, height)
        else:  # Defensive fallback for unusual headless Qt platforms.
            self.resize(900, 640)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Default download folder", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)

    def _browse_category(self, edit: QLineEdit, name: str) -> None:
        start = edit.text() or self.dir_edit.text()
        path = QFileDialog.getExistingDirectory(self, f"{name} folder", start)
        if path:
            edit.setText(path)

    def _on_proxy_type_changed(self, _index: int = 0) -> None:
        enabled = self.proxy_type.currentData() != "none"
        self.proxy_host.setEnabled(enabled)
        self.proxy_port.setEnabled(enabled)
        self.proxy_user.setEnabled(enabled)
        self.proxy_pass.setEnabled(enabled)

    def _on_speed_unit_changed(self, unit: str) -> None:
        self._speed_display_unit = unit
        configure_speed_spin(
            self.speed_limit,
            unit,
            self._speed_limit_kbps,
        )

    def _on_speed_value_changed(self, value: float) -> None:
        self._speed_limit_kbps = speed_value_to_kbps(
            value, self._speed_display_unit
        )

    def _on_accept(self) -> None:
        self.settings.download_dir = self.dir_edit.text().strip() or self.settings.download_dir
        self.settings.connections_per_server = self.connections.currentData()
        self.settings.max_concurrent = self.max_concurrent.value()
        self.settings.overall_speed_limit_kbps = self._speed_limit_kbps
        self.settings.speed_limiter_enabled = self.speed_enabled.isChecked()
        self.settings.speed_limit_unit = self.speed_unit.currentText()
        self.settings.time_format_24h = self.use_24h.isChecked()
        self.settings.auto_update_check = self.auto_update.isChecked()
        self.settings.intelligent_segments = self.smart_segments.isChecked()
        self.settings.notify_on_complete = self.notify_complete.isChecked()
        self.settings.notify_on_error = self.notify_error.isChecked()
        self.settings.proxy_type = self.proxy_type.currentData()
        self.settings.proxy_host = self.proxy_host.text().strip()
        self.settings.proxy_port = self.proxy_port.value()
        self.settings.proxy_username = self.proxy_user.text().strip()
        self.settings.proxy_password = self.proxy_pass.text()
        self.settings.auto_sort_by_category = self.auto_sort.isChecked()
        for name, edit in self._cat_edits.items():
            setattr(self.settings.category_dirs, name, edit.text().strip())
        self.settings.save()
        self.accept()
