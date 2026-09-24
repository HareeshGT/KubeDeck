from .common import *

class _IconButton(QPushButton):
  """A small flat, round icon-only button used inside the service cards.
  Deliberately not routed through KubernetesTab._toolbar_btn — these live
  inside a QFrame card, not a toolbar, and need to be small and circular
  rather than pill-shaped."""

  def __init__(self, glyph: str, tooltip: str = "", danger: bool = False, parent=None):
    super().__init__(glyph, parent)
    self.setFixedSize(30, 30)
    self.setCursor(Qt.PointingHandCursor)
    if tooltip:
      self.setToolTip(tooltip)
    self._danger = danger
    self._apply_style()

  def _apply_style(self):
    hover_bg = f"rgba(248,113,113,0.15)" if self._danger else T["BG_HOVER"]
    border_hover = T["DANGER"] if self._danger else T["ACCENT"]
    self.setStyleSheet(f"""
      QPushButton {{
        background: transparent; color: {T['TEXT_DIM']};
        border: 1px solid {T['BORDER']}; border-radius: 15px;
        font-size: 13px; padding: 0;
      }}
      QPushButton:hover {{
        background: {hover_bg}; color: {T['TEXT_PRIMARY']};
        border-color: {border_hover};
      }}
    """)

  def refresh_theme(self):
    self._apply_style()


class _ServiceCard(QFrame):
  """A single tunnel service rendered as a friendly card (name, namespace
  badge, port mapping) with edit/delete actions — the row-level building
  block of ManageTunnelServicesDialog's list, styled after the
  NodeCard/badge visual language used elsewhere in the app."""

  edit_clicked  = pyqtSignal(dict)
  delete_clicked = pyqtSignal(dict)

  def __init__(self, svc: dict, parent=None):
    super().__init__(parent)
    self.svc = svc
    self.setObjectName("tunnel_service_card")

    row = QHBoxLayout(self)
    row.setContentsMargins(16, 12, 12, 12)
    row.setSpacing(12)

    icon_lbl = QLabel("")
    icon_lbl.setStyleSheet("font-size: 18px;")
    icon_lbl.setFixedWidth(26)
    row.addWidget(icon_lbl)

    text_col = QVBoxLayout()
    text_col.setSpacing(4)

    name_row = QHBoxLayout()
    name_row.setSpacing(8)
    self.name_lbl = QLabel(svc["name"])
    name_row.addWidget(self.name_lbl)
    self.ns_badge = QLabel(f"ns/{svc.get('namespace') or 'default'}")
    name_row.addWidget(self.ns_badge)
    name_row.addStretch(1)
    text_col.addLayout(name_row)

    self.port_lbl = QLabel(
      f"container : {svc['container_port']}  →  local : {svc['port']}"
    )
    text_col.addWidget(self.port_lbl)

    row.addLayout(text_col, 1)

    self.edit_btn = _IconButton("", "Edit this service")
    self.edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.svc))
    row.addWidget(self.edit_btn)

    self.del_btn = _IconButton("", "Remove this service", danger=True)
    self.del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.svc))
    row.addWidget(self.del_btn)

    self._apply_styles()

  def _apply_styles(self):
    self.setStyleSheet(
      f"QFrame#tunnel_service_card {{ background: {T['BG_ITEM']}; "
      f"border: 1px solid {T['BORDER']}; border-radius: 12px; }} "
      f"QFrame#tunnel_service_card:hover {{ border: 1px solid {T['ACCENT']}; }}"
    )
    self.name_lbl.setStyleSheet(
      f"color: {T['TEXT_PRIMARY']}; font-size: 14px; font-weight: 700;"
    )
    self.ns_badge.setStyleSheet(
      f"background: {T['BG_ITEM_SEL']}; color: {T['TEXT_PRIMARY']}; "
      f"border-radius: 8px; padding: 1px 9px; font-size: 11px; font-weight: 600;"
    )
    self.port_lbl.setStyleSheet(f"color: {T['TEXT_DIM']}; font-size: 12px;")
    self.edit_btn.refresh_theme()
    self.del_btn.refresh_theme()

  def refresh_theme(self):
    self._apply_styles()


def _contains_completer(combo: QComboBox) -> QCompleter:
  """Attach a "contains, not just starts-with" popup completer to an
  editable QComboBox, sharing the combo's own model so it stays in sync
  whenever the combo's items are cleared/reloaded (e.g. after a
  dependent-dropdown query) without needing to be rebuilt.

  Qt's default combo-box completer only matches from the start of the
  string and mostly just auto-fills inline, so typing "api" against
  ["auth-api", "payments-api", "api-gateway"] would show nothing (or at
  best "api-gateway") instead of all three. This switches to
  case-insensitive substring matching with a real dropdown popup of
  every match, which is what you want when picking a k8s service name
  out of a list you didn't choose.
  """
  completer = QCompleter(combo.model(), combo)
  completer.setCaseSensitivity(Qt.CaseInsensitive)
  completer.setFilterMode(Qt.MatchContains)
  completer.setCompletionMode(QCompleter.PopupCompletion)
  combo.setCompleter(completer)
  return completer


class _ServiceFormPanel(QFrame):
  """Inline add/edit form. Shown in place of the card list (via a
  QStackedWidget in the owning dialog) rather than as its own popup
  dialog — keeps the whole flow feeling like one continuous window
  instead of a stack of nested modals.

  Namespace, Service Name, and Container Port are editable QComboBoxes
  rather than plain text fields: Namespace is pre-filled from the
  namespaces KubernetesTab already has cached; picking one queries the
  connected VM for that namespace's services (`kubectl get svc -n ...`)
  to fill Service Name; picking a service queries its actual container
  ports (`kubectl get svc <name> -n <ns>`) to fill Container Port. All
  three stay editable (QComboBox.setEditable) so a service that doesn't
  exist yet can still be typed in by hand — this is convenience
  autocomplete, not a hard constraint tied to what's live on the cluster.
  """

  save_clicked  = pyqtSignal(dict, object)  # (new_data, original_svc_or_None)
  cancel_clicked = pyqtSignal()

  def __init__(self, ssh=None, namespaces=None, parent=None):
    super().__init__(parent)
    self.setObjectName("tunnel_form_panel")
    self._editing  = None
    self.ssh     = ssh
    self._namespaces = list(namespaces or [])
    self._workers  = []

    outer = QVBoxLayout(self)
    outer.setContentsMargins(22, 20, 22, 20)
    outer.setSpacing(10)

    self.heading = QLabel("Add a new service")
    outer.addWidget(self.heading)

    # Namespace first — Service Name's choices depend on it.
    self.ns_input = QComboBox()
    self.ns_input.setEditable(True)
    self.ns_input.setInsertPolicy(QComboBox.NoInsert)
    self.ns_input.addItems(self._namespaces)
    self.ns_input.setCurrentText("default")
    self.ns_input.activated[str].connect(self._on_ns_picked)
    _contains_completer(self.ns_input)

    self.name_input = QComboBox()
    self.name_input.setEditable(True)
    self.name_input.setInsertPolicy(QComboBox.NoInsert)
    self.name_input.lineEdit().setPlaceholderText("e.g. auth-service")
    self.name_input.activated[str].connect(self._on_svc_picked)
    _contains_completer(self.name_input)

    ports_row = QHBoxLayout()
    ports_row.setSpacing(14)

    local_col = QVBoxLayout()
    local_col.setSpacing(4)
    local_lbl = QLabel("LOCAL PORT")
    local_col.addWidget(local_lbl)
    self.local_port_input = QLineEdit()
    self.local_port_input.setPlaceholderText("8080")
    self.local_port_input.setValidator(QIntValidator(1, 65535, self))
    local_col.addWidget(self.local_port_input)
    ports_row.addLayout(local_col)

    container_col = QVBoxLayout()
    container_col.setSpacing(4)
    container_lbl = QLabel("CONTAINER PORT")
    container_col.addWidget(container_lbl)
    self.container_port_input = QComboBox()
    self.container_port_input.setEditable(True)
    self.container_port_input.setInsertPolicy(QComboBox.NoInsert)
    self.container_port_input.lineEdit().setPlaceholderText("defaults to local port")
    self.container_port_input.lineEdit().setValidator(QIntValidator(1, 65535, self))
    _contains_completer(self.container_port_input)
    container_col.addWidget(self.container_port_input)
    ports_row.addLayout(container_col)

    self._field_labels = []
    for label_text, field in [
      ("NAMESPACE",  self.ns_input),
      ("SERVICE NAME", self.name_input),
    ]:
      lbl = QLabel(label_text)
      self._field_labels.append(lbl)
      outer.addWidget(lbl)
      outer.addWidget(field)

    outer.addLayout(ports_row)
    self._field_labels += [local_lbl, container_lbl]

    self.error_lbl = QLabel("")
    self.error_lbl.setWordWrap(True)
    self.error_lbl.hide()
    outer.addWidget(self.error_lbl)

    outer.addStretch(1)

    btn_row = QHBoxLayout()
    btn_row.addStretch(1)
    self.cancel_btn = QPushButton("Cancel")
    self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
    btn_row.addWidget(self.cancel_btn)
    self.save_btn = QPushButton("Add Service")
    self.save_btn.setObjectName("primary")
    self.save_btn.clicked.connect(self._on_save)
    btn_row.addWidget(self.save_btn)
    outer.addLayout(btn_row)

    self._apply_styles()

  def _apply_styles(self):
    self.setStyleSheet(
      f"QFrame#tunnel_form_panel {{ background: {T['BG_PANEL']}; "
      f"border: 1px solid {T['BORDER']}; border-radius: 14px; }}"
    )
    self.heading.setStyleSheet(
      f"color: {T['TEXT_PRIMARY']}; font-size: 15px; font-weight: 700; "
      f"background: transparent;"
    )
    for lbl in self._field_labels:
      lbl.setStyleSheet(
        f"color: {T['TEXT_MUTED']}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 0.8px; background: transparent;"
      )
    self.error_lbl.setStyleSheet(
      f"color: {T['DANGER']}; font-size: 12px; background: transparent;"
    )

  # ── Context from the owning dialog ──────────────────────────
  def set_context(self, ssh, namespaces: list):
    """Called by ManageTunnelServicesDialog whenever it (re)opens, so
    the form always has the current SSH connection and namespace list
    rather than whatever was passed in at construction time."""
    self.ssh = ssh
    self._namespaces = list(namespaces or [])
    current = self.ns_input.currentText()
    self.ns_input.blockSignals(True)
    self.ns_input.clear()
    self.ns_input.addItems(self._namespaces)
    self.ns_input.setCurrentText(current or "default")
    self.ns_input.blockSignals(False)

  # ── Dependent-dropdown queries ───────────────────────────────
  def _run_query(self, cmd: str, callback):
    if not self.ssh:
      return
    worker = CommandWorker(self.ssh, cmd)
    worker.done.connect(callback)
    worker.error.connect(lambda _e: None) # best-effort autocomplete only
    track_worker(self._workers, worker)
    worker.start()

  def _on_ns_picked(self, ns: str):
    self._reload_services(ns.strip())

  def _reload_services(self, ns: str):
    if not ns:
      return
    self._run_query(
      f"kubectl get svc -n {shlex.quote(ns)} "
      f"-o jsonpath='{{.items[*].metadata.name}}' 2>&1",
      self._populate_services,
    )

  def _populate_services(self, out: str):
    names = out.strip().strip("'").split()
    current = self.name_input.currentText()
    self.name_input.blockSignals(True)
    self.name_input.clear()
    self.name_input.addItems(names)
    self.name_input.setCurrentText(current)
    self.name_input.blockSignals(False)

  def _on_svc_picked(self, svc: str):
    svc = svc.strip()
    ns = self.ns_input.currentText().strip()
    if not svc or not ns:
      return
    self._run_query(
      f"kubectl get svc {shlex.quote(svc)} -n {shlex.quote(ns)} "
      f"-o jsonpath='{{.spec.ports[*].port}}' 2>&1",
      self._populate_container_ports,
    )

  def _populate_container_ports(self, out: str):
    ports = out.strip().strip("'").split()
    current = self.container_port_input.currentText()
    self.container_port_input.blockSignals(True)
    self.container_port_input.clear()
    self.container_port_input.addItems(ports)
    if current:
      self.container_port_input.setCurrentText(current)
    elif len(ports) == 1:
      self.container_port_input.setCurrentText(ports[0])
      if not self.local_port_input.text().strip():
        self.local_port_input.setText(ports[0])
    self.container_port_input.blockSignals(False)

  # ── Loading state ────────────────────────────────────────
  def load_for_add(self):
    self._editing = None
    self.heading.setText(" Add a new service")
    self.save_btn.setText("Add Service")
    self.name_input.clearEditText()
    self.name_input.clear()
    self.ns_input.setCurrentText("default")
    self.local_port_input.clear()
    self.container_port_input.clearEditText()
    self.container_port_input.clear()
    self.error_lbl.hide()
    self.name_input.setFocus()
    self._reload_services(self.ns_input.currentText().strip())

  def load_for_edit(self, svc: dict):
    self._editing = svc
    self.heading.setText(f" Edit “{svc['name']}”")
    self.save_btn.setText("Save Changes")
    ns = svc.get("namespace", "") or "default"
    self.ns_input.setCurrentText(ns)
    self.name_input.clear()
    self.name_input.setCurrentText(svc["name"])
    self.local_port_input.setText(str(svc["port"]))
    self.container_port_input.clear()
    self.container_port_input.setCurrentText(str(svc["container_port"]))
    self.error_lbl.hide()
    self.name_input.setFocus()
    self._reload_services(ns)

  def show_error(self, msg: str):
    self.error_lbl.setText(" " + msg)
    self.error_lbl.show()

  def _on_save(self):
    name = self.name_input.currentText().strip()
    ns  = self.ns_input.currentText().strip()
    local_s   = self.local_port_input.text().strip()
    container_s = self.container_port_input.currentText().strip() or local_s

    if not name:
      self.show_error("Service name is required.")
      return
    if not local_s.isdigit():
      self.show_error("Local port must be a number.")
      return
    if not container_s.isdigit():
      self.show_error("Container port must be a number.")
      return

    data = {
      "name": name,
      "namespace": ns,
      "port": int(local_s),
      "container_port": int(container_s),
    }
    self.save_clicked.emit(data, self._editing)


class ManageTunnelServicesDialog(QDialog):
  """Friendly, card-based editor for the tunnel-services CSV that lives on
  the connected VM (see utils.load_tunnel_services / REMOTE_TUNNEL_CSV_PATH).

  Lets the user add new services and edit or remove existing ones without
  ever seeing a raw CSV — changes are staged locally and only written back
  to the VM (as CSV, base64-piped over the existing SSH connection to
  avoid any shell-quoting issues with service names) when "Save to VM" is
  pressed. Emits services_saved(list) with the new full list after a
  successful write so the caller (KubernetesTab) can refresh its own
  checklist from the same data instead of re-reading the file.
  """

  services_saved = pyqtSignal(list)

  def __init__(self, ssh, services: list, csv_path: str, namespaces: list = None, parent=None):
    super().__init__(parent)
    self.ssh = ssh
    self.csv_path = csv_path
    self._services = [dict(s) for s in services]
    self._namespaces = list(namespaces or [])
    self._dirty = False
    self._worker = None

    self.setWindowTitle("Manage Tunnel Services")
    self.setMinimumSize(580, 640)
    apply_qss_to(self)

    outer = QVBoxLayout(self)
    outer.setContentsMargins(24, 22, 24, 18)
    outer.setSpacing(12)

    title = QLabel(" Tunnel Services")
    title.setFont(QFont("Segoe UI", 16, QFont.Bold))
    title.setStyleSheet(f"color: {T['TEXT_PRIMARY']};")
    outer.addWidget(title)

    self.subtitle = QLabel(f"Read from {csv_path} on the connected VM.")
    self.subtitle.setWordWrap(True)
    outer.addWidget(self.subtitle)

    top_row = QHBoxLayout()
    top_row.setSpacing(8)
    self.search = QLineEdit()
    self.search.setPlaceholderText(" Filter services…")
    self.search.setClearButtonEnabled(True)
    self.search.textChanged.connect(self._filter_cards)
    top_row.addWidget(self.search, 1)

    self.add_btn = icon_button(" Add Service")
    self.add_btn.setObjectName("primary")
    self.add_btn.clicked.connect(self._show_add_form)
    top_row.addWidget(self.add_btn)
    outer.addLayout(top_row)

    self.stack = QStackedWidget()

    # ── List page ────────────────────────────────────────
    list_page = QWidget()
    list_lay = QVBoxLayout(list_page)
    list_lay.setContentsMargins(0, 0, 0, 0)
    list_lay.setSpacing(0)

    self.scroll = QScrollArea()
    self.scroll.setWidgetResizable(True)
    self.scroll.setFrameShape(QFrame.NoFrame)
    self.scroll_body = QWidget()
    self.scroll_body.setStyleSheet("background: transparent;")
    self.cards_layout = QVBoxLayout(self.scroll_body)
    self.cards_layout.setContentsMargins(2, 2, 10, 2)
    self.cards_layout.setSpacing(8)
    self.cards_layout.addStretch(1)
    self.scroll.setWidget(self.scroll_body)
    list_lay.addWidget(self.scroll)

    self.empty_lbl = QLabel("No tunnel services yet — click “Add Service” above to create one.")
    self.empty_lbl.setAlignment(Qt.AlignCenter)
    self.empty_lbl.setWordWrap(True)
    self.empty_lbl.hide()
    list_lay.addWidget(self.empty_lbl)

    self.stack.addWidget(list_page)

    # ── Form page ────────────────────────────────────────
    self.form_panel = _ServiceFormPanel(ssh=self.ssh, namespaces=self._namespaces)
    self.form_panel.save_clicked.connect(self._on_form_save)
    self.form_panel.cancel_clicked.connect(self._show_list)
    self.stack.addWidget(self.form_panel)

    outer.addWidget(self.stack, 1)

    footer = QHBoxLayout()
    footer.setSpacing(8)
    self.status_lbl = QLabel("")
    footer.addWidget(self.status_lbl, 1)

    self.close_btn = QPushButton("Close")
    self.close_btn.clicked.connect(self.reject)
    footer.addWidget(self.close_btn)

    self.save_all_btn = icon_button(" Save to VM")
    self.save_all_btn.setObjectName("success")
    self.save_all_btn.clicked.connect(self._save_to_vm)
    footer.addWidget(self.save_all_btn)
    outer.addLayout(footer)

    self._apply_styles()
    self._rebuild_cards()

  def _apply_styles(self):
    self.subtitle.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 12px;")
    self.empty_lbl.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 13px; padding: 40px;")
    self.status_lbl.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 12px;")

  # ── Card list management ─────────────────────────────────
  def _rebuild_cards(self):
    while self.cards_layout.count() > 1:
      item = self.cards_layout.takeAt(0)
      w = item.widget()
      if w:
        w.deleteLater()

    for svc in self._services:
      card = _ServiceCard(svc)
      card.edit_clicked.connect(self._show_edit_form)
      card.delete_clicked.connect(self._delete_service)
      self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    self.empty_lbl.setVisible(not self._services)
    self.scroll.setVisible(bool(self._services))
    self._filter_cards(self.search.text())

  def _filter_cards(self, text):
    text = (text or "").strip().lower()
    for i in range(self.cards_layout.count() - 1):
      card = self.cards_layout.itemAt(i).widget()
      if not isinstance(card, _ServiceCard):
        continue
      svc = card.svc
      haystack = (
        f"{svc['name']} {svc.get('namespace','')} "
        f"{svc['port']} {svc['container_port']}"
      ).lower()
      card.setVisible(text in haystack)

  # ── Add / edit flow ──────────────────────────────────────
  def _show_add_form(self):
    self.form_panel.load_for_add()
    self.stack.setCurrentWidget(self.form_panel)

  def _show_edit_form(self, svc):
    self.form_panel.load_for_edit(svc)
    self.stack.setCurrentWidget(self.form_panel)

  def _show_list(self):
    self.stack.setCurrentIndex(0)

  def _on_form_save(self, data: dict, editing):
    others = [s for s in self._services if s is not editing]

    # Check for an identical service (all fields match)
    if any(s == data for s in others):
      self.form_panel.show_error("This service is already present.")
      return

    # Check for duplicate local port
    if any(s["port"] == data["port"] for s in others):
      self.form_panel.show_error(
        f"Local port {data['port']} is already used by another service."
      )
      return

    if editing is None:
      self._services.append(data)
      self.status_lbl.setText(
        f"Added “{data['name']}” — click Save to VM to apply."
      )
    else:
      idx = self._services.index(editing)
      self._services[idx] = data
      self.status_lbl.setText(
        f"Updated “{data['name']}” — click Save to VM to apply."
      )

    self._dirty = True
    self._rebuild_cards()
    self._show_list()

  def _delete_service(self, svc: dict):
    resp = QMessageBox.question(
      self, "Remove service",
      f"Remove “{svc['name']}” from the tunnel list?",
      QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    )
    if resp != QMessageBox.Yes:
      return
    self._services = [s for s in self._services if s is not svc]
    self._dirty = True
    self.status_lbl.setText(f"Removed “{svc['name']}” — click Save to VM to apply.")
    self._rebuild_cards()

  # ── Persistence ───────────────────────────────────────────
  @staticmethod
  def _services_to_csv(services: list) -> str:
    lines = ["service_name,local_port,container_port,namespace"]
    for s in services:
      lines.append(f"{s['name']},{s['port']},{s['container_port']},{s.get('namespace','')}")
    return "\n".join(lines) + "\n"

  def _save_to_vm(self):
    if not self.ssh:
      QMessageBox.warning(self, "Not connected", "Connect to a VM before saving.")
      return
    if not self._services:
      resp = QMessageBox.question(
        self, "Save empty list?",
        "This will clear all tunnel services on the VM. Continue?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
      )
      if resp != QMessageBox.Yes:
        return

    csv_text = self._services_to_csv(self._services)
    b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")

    # csv_path (REMOTE_TUNNEL_CSV_PATH) starts with '~' by default. Shell
    # tilde-expansion only happens on an *unquoted* leading '~' — once
    # shlex.quote() wraps the path in single quotes (needed so
    # service/namespace text can't break out of the command), '~' is no
    # longer expanded and bash creates/writes a literal directory named
    # "~" inside the SSH session's cwd instead of $HOME. That silently
    # succeeded (no error), so the dialog reported "Saved" while the
    # real ~/.tunnel/tunnel_services.csv (the file load_tunnel_services
    # reads, unquoted, so it *does* expand '~') was never touched —
    # every newly added service looked like it hadn't been saved.
    # Fix: resolve '~' to the actual remote $HOME first, then quote the
    # already-expanded absolute path.
    csv_path = self.csv_path
    if csv_path.startswith("~"):
      with managed_exec_command(self.ssh, "echo $HOME") as (_stdin, _home_out, _stderr):
        home = _home_out.read().decode(errors="replace").strip()
      if home:
        csv_path = home + csv_path[1:]

    remote_dir = os.path.dirname(csv_path) or "."
    cmd = "mkdir -p {d} 2>/dev/null; echo {b64} | base64 -d > {p}".format(
      d=shlex.quote(remote_dir), b64=shlex.quote(b64), p=shlex.quote(csv_path),
    )

    self.save_all_btn.setEnabled(False)
    self.save_all_btn.setText("Saving…")
    self.status_lbl.setText("Writing changes to the VM…")

    worker = CommandWorker(self.ssh, cmd)

    def on_done(_out):
      self.save_all_btn.setEnabled(True)
      self.save_all_btn.setText(" Save to VM")
      self._dirty = False
      self.status_lbl.setText(" Saved to VM.")
      self.services_saved.emit(self._services)

    def on_error(err):
      self.save_all_btn.setEnabled(True)
      self.save_all_btn.setText(" Save to VM")
      self.status_lbl.setText("")
      QMessageBox.critical(self, "Save failed", str(err))

    worker.done.connect(on_done)
    worker.error.connect(on_error)
    self._worker = worker
    worker.start()

  # ── Close handling ────────────────────────────────────────
  def closeEvent(self, event):
    if self._dirty:
      resp = QMessageBox.question(
        self, "Unsaved changes",
        "You have changes that haven't been saved to the VM yet. Close anyway?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
      )
      if resp != QMessageBox.Yes:
        event.ignore()
        return
    super().closeEvent(event)

  def reject(self):
    if self._dirty:
      resp = QMessageBox.question(
        self, "Unsaved changes",
        "You have changes that haven't been saved to the VM yet. Close anyway?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
      )
      if resp != QMessageBox.Yes:
        return
    super().reject()

