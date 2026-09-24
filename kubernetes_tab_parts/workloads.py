from .common import *


class KubernetesWorkloadsMixin:
  def _load_workloads(self, _=None):
    if self._workload_type == "CronJobs":
      self._load_cronjobs()
    else:
      self._load_jobs()


  @staticmethod
  def _job_status(status: dict, spec: dict) -> str:
    conditions = status.get("conditions") or []
    for c in conditions:
      if c.get("type") == "Complete" and c.get("status") == "True":
        return "Complete"
      if c.get("type") == "Failed" and c.get("status") == "True":
        return "Failed"
    if status.get("active"):
      return "Running"
    if status.get("succeeded"):
      return "Complete"
    if status.get("failed"):
      return "Failed"
    return "Pending"


  @staticmethod
  def _job_duration(status: dict) -> str:
    start = status.get("startTime")
    end  = status.get("completionTime")
    if not start:
      return "-"
    try:
      t0 = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
      return "-"
    t1 = datetime.now(timezone.utc)
    if end:
      try:
        t1 = datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
      except Exception:
        pass
    secs = max(0, int((t1 - t0).total_seconds()))
    if secs < 60:
      return f"{secs}s"
    mins = secs // 60
    if mins < 60:
      return f"{mins}m{secs % 60}s"
    hours = mins // 60
    return f"{hours}h{mins % 60}m"


  def _load_jobs(self):
    self._run_cmd(f"kubectl get jobs {self._ns_flag()} -o json 2>&1", self._populate_jobs)


  def _job_meta_from_item(self, it: dict) -> dict:
    meta_o = it.get("metadata") or {}
    spec  = it.get("spec") or {}
    status = it.get("status") or {}
    completions = spec.get("completions", 1)
    succeeded  = status.get("succeeded", 0)
    owner = ""
    for ref in meta_o.get("ownerReferences") or []:
      if ref.get("kind") == "CronJob":
        owner = ref.get("name", "")
        break
    return {
      "namespace":  meta_o.get("namespace", ""),
      "name":    meta_o.get("name", ""),
      "status":   self._job_status(status, spec),
      "completions": f"{succeeded}/{completions}",
      "duration":  self._job_duration(status),
      "owner":    owner,
      "age":     self._humanize_age(meta_o.get("creationTimestamp", "")),
    }


  def _populate_jobs(self, out: str):
    self.wl_list.clear()
    all_ns = (self._current_ns == "(all namespaces)")
    try:
      items = json.loads(out).get("items", [])
    except Exception:
      items = []
    for it in items:
      meta = self._job_meta_from_item(it)
      item = QListWidgetItem()
      item.setData(Qt.UserRole, {**meta, "kind": "job"})
      item.setSizeHint(QSize(0, JobCardWidget.CARD_HEIGHT))
      self.wl_list.addItem(item)
      self.wl_list.setItemWidget(item, JobCardWidget(meta, all_ns))
    total = len(items)
    color_key = "TEXT_MUTED" if total == 0 else "INFO"
    self._set_count_badge(self.wl_count_lbl, f"{total} job{'s' if total != 1 else ''}", color_key)
    self._filter_workloads(self.wl_filter.text())


  def _load_cronjobs(self):
    self._run_cmd(f"kubectl get cronjobs {self._ns_flag()} -o json 2>&1", self._populate_cronjobs)


  def _populate_cronjobs(self, out: str):
    self.wl_list.clear()
    all_ns = (self._current_ns == "(all namespaces)")
    try:
      items = json.loads(out).get("items", [])
    except Exception:
      items = []
    for it in items:
      meta_o = it.get("metadata") or {}
      spec  = it.get("spec") or {}
      status = it.get("status") or {}
      meta = {
        "namespace":   meta_o.get("namespace", ""),
        "name":     meta_o.get("name", ""),
        "schedule":   spec.get("schedule", "-"),
        "suspend":    bool(spec.get("suspend", False)),
        "active":    len(status.get("active") or []),
        "last_schedule": self._humanize_age(status.get("lastScheduleTime", "")) if status.get("lastScheduleTime") else "never",
        "age":      self._humanize_age(meta_o.get("creationTimestamp", "")),
      }
      item = QListWidgetItem()
      item.setData(Qt.UserRole, {**meta, "kind": "cronjob"})
      item.setSizeHint(QSize(0, CronJobCardWidget.CARD_HEIGHT))
      self.wl_list.addItem(item)
      self.wl_list.setItemWidget(item, CronJobCardWidget(meta, all_ns))
    total = len(items)
    color_key = "TEXT_MUTED" if total == 0 else "INFO"
    self._set_count_badge(self.wl_count_lbl, f"{total} cronjob{'s' if total != 1 else ''}", color_key)
    self._filter_workloads(self.wl_filter.text())


  def _filter_workloads(self, text: str):
    q = text.lower()
    for i in range(self.wl_list.count()):
      item = self.wl_list.item(i)
      meta = item.data(Qt.UserRole) or {}
      item.setHidden(q not in meta.get("name", "").lower())


  def _selected_workload(self) -> tuple: # (Optional[dict])
    item = self.wl_list.currentItem()
    if not item:
      QMessageBox.warning(self, "No selection", "Select a job or cronjob first.")
      return None
    return item.data(Qt.UserRole) or {}


  def _on_workload_double_click(self, item):
    meta = item.data(Qt.UserRole) or {}
    self._describe(meta.get("kind", "job"), meta.get("name"), meta.get("namespace") or "default")


  def _on_workload_selection_changed(self, current, previous):
    if previous is not None:
      w = self.wl_list.itemWidget(previous)
      if w:
        w.set_selected(False)
    if current is None:
      self.wl_history_list.clear()
      return
    w = self.wl_list.itemWidget(current)
    if w:
      w.set_selected(True)
    meta = current.data(Qt.UserRole) or {}
    if meta.get("kind") == "cronjob":
      self._load_job_history(meta.get("namespace") or "default", meta.get("name"))
    else:
      self.wl_history_list.clear()


  def _load_job_history(self, ns: str, cronjob_name: str):
    self._history_cronjob = cronjob_name
    self._run_cmd(f"kubectl get jobs -n {ns} -o json 2>&1",
           lambda o: self._populate_job_history(o, cronjob_name))


  def _populate_job_history(self, out: str, cronjob_name: str):
    # The selection may have moved on to a different CronJob (or off
    # CronJobs entirely) while this command was in flight — drop a
    # stale result rather than showing the wrong run history.
    if getattr(self, "_history_cronjob", None) != cronjob_name:
      return
    self.wl_history_list.clear()
    try:
      items = json.loads(out).get("items", [])
    except Exception:
      items = []
    runs = []
    for it in items:
      owners = (it.get("metadata") or {}).get("ownerReferences") or []
      if any(r.get("kind") == "CronJob" and r.get("name") == cronjob_name for r in owners):
        runs.append(it)
    # Most recent run first.
    runs.sort(key=lambda it: (it.get("metadata") or {}).get("creationTimestamp", ""), reverse=True)
    for it in runs:
      meta = self._job_meta_from_item(it)
      item = QListWidgetItem()
      item.setData(Qt.UserRole, {**meta, "kind": "job"})
      item.setSizeHint(QSize(0, JobCardWidget.CARD_HEIGHT))
      self.wl_history_list.addItem(item)
      self.wl_history_list.setItemWidget(item, JobCardWidget(meta, False))
    if not runs:
      self.wl_history_list.addItem(QListWidgetItem(" No runs yet."))


  def _on_wl_history_double_click(self, item):
    meta = item.data(Qt.UserRole)
    if not meta:
      return
    self._describe("job", meta.get("name"), meta.get("namespace") or "default")


  def _workload_describe(self):
    meta = self._selected_workload()
    if meta:
      self._describe(meta.get("kind", "job"), meta.get("name"), meta.get("namespace") or "default")


  def _workload_delete(self):
    meta = self._selected_workload()
    if not meta:
      return
    kind = meta.get("kind", "job")
    name = meta.get("name")
    ns  = meta.get("namespace") or "default"
    label = "CronJob" if kind == "cronjob" else "Job"
    if QMessageBox.question(self, f"Delete {label}", f'Delete {label.lower()} "{name}"?',
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
      self._run_cmd(f"kubectl delete {kind} {name} -n {ns} 2>&1",
             lambda o: (self._log(o), self._load_workloads()))


  def _workload_trigger_now(self):
    meta = self._selected_workload()
    if not meta:
      return
    if meta.get("kind") != "cronjob":
      QMessageBox.information(self, "Trigger Now", "Select a CronJob to trigger.")
      return
    name = meta.get("name")
    ns  = meta.get("namespace") or "default"
    job_name = f"{name}-manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def on_done(out):
      self._log(out)
      self._load_job_history(ns, name)
      self._load_cronjobs()

    self._run_cmd(
      f"kubectl create job {job_name} --from=cronjob/{name} -n {ns} 2>&1", on_done)


  def _workload_toggle_suspend(self):
    meta = self._selected_workload()
    if not meta:
      return
    if meta.get("kind") != "cronjob":
      QMessageBox.information(self, "Suspend / Resume", "Select a CronJob first.")
      return
    name = meta.get("name")
    ns  = meta.get("namespace") or "default"
    new_suspend = not meta.get("suspend")
    patch = '{"spec":{"suspend":%s}}' % ("true" if new_suspend else "false")
    self._run_cmd(
      f"kubectl patch cronjob {name} -n {ns} -p '{patch}' --type=merge 2>&1",
      lambda o: (self._log(o), self._load_cronjobs()))


  def _workload_ctx_menu(self, pos):
    item = self.wl_list.itemAt(pos)
    if not item:
      return
    self.wl_list.setCurrentItem(item)
    meta = item.data(Qt.UserRole) or {}
    kind = meta.get("kind", "job")
    menu = QMenu(self)
    menu.addAction(" Describe", self._workload_describe)
    if kind == "cronjob":
      menu.addAction("▶ Trigger Now", self._workload_trigger_now)
      suspend_label = "▶ Resume" if meta.get("suspend") else "⏸ Suspend"
      menu.addAction(suspend_label, self._workload_toggle_suspend)
    menu.addSeparator()
    menu.addAction(" Delete", self._workload_delete)
    menu.exec_(self.wl_list.viewport().mapToGlobal(pos))

  # ── Storage: PersistentVolumeClaims / PersistentVolumes ────

