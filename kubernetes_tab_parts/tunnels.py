from .common import *


class KubernetesTunnelsMixin:
  def _filter_tunnel_services(self, _text=None):
    """
    Filter tunnel services by service name, namespace or port, AND by
    the Active/Inactive status toggle. Both conditions must pass for a
    row to be shown. Preserves the checkbox state.

    `_text` is accepted (and ignored) so this can be connected directly
    to QLineEdit.textChanged as well as called with no arguments from
    the status-toggle handler and after a status refresh.
    """
    text = self.tunnel_search.text().strip().lower()

    for i in range(self.tunnel_list.count()):
      item = self.tunnel_list.item(i)

      svc = item.data(Qt.UserRole)
      if svc is None:
        continue

      searchable = (
        f"{svc['name']} "
        f"{svc['namespace']} "
        f"{svc['port']}"
      ).lower()
      text_match = text in searchable

      exposed = item.data(self.TUNNEL_STATUS_ROLE)
      if self._tunnel_status_filter == "active":
        status_match = exposed is True
      elif self._tunnel_status_filter == "inactive":
        status_match = exposed is False
      else:
        status_match = True

      item.setHidden(not (text_match and status_match))


  def _on_tunnel_status_filter_clicked(self, btn):
    self._tunnel_status_filter = self._tunnel_filter_keys.get(btn, "all")
    self._filter_tunnel_services()

  # ── Namespace helpers ─────────────────────────────────────

  def _format_tunnel_label(self, svc: dict, glyph: str) -> str:
    max_name, max_ns = self._tunnel_col_widths
    return (
      f"{glyph} "
      f"{svc['name']:<{max_name}}"
      f"{'ns/' + svc['namespace']:<{max_ns}}"
      f" : {svc['container_port']}"
      f" → {svc['port']}"
    )


  def _open_manage_tunnel_services(self):
    """Open the card-based dialog for adding/editing/removing tunnel
    services on the connected VM's CSV. Reloads the checklist from the
    VM afterwards so it reflects whatever was actually saved (rather
    than just trusting the dialog's in-memory copy)."""
    if not self.ssh:
      QMessageBox.information(
        self, "Not connected",
        "Connect to a VM first to manage its tunnel services."
      )
      return
    dlg = ManageTunnelServicesDialog(
      self.ssh, self._tunnel_services, self._tunnel_csv_path,
      namespaces=self._namespaces, parent=self,
    )
    dlg.services_saved.connect(lambda _: self._load_tunnel_csv())
    dlg.exec_()


  def _change_tunnel_csv_path(self):
    """Let the user point the Tunnels tab at a different remote CSV
    (e.g. their own file instead of the shared team default), and
    remember the choice across restarts."""
    path, ok = QInputDialog.getText(
      self, "Change Tunnel Services File",
      "Remote CSV path (on the connected VM):",
      QLineEdit.Normal, self._tunnel_csv_path,
    )
    if not ok:
      return
    path = path.strip()
    if not path or path == self._tunnel_csv_path:
      return
    self._tunnel_csv_path = path
    self.tunnel_path_lbl.setText(f" {self._tunnel_csv_path} (on VM)")
    save_settings(tunnel_csv_path=self._tunnel_csv_path)
    if self.ssh:
      self._load_tunnel_csv()


  def _load_tunnel_csv(self):
    """Load tunnel services from the currently connected VM."""

    self.tunnel_list.blockSignals(True)
    self.tunnel_list.clear()
    self._tunnel_services = []

    # No VM connected
    if not self.ssh:
      self.tunnel_cmd_preview.clear()
      self.tunnel_list.blockSignals(False)
      return

    # Load services from the connected VM
    self._tunnel_services = load_tunnel_services(
      self.ssh,
      self._tunnel_csv_path
    )

    if not self._tunnel_services:
      item = QListWidgetItem("(No tunnel services found on the connected VM)")
      item.setFlags(Qt.NoItemFlags)
      item.setForeground(QColor(T["TEXT_MUTED"]))
      self.tunnel_list.addItem(item)
    else:
      # Use the system's fixed-width font
      font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
      font.setPointSize(10)

      # Determine column widths (shared with _refresh_tunnel_status
      # so updating the status glyph later doesn't reflow anything)
      max_name = max(len(svc["name"]) for svc in self._tunnel_services) + 4
      max_ns = max(len(f"ns/{svc['namespace']}") for svc in self._tunnel_services) + 4
      self._tunnel_col_widths = (max_name, max_ns)

      for svc in self._tunnel_services:
        label = self._format_tunnel_label(svc, self.STATUS_UNKNOWN)

        item = QListWidgetItem(label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        item.setData(Qt.UserRole, svc)
        item.setData(self.TUNNEL_STATUS_ROLE, None)
        item.setFont(font)
        item.setForeground(QColor(T["TEXT_MUTED"]))
        item.setToolTip("Checking whether this port is exposed on the VM…")

        self.tunnel_list.addItem(item)

    self.tunnel_list.blockSignals(False)
    self._update_tunnel_cmd_preview()
    self._filter_tunnel_services()
    self._refresh_tunnel_status()


  def _refresh_tunnel_status(self):
    """Check, in a single SSH round-trip, which configured local ports
    are currently listening on the VM — i.e. whether each service's
    'kubectl port-forward' is actually up right now — and update the
    checklist with a / status glyph per row."""
    if not self.ssh or not self._tunnel_services:
      return
    cmd = "ss -ltn 2>/dev/null | awk 'NR>1{print $4}'"
    self._run_cmd(cmd, self._on_tunnel_status_result)


  def _on_tunnel_status_result(self, out: str):
    listening_ports = set()
    for line in out.splitlines():
      line = line.strip()
      if not line or ":" not in line:
        continue
      port_s = line.rsplit(":", 1)[-1]
      if port_s.isdigit():
        listening_ports.add(int(port_s))

    for i in range(self.tunnel_list.count()):
      item = self.tunnel_list.item(i)
      svc = item.data(Qt.UserRole)
      if not svc:
        continue
      exposed = svc["port"] in listening_ports
      glyph  = self.STATUS_UP if exposed else self.STATUS_DOWN
      item.setText(self._format_tunnel_label(svc, glyph))
      item.setData(self.TUNNEL_STATUS_ROLE, exposed)
      item.setForeground(QColor(T["SUCCESS"] if exposed else T["DANGER"]))
      item.setToolTip(
        "Port {} is {} on the VM.".format(
          svc["port"], "listening (exposed)" if exposed else "NOT listening"
        )
      )

    # Statuses just changed — re-apply the Active/Inactive toggle (and
    # the text search) now that they're known, rather than waiting for
    # the user to touch the search box again.
    self._filter_tunnel_services()


  def _set_all_tunnel_checks(self, checked: bool):
    """Check/uncheck every currently VISIBLE row — i.e. respects
    whatever the search box and Active/Inactive toggle are currently
    hiding, rather than reaching through the filter to rows the user
    can't see."""
    state = Qt.Checked if checked else Qt.Unchecked
    self.tunnel_list.blockSignals(True)
    for i in range(self.tunnel_list.count()):
      item = self.tunnel_list.item(i)
      if item.isHidden():
        continue
      if item.flags() & Qt.ItemIsUserCheckable:
        item.setCheckState(state)
    self.tunnel_list.blockSignals(False)
    self._update_tunnel_cmd_preview()


  def _selected_tunnel_services(self) -> list:
    selected = []
    for i in range(self.tunnel_list.count()):
      item = self.tunnel_list.item(i)
      if (item.flags() & Qt.ItemIsUserCheckable) and item.checkState() == Qt.Checked:
        selected.append(item.data(Qt.UserRole))
    return selected


  def _build_tunnel_cmd(self, services: list):
    """Returns (cmd_list, None) on success or (None, error_message) on failure."""
    if not services:
      return None, "Select at least one service to tunnel."
    if not self._conn_host or not self._conn_user:
      return None, "Connect to an instance first."
    if not self._conn_pem:
      return None, "A private-key (.pem) connection is required for tunnelling."

    seen_ports = {}
    forwards = []
    for svc in services:
      port = svc["port"]
      if port in seen_ports and seen_ports[port] != svc["name"]:
        return None, (f"Port {port} is used by both '{seen_ports[port]}' and "
               f"'{svc['name']}' — can't forward the same local port twice.")
      seen_ports[port] = svc["name"]
      forwards += ["-L", f"{port}:127.0.0.1:{port}"]

    cmd = ["ssh", "-nNT"] + forwards
    if self._conn_port and int(self._conn_port) != 22:
      cmd += ["-p", str(self._conn_port)]
    cmd += ["-i", self._conn_pem, f"{self._conn_user}@{self._conn_host}"]
    return cmd, None


  def _update_tunnel_cmd_preview(self, *_):
    services = self._selected_tunnel_services()
    cmd, err = self._build_tunnel_cmd(services)
    self.tunnel_cmd_preview.setText(" ".join(cmd) if cmd else (err or ""))


  def _start_tunnel(self):
    if self._tunnel_process is not None and self._tunnel_process.state() != QProcess.NotRunning:
      QMessageBox.information(self, "Tunnel already running",
                  "Stop the current tunnel before starting a new one.")
      return

    services = self._selected_tunnel_services()
    cmd, err = self._build_tunnel_cmd(services)
    if not cmd:
      QMessageBox.warning(self, "Can't start tunnel", err)
      return

    self.tunnel_log.clear()
    append_terminal_html(self.tunnel_log, f"<span style='color:{T['ACCENT2']}'>$ {self._esc(' '.join(cmd))}</span>")

    proc = QProcess(self)
    proc.setProcessChannelMode(QProcess.MergedChannels)
    proc.readyReadStandardOutput.connect(lambda: self._on_tunnel_output(proc))
    proc.errorOccurred.connect(self._on_tunnel_error)
    proc.finished.connect(self._on_tunnel_finished)
    proc.start(cmd[0], cmd[1:])
    self._tunnel_process = proc

    self.tunnel_start_btn.setEnabled(False)
    self.tunnel_stop_btn.setEnabled(True)
    self.tunnel_status_lbl.setText(f"● Tunnelling {len(services)} service(s)")
    self.tunnel_status_lbl.setStyleSheet(f"color: {T['SUCCESS']}; font-size: 12px;")


  def _stop_tunnel(self):
    if self._tunnel_process is not None and self._tunnel_process.state() != QProcess.NotRunning:
      self._tunnel_process.terminate()
      if not self._tunnel_process.waitForFinished(2000):
        self._tunnel_process.kill()
        self._tunnel_process.waitForFinished(1000)
    # _on_tunnel_finished (connected above) resets buttons/status when the
    # process actually exits; if there was never a process, reset here.
    if self._tunnel_process is None:
      self.tunnel_start_btn.setEnabled(True)
      self.tunnel_stop_btn.setEnabled(False)
      self.tunnel_status_lbl.setText("● Not tunnelling")
      self.tunnel_status_lbl.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 12px;")


  def _on_ports_killed(self, out):
    if out.strip():
      append_terminal_text(self.tunnel_log, out)

    self._refresh_tunnel_status()


  def _kill_selected_ports(self):
    if not self.ssh:
      QMessageBox.warning(self, "Not connected", "Connect to an instance first.")
      return
    services = self._selected_tunnel_services()
    if not services:
      QMessageBox.warning(
        self,
        "No services selected",
        "Select one or more services first."
      )
      return
    ports = [str(svc["port"]) for svc in services]
    # Kill anything listening on the selected ports
    cmd = " ; ".join(
      [
        f"pid=$(lsof -ti:{port} 2>/dev/null); "
        f'[ -n "$pid" ] && kill -9 $pid || echo "Nothing running on {port}"'
        for port in ports
      ]
    )
    cmd = f"bash -lc {shlex.quote(cmd)}"
    append_terminal_html(
      self.tunnel_log,
      f"<span style='color:{T['ACCENT2']}'>$ {self._esc(cmd)}</span>"
    )
    self._run_cmd(cmd, self._on_ports_killed)


  def _on_tunnel_output(self, proc):
    data = bytes(proc.readAllStandardOutput()).decode(errors="replace")
    if data:
      append_terminal_text(self.tunnel_log, data)


  def _on_tunnel_error(self, error):
    append_terminal_html(self.tunnel_log, f"<span style='color:{T['DANGER']}'>[process error: {error}]</span>")


  def _on_tunnel_finished(self, exit_code, _exit_status):
    color = T['SUCCESS'] if exit_code == 0 else T['DANGER']
    append_terminal_html(self.tunnel_log, f"<span style='color:{color}'>[tunnel closed, exit code {exit_code}]</span>")
    self.tunnel_start_btn.setEnabled(True)
    self.tunnel_stop_btn.setEnabled(False)
    self.tunnel_status_lbl.setText("● Not tunnelling")
    self.tunnel_status_lbl.setStyleSheet(f"color: {T['TEXT_MUTED']}; font-size: 12px;")
    self._tunnel_process = None

  # ── Remote kubectl port-forward restart ───────────────────
  # Distinct from the SSH -L tunnel above: this runs 'kubectl port-forward'
  # directly on the connected VM, in the exact format:
  #  nohup kubectl -n <namespace> port-forward svc/<name> <port>:<port> &
  # Supports restarting several services in one go.

  def _build_kubectl_tunnel_restart_cmd(self, services: list) -> str:
    """Kill whatever's already on the port, then relaunch — mirrors the
    kill_kubectl_port.sh + nohup pattern used by the real restart script."""
    cmds = []

    for svc in services:
      name = svc["name"]
      port = svc["port"]
      container_port = svc.get("container_port", port)
      ns = svc["namespace"]

      cmds.append(
        f'pid=$(lsof -ti:{port} 2>/dev/null); [ -n "$pid" ] && kill -9 $pid'
      )
      cmds.append(
        "nohup kubectl {} -n {} port-forward svc/{} {}:{} > /dev/null 2>&1 &".format(
          self._context_flag(),
          shlex.quote(ns),
          shlex.quote(name),
          int(port),
          int(container_port),
        )
      )
    # ';' not '&&' — the kill script may exit nonzero if nothing was listening
    inner = " ; ".join(cmds)
    # exec_command() opens a non-login shell, which skips /etc/profile —
    # exactly where kubectl's PATH entry usually lives (Homebrew, snap,
    # etc.). "bash -lc" forces a login shell so those get sourced.
    return f"bash -lc {shlex.quote(inner)}"


  def _restart_kubectl_tunnels(self):
    if not self.ssh:
      QMessageBox.warning(self, "Not connected", "Connect to an instance first.")
      return

    services = self._selected_tunnel_services()
    if not services:
      QMessageBox.warning(self, "No services selected",
                "Check one or more services below to restart their tunnel.")
      return

    # Each service's restart is an independent SSH command (kill-port +
    # nohup port-forward), so there's no dependency between them — but
    # each one's CommandWorker opens its own channel(s) on the *same*
    # SSH transport, and sshd caps how many of those can be open at
    # once (MaxSessions, commonly 10). Firing every selected service at
    # once used to blow past that ceiling as soon as more than a
    # handful were selected, and every worker beyond the limit failed
    # with ChannelException/"Unable to open channel." Instead, queue
    # everything and keep only MAX_CONCURRENT_TUNNEL_RESTARTS workers
    # in flight; each finished worker pulls the next one off the queue.
    self._tunnel_restart_queue  = list(services)
    self._tunnel_restart_pending = len(services)
    self._tunnel_restart_failed  = []
    self._tunnel_restart_inflight = 0

    self.tunnel_restart_btn.setEnabled(False)
    self.progress.show()

    for _ in range(min(self.MAX_CONCURRENT_TUNNEL_RESTARTS, len(self._tunnel_restart_queue))):
      self._start_next_tunnel_restart()


  def _start_next_tunnel_restart(self):
    if not self._tunnel_restart_queue:
      return
    service = self._tunnel_restart_queue.pop(0)
    self._tunnel_restart_inflight += 1

    cmd = self._build_kubectl_tunnel_restart_cmd([service]) # single-service cmd
    append_terminal_html(
      self.tunnel_log,
      f"<span style='color:{T['ACCENT2']}'>$ {self._esc(cmd)}</span>"
    )
    worker = CommandWorker(self.ssh, cmd)
    worker.done.connect(lambda out, svc=service: self._on_tunnel_step_done(svc, out))
    worker.error.connect(lambda err, svc=service: self._on_tunnel_step_error(svc, err))
    track_worker(self._workers, worker)
    worker.start()


  def _on_tunnel_step_done(self, service, output):
    append_terminal_html(
      self.tunnel_log,
      f"<span style='color:{T['SUCCESS']}'> {self._esc(service['name'])}</span>"
    )
    self._on_tunnel_step_finished()


  def _on_tunnel_step_error(self, service, err):
    self._tunnel_restart_failed.append(service['name'])
    append_terminal_html(
      self.tunnel_log,
      f"<span style='color:{T['DANGER']}'> {self._esc(service['name'])}: {self._esc(str(err))}</span>"
    )
    self._on_tunnel_step_finished()


  def _on_tunnel_step_finished(self):
    # Workers finish in whatever order the remote shell happens to
    # complete them, not the order they were started. Each completion
    # frees up one of the MAX_CONCURRENT_TUNNEL_RESTARTS slots, so pull
    # the next queued service (if any) in before checking whether the
    # whole batch is done.
    self._tunnel_restart_inflight -= 1
    self._tunnel_restart_pending -= 1
    if self._tunnel_restart_queue:
      self._start_next_tunnel_restart()
    elif self._tunnel_restart_pending <= 0:
      self._finish_kubectl_tunnel_restarts()


  def _finish_kubectl_tunnel_restarts(self):
    if self._tunnel_restart_failed:
      self._on_kubectl_tunnel_restart_error(
        f"{len(self._tunnel_restart_failed)} service(s) failed: {', '.join(self._tunnel_restart_failed)}"
      )
    else:
      self._on_kubectl_tunnel_restart_done("all tunnels restarted")


  def _on_kubectl_tunnel_restart_done(self, out: str):
    self.progress.hide()
    self.tunnel_restart_btn.setEnabled(True)
    if out.strip():
      append_terminal_text(self.tunnel_log, out)
    # Give kubectl a moment to bind, then check what's actually listening.
    QTimer.singleShot(1200, self._refresh_tunnel_status)


  def _on_kubectl_tunnel_restart_error(self, err: str):
    # Even if this fires (e.g. a slow-starting kubectl, or any other
    # transient hiccup), the button must never stay stuck disabled, and
    # we should still check whether the tunnel actually came up.
    self.progress.hide()
    self.tunnel_restart_btn.setEnabled(True)
    append_terminal_html(
      self.tunnel_log,
      f"<span style='color:{T['DANGER']}'>[error] {self._esc(err)}</span>"
    )
    QTimer.singleShot(1200, self._refresh_tunnel_status)

  # ── Worker runner ─────────────────────────────────────────

