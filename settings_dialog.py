"""settings_dialog.py — App-wide Settings dialog."""

from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QComboBox,
    QTabBar,
    QTabWidget,
    QWidget,
    QScrollArea,
    QDialogButtonBox,
    QFrame,
    QLineEdit,
)
from PyQt5.QtGui import QFont

from themes import T, apply_qss_to, load_settings, save_settings
import security
import ai_assist
import k8s_ai_ops
from lock_screen import SetPinDialog

_AUTOLOCK_OPTIONS = [
    ("1 minute", 1),
    ("2 minutes", 2),
    ("5 minutes", 5),
    ("10 minutes", 10),
    ("15 minutes", 15),
    ("30 minutes", 30),
]


class SwipeTabWidget(QTabWidget):
    """QTabWidget that supports horizontal swipe gestures in addition to clicks."""

    _DRAG_THRESHOLD = 65
    _WHEEL_THRESHOLD = 55
    _SWIPE_COOLDOWN_MS = 350

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(QTabBar())
        self.tabBar().setUsesScrollButtons(True)
        self.tabBar().setExpanding(False)

        self._swipe_start = None
        self._swipe_dragging = False
        self._wheel_distance = 0
        self._wheel_locked = False

        self.tabBar().installEventFilter(self)

    def addTab(self, widget, label):
        index = super().addTab(widget, label)
        self._install_swipe_filter(widget)
        return index

    def _install_swipe_filter(self, widget):
        """Watch the tab page and its children so a swipe can start anywhere."""
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)

    def _reset_swipe(self):
        self._swipe_start = None
        self._swipe_dragging = False

    def _change_tab_from_direction(self, direction):
        current = self.currentIndex()
        target = current + direction

        if target < 0 or target >= self.count():
            return False

        self.setCurrentIndex(target)
        return True

    def _unlock_wheel(self):
        self._wheel_locked = False
        self._wheel_distance = 0

    def _handle_horizontal_wheel(self, event):
        pixel_delta = event.pixelDelta().x()
        angle_delta = event.angleDelta().x()
        delta = pixel_delta if pixel_delta else angle_delta

        if not delta:
            return False

        # Ignore predominantly vertical scrolling so normal QScrollArea behavior
        # continues to work inside the settings pages.
        vertical = event.pixelDelta().y() or event.angleDelta().y()
        if abs(delta) <= abs(vertical) * 1.15:
            return False

        if self._wheel_locked:
            return True

        if self._wheel_distance and (delta > 0) != (self._wheel_distance > 0):
            self._wheel_distance = 0

        self._wheel_distance += delta

        if abs(self._wheel_distance) < self._WHEEL_THRESHOLD:
            return True

        direction = -1 if self._wheel_distance > 0 else 1
        changed = self._change_tab_from_direction(direction)
        self._wheel_distance = 0

        if changed:
            self._wheel_locked = True
            QTimer.singleShot(self._SWIPE_COOLDOWN_MS, self._unlock_wheel)

        return True

    def eventFilter(self, watched, event):
        event_type = event.type()

        if event_type == QEvent.Wheel:
            if self._handle_horizontal_wheel(event):
                return True

        elif event_type == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self._swipe_start = event.pos()
                self._swipe_dragging = False

        elif event_type == QEvent.MouseMove:
            if (
                self._swipe_start is not None
                and event.buttons() & Qt.LeftButton
            ):
                dx = event.pos().x() - self._swipe_start.x()
                dy = event.pos().y() - self._swipe_start.y()

                if not self._swipe_dragging:
                    horizontal = abs(dx) > abs(dy) * 1.25
                    if horizontal and abs(dx) >= self._DRAG_THRESHOLD:
                        self._swipe_dragging = True

                if self._swipe_dragging:
                    return True

        elif event_type == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton and self._swipe_start is not None:
                dx = event.pos().x() - self._swipe_start.x()
                dy = event.pos().y() - self._swipe_start.y()

                if (
                    abs(dx) >= self._DRAG_THRESHOLD
                    and abs(dx) > abs(dy) * 1.25
                ):
                    # Dragging left moves to the next tab; dragging right moves
                    # to the previous tab.
                    self._change_tab_from_direction(-1 if dx > 0 else 1)
                    self._reset_swipe()
                    return True

                self._reset_swipe()

        return super().eventFilter(watched, event)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, k8s_tab_titles=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(460, 540)
        apply_qss_to(self)
        settings = load_settings()
        self._k8s_titles = list(k8s_tab_titles or [])
        self._hidden = set(settings.get("k8s_hidden_tabs", []))
        self._lock = security.get_lock_settings()
        self._pending_pin = None
        self._webapp_username = str(settings.get("webapp_username", ""))
        self._webapp_enabled = bool(settings.get("webapp_enabled", False))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)

        title = QLabel("⚙  Settings")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setStyleSheet(f"color: {T['TEXT_PRIMARY']};")
        lay.addWidget(title)

        tabs = SwipeTabWidget()
        tabs.addTab(self._build_security_tab(), " 🔒  Security ")
        tabs.addTab(self._build_k8s_tab(), " ⎈  Kubernetes Tabs ")
        tabs.addTab(self._build_ai_tab(), " 🤖  AI ")
        tabs.addTab(self._build_webapp_tab(), " 🌐  Web App ")
        lay.addWidget(tabs, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Save")
        btns.button(QDialogButtonBox.Ok).setObjectName("primary")
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _build_security_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.setContentsMargins(4, 14, 4, 4)

        self.lock_chk = QCheckBox("Require a PIN to open this app")
        self.lock_chk.setChecked(self._lock["enabled"])
        self.lock_chk.toggled.connect(self._on_lock_toggled)
        v.addWidget(self.lock_chk)

        desc = QLabel("Locks the app on launch, and again after a period of inactivity.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 12px;")
        v.addWidget(desc)
        v.addSpacing(4)

        self.pin_btn = QPushButton(
            "Change PIN…" if self._lock["pin_hash"] else "Set PIN…"
        )
        self.pin_btn.clicked.connect(self._on_set_pin)
        v.addWidget(self.pin_btn)

        self.pin_status = QLabel(
            "PIN is set." if self._lock["pin_hash"] else "No PIN set yet."
        )
        self.pin_status.setStyleSheet(
            f"color: {T['TEXT_DIM']}; font-size: 12px;"
        )
        v.addWidget(self.pin_status)
        v.addSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel("Auto-lock after"))
        self.autolock_combo = QComboBox()
        for label, mins in _AUTOLOCK_OPTIONS:
            self.autolock_combo.addItem(label, mins)
        idx = self.autolock_combo.findData(self._lock["autolock_minutes"])
        self.autolock_combo.setCurrentIndex(idx if idx >= 0 else 2)
        row.addWidget(self.autolock_combo)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()

        self._update_security_enabled_state()
        return w

    def _on_lock_toggled(self, checked):
        if checked and not self._lock["pin_hash"] and not self._pending_pin:
            self._on_set_pin()
            if not self._pending_pin:
                self.lock_chk.blockSignals(True)
                self.lock_chk.setChecked(False)
                self.lock_chk.blockSignals(False)
        self._update_security_enabled_state()

    def _update_security_enabled_state(self):
        self.autolock_combo.setEnabled(self.lock_chk.isChecked())

    def _on_set_pin(self):
        dlg = SetPinDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._pending_pin = dlg.pin_value()
            self.pin_status.setText("PIN is set.")
            self.pin_btn.setText("Change PIN…")
            if not self.lock_chk.isChecked():
                self.lock_chk.blockSignals(True)
                self.lock_chk.setChecked(True)
                self.lock_chk.blockSignals(False)
                self._update_security_enabled_state()

    def _build_k8s_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(6)
        v.setContentsMargins(4, 14, 4, 4)

        desc = QLabel("Choose which Kubernetes sub-tabs are visible.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 12px;")
        v.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setSpacing(4)
        iv.setContentsMargins(2, 6, 2, 6)
        self._k8s_checks = {}

        for title in self._k8s_titles:
            chk = QCheckBox(title.strip())
            chk.setChecked(title not in self._hidden)
            iv.addWidget(chk)
            self._k8s_checks[title] = chk

        iv.addStretch()
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        v.addSpacing(4)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {T['BORDER']};")
        v.addWidget(line)
        v.addSpacing(4)

        protected_lbl = QLabel("Protected namespaces (Ops Mind)")
        protected_lbl.setStyleSheet(
            f"color: {T['TEXT_PRIMARY']}; font-weight: 600;"
        )
        v.addWidget(protected_lbl)

        protected_desc = QLabel(
            "Comma-separated name fragments. When the AI Kubernetes Operations "
            "panel targets a namespace matching one of these (e.g. \"mcp\" "
            "matches \"mcp-prod-eks\"), scale requests require confirmation "
            "just like delete already does. Restart always confirms."
        )
        protected_desc.setWordWrap(True)
        protected_desc.setStyleSheet(
            f"color: {T['TEXT_MUTED']}; font-size: 12px;"
        )
        v.addWidget(protected_desc)

        self.protected_ns_edit = QLineEdit()
        self.protected_ns_edit.setText(", ".join(k8s_ai_ops.get_protected_namespaces()))
        self.protected_ns_edit.setPlaceholderText("prod, production, mcp")
        v.addWidget(self.protected_ns_edit)
        return w

    def _build_ai_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.setContentsMargins(4, 14, 4, 4)

        desc = QLabel(
            "Used by the ✨ Explain button in pod log/exec views to get an AI "
            "diagnosis of crashes and errors. Pick a provider, choose (or type) "
            "a model, and paste the matching API key — each is stored "
            "per-provider and sent only to that provider's own API."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 12px;")
        v.addWidget(desc)

        ai_settings = ai_assist.get_ai_settings()
        self._ai_keys = dict(ai_settings["api_keys"])
        self._ai_models = dict(ai_settings["models"])
        self._current_provider_id = None

        v.addSpacing(4)
        v.addWidget(QLabel("Provider"))
        self.provider_combo = QComboBox()
        for pid, info in ai_assist.PROVIDERS.items():
            self.provider_combo.addItem(info["label"], pid)
        v.addWidget(self.provider_combo)

        v.addWidget(QLabel("Model"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        v.addWidget(self.model_combo)

        v.addWidget(QLabel("API key"))
        row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        row.addWidget(self.api_key_edit, 1)

        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setFixedWidth(60)
        self.show_key_btn.toggled.connect(self._on_toggle_show_key)
        row.addWidget(self.show_key_btn)
        v.addLayout(row)

        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        idx = self.provider_combo.findData(ai_settings["provider"])
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        v.addStretch()
        return w

    def _on_provider_changed(self, _index):
        if self._current_provider_id is not None:
            self._ai_keys[self._current_provider_id] = self.api_key_edit.text()
            self._ai_models[self._current_provider_id] = self.model_combo.currentText()

        pid = self.provider_combo.currentData()
        info = ai_assist.PROVIDERS[pid]
        self._current_provider_id = pid

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(info["model_samples"])
        current_model = self._ai_models.get(pid) or info["default_model"]
        model_idx = self.model_combo.findText(current_model)
        if model_idx >= 0:
            self.model_combo.setCurrentIndex(model_idx)
        else:
            self.model_combo.setEditText(current_model)
        self.model_combo.blockSignals(False)

        self.api_key_edit.setText(self._ai_keys.get(pid, ""))
        self.api_key_edit.setPlaceholderText(info["key_placeholder"])

    def _on_toggle_show_key(self, checked):
        self.api_key_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )
        self.show_key_btn.setText("Hide" if checked else "Show")

    def _build_webapp_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.setContentsMargins(4, 14, 4, 4)

        self.webapp_enable_chk = QCheckBox("Enable the local web dashboard")
        self.webapp_enable_chk.setChecked(self._webapp_enabled)
        v.addWidget(self.webapp_enable_chk)

        desc = QLabel(
            "Optional local web dashboard. It is disabled by default and binds "
            "only to 127.0.0.1 when enabled. It reuses the current SSH connection."
        )        v.addWidget(desc)
        v.addSpacing(6)

        v.addWidget(QLabel("Web App username"))
        self.web_username_edit = QLineEdit(self._webapp_username)
        self.web_username_edit.setPlaceholderText("admin")
        v.addWidget(self.web_username_edit)

        v.addWidget(QLabel("Web App password"))
        row = QHBoxLayout()
        self.web_password_edit = QLineEdit()
        self.web_password_edit.setEchoMode(QLineEdit.Password)
        self.web_password_edit.setPlaceholderText("Leave blank to keep the stored password")
        row.addWidget(self.web_password_edit, 1)

        self.show_web_password_btn = QPushButton("Show")
        self.show_web_password_btn.setCheckable(True)
        self.show_web_password_btn.setFixedWidth(60)
        self.show_web_password_btn.toggled.connect(self._on_toggle_show_web_password)
        row.addWidget(self.show_web_password_btn)
        v.addLayout(row)

        try:
            from webapp import get_server_url
            login_url = get_server_url()
        except (ImportError, AttributeError):
            login_url = "http://127.0.0.1:8000"

        self.webapp_link = QLabel(
            f'<a href="{login_url}">🔗 Open Web App Login</a>'
        )
        self.webapp_link.setOpenExternalLinks(True)
        self.webapp_link.setStyleSheet(f"color: {T['ACCENT']};")
        self.webapp_link.setToolTip(login_url)
        v.addWidget(self.webapp_link)

        self.webapp_url_label = QLabel(login_url)
        self.webapp_url_label.setStyleSheet(
            f"color: {T['TEXT_DIM']}; font-size: 12px;"
        )
        v.addWidget(self.webapp_url_label)
        v.addStretch()
        return w

    def _on_toggle_show_web_password(self, checked):
        self.web_password_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )
        self.show_web_password_btn.setText("Hide" if checked else "Show")

    def _on_save(self):
        if self.lock_chk.isChecked():
            if self._pending_pin:
                security.set_pin(
                    self._pending_pin,
                    self.autolock_combo.currentData(),
                )
            elif self._lock["pin_hash"]:
                security.save_lock_settings(
                    enabled=True,
                    autolock_minutes=self.autolock_combo.currentData(),
                )
            else:
                security.disable_lock()
        else:
            security.save_lock_settings(enabled=False)

        save_settings(k8s_hidden_tabs=self.hidden_k8s_tabs())
        k8s_ai_ops.save_protected_namespaces(
            [p.strip() for p in self.protected_ns_edit.text().split(",")]
        )
        self._ai_keys[self._current_provider_id] = self.api_key_edit.text()
        self._ai_models[self._current_provider_id] = self.model_combo.currentText()
        ai_assist.save_ai_settings(
            self.provider_combo.currentData(),
            self._ai_keys,
            self._ai_models,
        )
        webapp_extra = {
            "webapp_enabled": self.webapp_enable_chk.isChecked(),
            "webapp_username": self.web_username_edit.text().strip(),
        }
        new_web_password = self.web_password_edit.text()
        if new_web_password:
            from webapp.server import hash_web_password
            salt, digest = hash_web_password(new_web_password)
            webapp_extra.update({
                "webapp_password_salt": salt,
                "webapp_password_hash": digest,
                "webapp_password": "",
            })
        save_settings(**webapp_extra)

        try:
            from webapp import app as webapp_app
            main_window = self.parent()
            if self.webapp_enable_chk.isChecked():
                webapp_app.start_server(lambda: getattr(main_window, "ssh", None))
            else:
                webapp_app.stop_server()
        except Exception:
            pass
        self.accept()

    def hidden_k8s_tabs(self):
        return [t for t, chk in self._k8s_checks.items() if not chk.isChecked()]
