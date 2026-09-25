#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== KubeDock Test Platform ==="
echo "Python: $(python3 --version)"
echo "Pytest: $(python3 -m pytest --version)"
echo

echo "[1/5] Compile check"
python3 -m compileall -q \
  main.py \
  main_window.py \
  main_window_parts \
  dialogs_parts \
  kubernetes_tab_parts \
  dashboard_tab_parts
echo "PASS: compileall"
echo

echo "[2/5] Package import check"
python3 - <<'PY'
import importlib

packages = [
    "dialogs_parts",
    "kubernetes_tab_parts",
    "dashboard_tab_parts",
    "main_window_parts",
]

for package in packages:
    importlib.import_module(package)
    print(f"PASS: {package}")

importlib.import_module("main_window")
print("PASS: main_window")
PY
echo

echo "[3/5] Refactor regression tests"
python3 -m pytest -q tests/test_refactor_platform.py
echo

echo "[4/5] GUI dependency check"
python3 - <<'PY'
try:
    import PyQt5
    print("PASS: PyQt5")
except ImportError:
    try:
        from PySide6 import QtWidgets
        print("PASS: PySide6")
    except ImportError as exc:
        raise SystemExit(f"GUI dependency missing: {exc}")
PY
echo

echo "[5/5] Main-window facade check"
python3 - <<'PY'
import main_window

assert hasattr(main_window, "EC2FileManager")
print("PASS: EC2FileManager facade")
PY
echo

echo "=== Test platform completed ==="
