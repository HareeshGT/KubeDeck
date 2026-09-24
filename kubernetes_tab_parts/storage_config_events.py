from .common import *


class KubernetesStorageConfigEventsMixin:
  def _load_storage(self, _=None):
    if self._storage_type == "PV":
      self._load_pvs()
    else:
      self._load_pvcs()


  def _load_pvcs(self):
    self._run_cmd(f"kubectl get pvc {self._ns_flag()} -o json 2>&1", self._populate_pvcs)


  def _populate_pvcs(self, out: str):
    self.pvx_list.clear()
    all_ns = (self._current_ns == "(all namespaces)")
    try:
      items = json.loads(out).get("items", [])
    except Exception:
      items = []
    for it in items:
      meta_o = it.get("metadata") or {}
      spec  = it.get("spec") or {}
      status = it.get("status") or {}
      capacity = (status.get("capacity") or {}).get("storage", "-")
      meta = {
        "namespace":   meta_o.get("namespace", ""),
        "name":     meta_o.get("name", ""),
        "status":    status.get("phase", "Unknown"),
        "volume":    spec.get("volumeName", "-") or "-",
        "capacity":   capacity,
        "access_modes": ", ".join(spec.get("accessModes") or []) or "-",
        "storage_class": spec.get("storageClassName", "-") or "-",
        "age":      self._humanize_age(meta_o.get("creationTimestamp", "")),
      }
      item = QListWidgetItem()
      item.setData(Qt.UserRole, {**meta, "kind": "pvc"})
      item.setSizeHint(QSize(0, PVCCardWidget.CARD_HEIGHT))
      self.pvx_list.addItem(item)
      self.pvx_list.setItemWidget(item, PVCCardWidget(meta, all_ns))
    total = len(items)
    color_key = "TEXT_MUTED" if total == 0 else "INFO"
    self._set_count_badge(self.pvx_count_lbl, f"{total} claim{'s' if total != 1 else ''}", color_key)
    self._filter_storage(self.pvx_filter.text())


  def _load_pvs(self):
    # PersistentVolumes are cluster-scoped — no namespace flag applies.
    self._run_cmd("kubectl get pv -o json 2>&1", self._populate_pvs)


  def _populate_pvs(self, out: str):
    self.pvx_list.clear()
    try:
      items = json.loads(out).get("items", [])
    except Exception:
      items = []
    for it in items:
      meta_o = it.get("metadata") or {}
      spec  = it.get("spec") or {}
      status = it.get("status") or {}
      claim_ref = spec.get("claimRef") or {}
      claim = (f"{claim_ref.get('namespace', '')}/{claim_ref.get('name', '')}"
           if claim_ref.get("name") else "-")
      meta = {
        "name":      meta_o.get("name", ""),
        "capacity":    (spec.get("capacity") or {}).get("storage", "-"),
        "access_modes":  ", ".join(spec.get("accessModes") or []) or "-",
        "reclaim_policy": spec.get("persistentVolumeReclaimPolicy", "-") or "-",
        "status":     status.get("phase", "Unknown"),
        "claim":     claim,
        "storage_class": spec.get("storageClassName", "-") or "-",
        "age":      self._humanize_age(meta_o.get("creationTimestamp", "")),
      }
      item = QListWidgetItem()
      item.setData(Qt.UserRole, {**meta, "kind": "pv"})
      item.setSizeHint(QSize(0, PVCardWidget.CARD_HEIGHT))
      self.pvx_list.addItem(item)
      self.pvx_list.setItemWidget(item, PVCardWidget(meta))
    total = len(items)
    color_key = "TEXT_MUTED" if total == 0 else "INFO"
    self._set_count_badge(self.pvx_count_lbl, f"{total} volume{'s' if total != 1 else ''}", color_key)
    self._filter_storage(self.pvx_filter.text())


  def _filter_storage(self, text: str):
    q = text.lower()
    for i in range(self.pvx_list.count()):
      item = self.pvx_list.item(i)
      meta = item.data(Qt.UserRole) or {}
      item.setHidden(q not in meta.get("name", "").lower())


  def _selected_storage(self):
    item = self.pvx_list.currentItem()
    if not item:
      QMessageBox.warning(self, "No selection", "Select a claim or volume first.")
      return None
    return item.data(Qt.UserRole) or {}


  def _on_storage_double_click(self, item):
    meta = item.data(Qt.UserRole) or {}
    kind = "pvc" if meta.get("kind") == "pvc" else "pv"
    self._describe(kind, meta.get("name"), meta.get("namespace") or "default")


  def _on_storage_selection_changed(self, current, previous):
    if previous is not None:
      w = self.pvx_list.itemWidget(previous)
      if w:
        w.set_selected(False)
    if current is not None:
      w = self.pvx_list.itemWidget(current)
      if w:
        w.set_selected(True)


  def _storage_describe(self):
    meta = self._selected_storage()
    if meta:
      kind = "pvc" if meta.get("kind") == "pvc" else "pv"
      self._describe(kind, meta.get("name"), meta.get("namespace") or "default")


  def _storage_delete(self):
    meta = self._selected_storage()
    if not meta:
      return
    is_pvc = meta.get("kind") == "pvc"
    name = meta.get("name")
    ns  = meta.get("namespace") or "default"
    label = "PersistentVolumeClaim" if is_pvc else "PersistentVolume"
    if QMessageBox.question(self, f"Delete {label}", f'Delete {label} "{name}"?',
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
      if is_pvc:
        cmd = f"kubectl delete pvc {name} -n {ns} 2>&1"
      else:
        cmd = f"kubectl delete pv {name} 2>&1"
      self._run_cmd(cmd, lambda o: (self._log(o), self._load_storage()))


  def _storage_ctx_menu(self, pos):
    item = self.pvx_list.itemAt(pos)
    if not item:
      return
    self.pvx_list.setCurrentItem(item)
    meta = item.data(Qt.UserRole) or {}
    kind = "pvc" if meta.get("kind") == "pvc" else "pv"
    name = meta.get("name")
    ns  = meta.get("namespace") or "default"
    menu = QMenu(self)
    menu.addAction(" Describe", lambda: self._describe(kind, name, ns))
    menu.addSeparator()
    menu.addAction(" Delete", self._storage_delete)
    menu.exec_(self.pvx_list.viewport().mapToGlobal(pos))


  def _load_config_resources(self, _=None):
    rtype = "configmaps" if self._cfg_type == "ConfigMaps" else "secrets"
    cmd = (
      f"kubectl get {rtype} {self._ns_flag()} "
      f"-o jsonpath='{{range .items[*]}}{{.metadata.name}}\n{{end}}' 2>&1"
    )
    self._run_cmd(cmd, self._populate_cfg_list)


  def _populate_cfg_list(self, out: str):
    self.cfg_list.clear()
    self.cfg_detail.clear()
    self.cfg_raw.clear()
    card_type = "configmap" if self._cfg_type == "ConfigMaps" else "secret"
    for name in out.strip().splitlines():
      name = name.strip()
      if not name:
        continue
      meta = {"name": name, "type": card_type}
      item = QListWidgetItem()
      item.setData(Qt.UserRole, meta)
      item.setSizeHint(QSize(0, ConfigCardWidget.CARD_HEIGHT))
      self.cfg_list.addItem(item)
      self.cfg_list.setItemWidget(item, ConfigCardWidget(meta))
    # Same reasoning as _populate_pods: reapply whatever's in the
    # filter box, since the rebuild above doesn't know about it.
    self._filter_configs(self.cfg_filter.text())


  def _filter_configs(self, text: str):
    q = text.lower()
    for i in range(self.cfg_list.count()):
      item = self.cfg_list.item(i)
      meta = item.data(Qt.UserRole) or {}
      item.setHidden(q not in meta.get("name", "").lower())


  def _on_cfg_selection_changed(self, current, previous):
    """Same card-selection forwarding as pods/deployments — the card
    widget owns its own selected-state paint, so the list has to tell
    it explicitly (see k8s_cards.py's _CardBase docstring)."""
    if previous is not None:
      w = self.cfg_list.itemWidget(previous)
      if w:
        w.set_selected(False)
    if current is None:
      return
    w = self.cfg_list.itemWidget(current)
    if w:
      w.set_selected(True)
    meta = current.data(Qt.UserRole) or {}
    name = meta.get("name", "")
    rtype = meta.get("type", "configmap")
    ns  = self._current_ns if self._current_ns != "(all namespaces)" else "default"
    self._run_cmd(f"kubectl get {rtype} {name} -n {ns} -o json 2>&1",
           lambda o: self._show_cfg_detail(o, rtype))


  def _pretty_cfg_value(self, val) -> str:
    """Re-indent a ConfigMap/Secret value for display.

    Values are often themselves a JSON document embedded as a string
    (e.g. a 'config.json' key). kubectl's default '-o yaml' renders any
    string containing real newlines as a double-quoted flow scalar —
    literal '\\n' escapes, long lines wrapped with a trailing
    backslash — which is unreadable for exactly this case. We already
    have the value un-escaped (real newlines) from '-o json', so if it
    parses as JSON we re-emit it with consistent 2-space indentation;
    otherwise it's shown as-is with its real line breaks intact.
    """
    text = str(val)
    stripped = text.strip()
    if stripped[:1] in "{[":
      try:
        parsed = json.loads(stripped)
        return json.dumps(parsed, indent=2)
      except Exception:
        pass
    return text


  def _show_cfg_detail(self, out: str, rtype: str):
    self.cfg_detail.clear()
    self.cfg_raw.clear()
    try:
      obj = json.loads(out)
    except Exception:
      QTreeWidgetItem(self.cfg_detail, ["(parse error)", out[:200]])
      self.cfg_raw.setPlainText(out)
      return

    data = obj.get("data") or obj.get("stringData") or {}
    decoded = {}
    for key, val in data.items():
      if rtype == "secret":
        import base64
        try:
          val = base64.b64decode(val).decode(errors="replace")
        except Exception:
          val = "(binary)"
      decoded[key] = val

    # ── Tree: one row per key, single-line preview (real newlines
    # would otherwise render oddly/collapse inside a tree cell) ──
    for key, val in decoded.items():
      preview = str(val).replace("\n", " ⏎ ").strip()
      if len(preview) > 200:
        preview = preview[:200] + " …"
      vi = QTreeWidgetItem([key, preview])
      vi.setFont(0, monospace_font(11))
      vi.setFont(1, monospace_font(10))
      self.cfg_detail.addTopLevelItem(vi)

    # ── Structured view: metadata + each key's full content, pretty
    # printed instead of kubectl's escaped/wrapped YAML flow scalar.
    meta = obj.get("metadata", {}) or {}
    lines = [
      f"apiVersion: {obj.get('apiVersion', 'v1')}",
      f"kind: {obj.get('kind', rtype.capitalize())}",
      f"name: {meta.get('name', '')}",
      f"namespace: {meta.get('namespace', '')}",
      "",
    ]
    for key, val in decoded.items():
      lines.append(f"{key}:")
      pretty = self._pretty_cfg_value(val)
      for pline in (pretty.splitlines() or [""]):
        lines.append(f" {pline}")
      lines.append("")
    self.cfg_raw.setPlainText("\n".join(lines).rstrip() + "\n")

  # ── Events ────────────────────────────────────────────────

  @staticmethod
  def _humanize_age(iso_ts: str) -> str:
    """Compact kubectl-style age ('45s' / '12m' / '3h' / '5d' / '2y')
    from a Kubernetes ISO-8601 UTC timestamp. Events come from '-o json'
    rather than a pre-formatted AGE column (unlike every other tab
    here), so this has to be computed client-side."""
    if not iso_ts:
      return "-"
    try:
      ts = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
      return "-"
    secs = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    if secs < 60:
      return f"{secs}s"
    mins = secs // 60
    if mins < 60:
      return f"{mins}m"
    hours = mins // 60
    if hours < 24:
      return f"{hours}h"
    days = hours // 24
    if days < 365:
      return f"{days}d"
    return f"{days // 365}y"


  def _load_events(self):
    self._run_cmd(f"kubectl get events {self._ns_flag()} -o json 2>&1", self._on_events_loaded)


  def _on_events_loaded(self, out: str):
    # Cached so the "Warnings only" toggle can re-filter instantly
    # without an extra SSH round-trip.
    self._events_raw = out
    self._populate_events(out)


  def _populate_events(self, out: str):
    self.event_list.clear()
    all_ns = (self._current_ns == "(all namespaces)")
    try:
      items = json.loads(out).get("items", [])
    except Exception:
      items = []

    def sort_key(it):
      return (it.get("lastTimestamp") or it.get("eventTime")
          or (it.get("metadata") or {}).get("creationTimestamp") or "")

    items.sort(key=sort_key, reverse=True)

    warnings_only = getattr(self, "_events_warnings_only", False)
    total = 0
    warning_count = 0
    for it in items:
      etype = it.get("type") or "Normal"
      if warnings_only and etype != "Warning":
        continue
      involved = it.get("involvedObject") or {}
      ts = sort_key(it)
      meta = {
        "namespace":  (it.get("metadata") or {}).get("namespace", ""),
        "type":    etype,
        "reason":   it.get("reason", "") or "-",
        "message":   it.get("message", "") or "",
        "count":    it.get("count") or 1,
        "object_kind": involved.get("kind", ""),
        "object_name": involved.get("name", ""),
        "age":     self._humanize_age(ts),
      }
      item = QListWidgetItem()
      item.setData(Qt.UserRole, meta)
      item.setSizeHint(QSize(0, EventCardWidget.CARD_HEIGHT))
      self.event_list.addItem(item)
      self.event_list.setItemWidget(item, EventCardWidget(meta, all_ns))
      total += 1
      if etype == "Warning":
        warning_count += 1

    if total == 0:
      color_key = "TEXT_MUTED"
    elif warning_count == 0:
      color_key = "SUCCESS"
    else:
      color_key = "DANGER"
    self._set_count_badge(
      self.event_count_lbl,
      f"{total} event{'s' if total != 1 else ''} · {warning_count} warning{'s' if warning_count != 1 else ''}",
      color_key,
    )
    self._filter_events(self.event_filter.text())


  def _toggle_events_warnings_only(self, on: bool):
    self._events_warnings_only = on
    if getattr(self, "_events_raw", None):
      self._populate_events(self._events_raw)
    else:
      self._load_events()


  def _filter_events(self, text: str):
    q = text.lower()
    for i in range(self.event_list.count()):
      item = self.event_list.item(i)
      meta = item.data(Qt.UserRole) or {}
      searchable = (
        f"{meta.get('reason', '')} {meta.get('object_kind', '')} "
        f"{meta.get('object_name', '')} {meta.get('message', '')}"
      ).lower()
      item.setHidden(q not in searchable)


  def _on_event_selection_changed(self, current, previous):
    if previous is not None:
      w = self.event_list.itemWidget(previous)
      if w:
        w.set_selected(False)
    if current is not None:
      w = self.event_list.itemWidget(current)
      if w:
        w.set_selected(True)


  def _event_involved_object(self, meta: dict):
    """Returns (kubectl_kind, name, namespace) for the object an event
    is about, or (None, None, None) if the event didn't carry one."""
    kind = (meta.get("object_kind") or "").lower()
    name = meta.get("object_name")
    if not kind or not name:
      return None, None, None
    ns = meta.get("namespace") or (
      self._current_ns if self._current_ns != "(all namespaces)" else "default"
    )
    return kind, name, ns


  def _on_event_double_click(self, item):
    meta = item.data(Qt.UserRole) or {}
    kind, name, ns = self._event_involved_object(meta)
    if kind:
      self._describe(kind, name, ns)


  def _event_ctx_menu(self, pos):
    item = self.event_list.itemAt(pos)
    if not item:
      return
    self.event_list.setCurrentItem(item)
    meta = item.data(Qt.UserRole) or {}
    kind, name, ns = self._event_involved_object(meta)
    menu = QMenu(self)
    if kind:
      menu.addAction(f" Describe {meta.get('object_kind')}/{name}",
              lambda: self._describe(kind, name, ns))
      menu.addSeparator()
    menu.addAction(" Copy Message",
            lambda: QApplication.clipboard().setText(meta.get("message", "")))
    menu.exec_(self.event_list.viewport().mapToGlobal(pos))

  # ── Describe helper ───────────────────────────────────────

