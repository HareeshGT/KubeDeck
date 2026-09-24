from dashboard_tab import *
from dashboard_tab import _dashboard_text

"""DashboardTab implementation mixin.

The public DashboardTab class remains in dashboard_tab.py; this module only
contains logically grouped DashboardTab methods.
"""

class DashboardNodesHistoryMixin:
  def _refresh_node_detail_from_api(self, node_name: str, win):
      """Fetch authoritative pod objects for one node.
      
      The dashboard-wide pod snapshot is intentionally compact and can degrade
      to a node/name map. A node detail window needs richer fields, so fetch
      only this node's pods as JSON; the response is small and avoids the
      large-cluster dashboard query/parser entirely.
      """
      safe_node = shlex.quote(str(node_name))
      command = self._contextual_command(
        f"kubectl get pods --all-namespaces --field-selector "
        f"spec.nodeName={safe_node} -o json 2>/dev/null"
      )
  
      worker = CommandWorker(self.ssh, command, timeout=20)
  
      def on_done(out, target=win, target_name=node_name):
        if self._node_windows.get(target_name) is not target:
          return
        try:
          data = json.loads(out or "{}")
          pods = []
          for item in data.get("items", []):
            meta = item.get("metadata") or {}
            status = item.get("status") or {}
            containers = status.get("containerStatuses") or []
            ready_count = sum(1 for c in containers if c.get("ready") is True)
            restart_count = sum(int(c.get("restartCount") or 0) for c in containers)
            owners = meta.get("ownerReferences") or []
            owner = ""
            if owners:
              owner_ref = owners[0]
              owner = f"{owner_ref.get('kind', '')}/{owner_ref.get('name', '')}".strip("/")
            created = str(meta.get("creationTimestamp") or "")
            pods.append({
              "namespace": str(meta.get("namespace") or ""),
              "name": str(meta.get("name") or ""),
              "phase": str(status.get("phase") or "Unknown"),
              "restarts": restart_count,
              "ready": f"{ready_count}/{len(containers)}" if containers else "-",
              "reason": str(status.get("reason") or ""),
              "message": str(status.get("message") or ""),
              "pod_ip": str(status.get("podIP") or ""),
              "host_ip": str(status.get("hostIP") or ""),
              "qos": str(status.get("qosClass") or ""),
              "created": created,
              "owner": owner,
              "waiting": "",
            })
          self._pods_by_node_cache[target_name] = pods
          target.update_pods(pods, self._pod_usage_cache)
        except Exception as exc:
          target.update_pods(
            self._pods_by_node_cache.get(target_name, []),
            self._pod_usage_cache,
            parse_error=f"Detailed pod query failed: {exc}",
          )
  
      def on_error(err, target=win, target_name=node_name):
        if self._node_windows.get(target_name) is target:
          target.update_pods(
            self._pods_by_node_cache.get(target_name, []),
            self._pod_usage_cache,
            parse_error=f"Detailed pod query failed: {err}",
          )
  
      worker.done.connect(on_done)
      worker.error.connect(on_error)
      track_worker(self._workers, worker)
      worker.start()
  
  
  def _on_node_double_clicked(self, node_name: str):
      pods = self._pods_by_node_cache.get(node_name, [])
  
      win = self._node_windows.get(node_name)
      if win is None:
        win = NodeDetailWindow(node_name, parent=self)
        win.closed.connect(self._on_node_window_closed)
        self._node_windows[node_name] = win
  
      win.update_pods(pods, self._pod_usage_cache, parse_error="Loading detailed pod status…")
      win.show()
      win.raise_()
      win.activateWindow()
  
      if self.ssh:
        self._refresh_node_detail_from_api(node_name, win)
  
  
  def _on_node_window_closed(self, node_name: str):
      self._node_windows.pop(node_name, None)
  
  
  def _load_all_history(self):
      """Read the whole on-disk store: {instance_key: [samples...]}.
      Tolerates the old pre-keying format (a bare list) by folding it
      into a "_legacy" bucket instead of discarding it outright."""
      try:
        with open(self._history_file, "r", encoding="utf-8") as f:
          data = json.load(f)
      except (OSError, ValueError, TypeError):
        return {}
      if isinstance(data, list):
        return {"_legacy": data[-500:]} if data else {}
      if isinstance(data, dict):
        return data
      return {}
  
  
  def _load_history(self):
      """Load just the current instance's slice of history."""
      if not self._history_key:
        return []
      all_history = self._load_all_history()
      data = all_history.get(self._history_key, [])
      return data[-500:] if isinstance(data, list) else []
  
  
  def _save_history(self):
      if not self._history_key:
        return
      try:
        # Read-modify-write against the full store so saving this
        # instance's history never clobbers any other instance's data
        # that another connection/session already wrote to the file.
        all_history = self._load_all_history()
        all_history[self._history_key] = self._history[-500:]
        tmp = self._history_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
          json.dump(all_history, f, separators=(",", ":"))
        os.replace(tmp, self._history_file)
      except OSError:
        pass
  
  
  def _record_history(self, node_lines, top, pods_by_node, events):
      now = time.time()
      if now - self._last_history_time < 60:
        return
      self._last_history_time = now
  
      cpu = []
      mem = []
      for value in top.values():
        try: cpu.append(float(value.get("cpu_pct")))
        except (TypeError, ValueError): pass
        try: mem.append(float(value.get("mem_pct")))
        except (TypeError, ValueError): pass
  
      pods = [p for rows in pods_by_node.values() for p in rows]
      ready = sum(
        1 for line in node_lines
        if len(line.split()) >= 2 and line.split()[1].lower().split(",", 1)[0] == "ready"
      )
      sample = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu": round(sum(cpu) / len(cpu), 1) if cpu else None,
        "memory": round(sum(mem) / len(mem), 1) if mem else None,
        "pods": len(pods),
        "ready_nodes": ready,
        "restarts": sum(p.get("restarts", 0) for p in pods),
        "pending": sum(1 for p in pods if p.get("phase", "").lower() == "pending"),
        "events": events[-20:],
      }
      self._history.append(sample)
      self._history = self._history[-500:]
      self._save_history()
      self._render_history()
  
  
  def _render_history(self):
      rows = self._history[-120:]
      self.history_cpu.set_points([(x["time"][11:16], x.get("cpu")) for x in rows])
      self.history_mem.set_points([(x["time"][11:16], x.get("memory")) for x in rows])
      self.history_pods.set_points([(x["time"][11:16], x.get("pods")) for x in rows])
      self.history_nodes.set_points([(x["time"][11:16], x.get("ready_nodes")) for x in rows])
  
      self.history_events.clear()
      seen = set()
      for row in reversed(rows):
        for e in reversed(row.get("events", [])):
          key = (row["time"], e.get("reason"), e.get("object"), e.get("message"))
          if key in seen:
            continue
          seen.add(key)
          item = QTreeWidgetItem([
            row["time"], e.get("type", "Normal"), e.get("reason", "—"),
            e.get("object", "—"), e.get("namespace", "—"), e.get("message", "—")
          ])
          item.setForeground(1, QColor(
            T["DANGER"] if e.get("type", "").lower() == "warning" else T["SUCCESS"]
          ))
          self.history_events.addTopLevelItem(item)
      for col in range(6):
        self.history_events.resizeColumnToContents(col)
  
      self.history_status.setText(
        f"{len(self._history)} samples · 1 minute interval · last 500 samples kept"
      )
      if rows:
        latest = rows[-1]
        alerts = []
        if latest.get("cpu") is not None and latest["cpu"] >= self._history_cpu_limit:
          alerts.append(f"CPU {latest['cpu']}%")
        if latest.get("memory") is not None and latest["memory"] >= self._history_mem_limit:
          alerts.append(f"Memory {latest['memory']}%")
        if latest.get("restarts", 0) >= self._history_restart_limit:
          alerts.append(f"Restarts {latest['restarts']}")
        if latest.get("pending", 0) >= self._history_pending_limit:
          alerts.append(f"Pending pods {latest['pending']}")
        self.history_alerts.setText("Alerts: " + (", ".join(alerts) if alerts else "none"))
        self.history_alerts.setStyleSheet(
          f"color: {T['DANGER'] if alerts else _dashboard_text('muted')}; font-size: 12px;"
        )

