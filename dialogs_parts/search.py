from .file_exec import _ExecStreamWorker
from .common import *

class SearchDialog(QDialog):
  """Search file contents (grep) and filenames (find) on the remote host."""

  navigate = pyqtSignal(str)

  def __init__(self, parent, ssh, start_path: str = "/"):
    super().__init__(parent)
    self._ssh    = ssh
    self._start_path = start_path
    self._worker   = None

    self.setWindowTitle("Search Remote")
    self.resize(820, 560)
    apply_qss_to(self)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    # ── Search bar ────────────────────────────────────────
    top = QWidget()
    top.setFixedHeight(52)
    top.setStyleSheet(
      f"background: {T['BG_PANEL']}; border-bottom: 1px solid {T['BORDER']};"
    )
    tb = QHBoxLayout(top)
    tb.setContentsMargins(12, 0, 12, 0)
    tb.setSpacing(8)

    self._mode_combo = QComboBox()
    self._mode_combo.addItems(["Content (grep)", "Filename (find)"])
    self._mode_combo.setFixedWidth(150)
    self._mode_combo.currentIndexChanged.connect(self._on_mode_change)
    tb.addWidget(self._mode_combo)

    self._query_inp = QLineEdit()
    self._query_inp.setPlaceholderText("Search pattern…")
    self._query_inp.setFont(monospace_font(12))
    self._query_inp.returnPressed.connect(self._search)
    tb.addWidget(self._query_inp, 1)

    tb.addWidget(QLabel("In:"))
    self._path_inp = QLineEdit(start_path)
    self._path_inp.setFixedWidth(200)
    tb.addWidget(self._path_inp)

    self._case_chk = QCheckBox("Case")
    self._case_chk.setStyleSheet(f"color: {T['TEXT_DIM']};")
    tb.addWidget(self._case_chk)

    self._regex_chk = QCheckBox("Regex")
    self._regex_chk.setStyleSheet(f"color: {T['TEXT_DIM']};")
    tb.addWidget(self._regex_chk)

    self._search_btn = icon_button(" Search")
    self._search_btn.setObjectName("primary")
    self._search_btn.setFixedWidth(100)
    self._search_btn.clicked.connect(self._search)
    tb.addWidget(self._search_btn)

    self._stop_btn = QPushButton("■ Stop")
    self._stop_btn.setObjectName("danger")
    self._stop_btn.setFixedWidth(80)
    self._stop_btn.setEnabled(False)
    self._stop_btn.clicked.connect(self._stop)
    tb.addWidget(self._stop_btn)
    lay.addWidget(top)

    # ── Options row ───────────────────────────────────────
    self._opts_row = QWidget()
    self._opts_row.setFixedHeight(36)
    self._opts_row.setStyleSheet(
      f"background: {T['BG_DARK']}; border-bottom: 1px solid {T['BORDER']};"
    )
    or_lay = QHBoxLayout(self._opts_row)
    or_lay.setContentsMargins(12, 0, 12, 0)
    or_lay.setSpacing(12)

    or_lay.addWidget(QLabel("File filter:"))
    self._include_inp = QLineEdit("*")
    self._include_inp.setFixedWidth(120)
    self._include_inp.setToolTip("e.g. *.py *.js *.txt")
    or_lay.addWidget(self._include_inp)

    self._recursive_chk = QCheckBox("Recursive")
    self._recursive_chk.setChecked(True)
    self._recursive_chk.setStyleSheet(f"color: {T['TEXT_DIM']};")
    or_lay.addWidget(self._recursive_chk)

    self._hidden_chk = QCheckBox("Include hidden")
    self._hidden_chk.setStyleSheet(f"color: {T['TEXT_DIM']};")
    or_lay.addWidget(self._hidden_chk)

    or_lay.addStretch()
    self._result_count_lbl = QLabel("")
    self._result_count_lbl.setStyleSheet(f"color: {T['TEXT_DIM']}; font-size: 13px;")
    or_lay.addWidget(self._result_count_lbl)
    lay.addWidget(self._opts_row)

    # ── Results tree ──────────────────────────────────────
    self._results = QTreeWidget()
    self._results.setRootIsDecorated(True)
    self._results.setColumnCount(2)
    self._results.setHeaderLabels(["File / Match", "Line"])
    self._results.header().setSectionResizeMode(0, QHeaderView.Stretch)
    self._results.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    self._results.setAlternatingRowColors(True)
    self._results.setFont(monospace_font(11))
    self._results.itemDoubleClicked.connect(self._on_result_dblclick)
    lay.addWidget(self._results, 1)

    # ── Status / progress ─────────────────────────────────
    sb = QWidget()
    sb.setFixedHeight(26)
    sb.setStyleSheet(
      f"background: {T['BG_PANEL']}; border-top: 1px solid {T['BORDER']};"
    )
    sb_lay = QHBoxLayout(sb)
    sb_lay.setContentsMargins(12, 0, 12, 0)
    self._status_lbl = QLabel("Ready")
    self._status_lbl.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 13px;")
    sb_lay.addWidget(self._status_lbl)
    sb_lay.addStretch()
    self._progress = QProgressBar()
    self._progress.setRange(0, 0)
    self._progress.setFixedWidth(120)
    self._progress.setFixedHeight(10)
    self._progress.hide()
    sb_lay.addWidget(self._progress)
    lay.addWidget(sb)

    self._query_inp.setFocus()

  def _on_mode_change(self, idx: int):
    is_grep = idx == 0
    self._opts_row.setVisible(is_grep)
    self._query_inp.setPlaceholderText(
      "Search pattern…" if is_grep else "Filename pattern (e.g. *.log)"
    )

  def _build_grep_cmd(self) -> str:
    q    = self._query_inp.text().strip()
    path  = self._path_inp.text().strip() or "/"
    incl  = self._include_inp.text().strip() or "*"
    flags  = []
    if not self._case_chk.isChecked():
      flags.append("-i")
    if not self._regex_chk.isChecked():
      flags.append("-F")
    if self._recursive_chk.isChecked():
      flags.append("-r")
    flags += ["-n", "--include=" + incl]
    if not self._hidden_chk.isChecked():
      flags.append("--exclude-dir='.*'")

    flag_str = " ".join(flags)
    sq_q   = "'" + q.replace("'", "'\\''") + "'"
    sq_path = "'" + path.replace("'", "'\\''") + "'"
    return f"grep {flag_str} {sq_q} {sq_path} 2>/dev/null | head -500"

  def _build_find_cmd(self) -> str:
    q  = self._query_inp.text().strip()
    path = self._path_inp.text().strip() or "/"
    sq_q  = "'" + q.replace("'", "'\\''") + "'"
    sq_path = "'" + path.replace("'", "'\\''") + "'"
    hidden = "" if self._hidden_chk.isChecked() else r" ! -path '*/.*'"
    return f"find {sq_path}{hidden} -name {sq_q} 2>/dev/null | head -500"

  def _search(self):
    q = self._query_inp.text().strip()
    if not q:
      return
    if self._worker and self._worker.isRunning():
      return

    self._results.clear()
    self._result_count_lbl.setText("")
    self._progress.show()
    self._search_btn.setEnabled(False)
    self._stop_btn.setEnabled(True)
    self._status_lbl.setText("Searching…")

    if self._mode_combo.currentIndex() == 0:
      cmd = self._build_grep_cmd()
      self._worker = _ExecStreamWorker(self._ssh, cmd)
      self._worker.line.connect(self._on_grep_line)
    else:
      cmd = self._build_find_cmd()
      self._worker = _ExecStreamWorker(self._ssh, cmd)
      self._worker.line.connect(self._on_find_line)

    self._worker.error.connect(self._on_error)
    self._worker.finished.connect(self._on_search_done)
    self._worker.start()

  def _stop(self):
    if self._worker and self._worker.isRunning():
      self._worker.request_stop()

  def _on_grep_line(self, line: str):
    parts = line.split(":", 2)
    if len(parts) < 3:
      return
    fpath, lineno, content = parts[0], parts[1], parts[2]

    parent = None
    for i in range(self._results.topLevelItemCount()):
      item = self._results.topLevelItem(i)
      if item.text(0) == fpath:
        parent = item
        break
    if parent is None:
      parent = QTreeWidgetItem([fpath, ""])
      parent.setForeground(0, QColor(T['ACCENT2']))
      parent.setFont(0, monospace_font(11, bold=True))
      parent.setData(0, Qt.UserRole, {"path": fpath})
      self._results.addTopLevelItem(parent)
      parent.setExpanded(True)

    child = QTreeWidgetItem([content.strip(), lineno])
    child.setData(0, Qt.UserRole, {"path": fpath, "line": lineno})
    child.setForeground(1, QColor(T['TEXT_MUTED']))
    parent.addChild(child)
    self._update_count()

  def _on_find_line(self, line: str):
    line = line.strip()
    if not line:
      return
    item = QTreeWidgetItem([line, ""])
    item.setData(0, Qt.UserRole, {"path": line})
    item.setForeground(0, QColor(T['ACCENT2']))
    self._results.addTopLevelItem(item)
    self._update_count()

  def _update_count(self):
    n = self._results.topLevelItemCount()
    self._result_count_lbl.setText(f"{n} file{'s' if n != 1 else ''}")

  def _on_error(self, err: str):
    self._status_lbl.setText(f"Error: {err}")

  def _on_search_done(self, code: int):
    self._progress.hide()
    self._search_btn.setEnabled(True)
    self._stop_btn.setEnabled(False)
    n = self._results.topLevelItemCount()
    self._status_lbl.setText(f"Done — {n} result{'s' if n != 1 else ''}")

  def _on_result_dblclick(self, item, col):
    data = item.data(0, Qt.UserRole)
    if data and "path" in data:
      self.navigate.emit(os.path.dirname(data["path"]) or "/")

