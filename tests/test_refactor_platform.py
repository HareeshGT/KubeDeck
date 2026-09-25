import ast
import importlib
import os
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _compile_tree(path: Path):
    files = list(path.rglob("*.py")) if path.is_dir() else [path]
    for f in files:
        py_compile.compile(str(f), doraise=True)


def _method_names(path: Path, class_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()


def test_main_window_compiles():
    _compile_tree(ROOT / "main_window.py")
    _compile_tree(ROOT / "main_window_parts")


def test_main_window_methods_preserved_when_original_available():
    original_root = os.environ.get("KUBEDOCK_ORIG")
    if not original_root:
        import pytest
        pytest.skip("Set KUBEDOCK_ORIG to compare against the original source")

    original = Path(original_root) / "main_window.py"
    if not original.exists():
        import pytest
        pytest.skip(f"Original source not found: {original}")

    original_methods = _method_names(original, "EC2FileManager")

    mixin_methods = set()
    for f in (ROOT / "main_window_parts").glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("Mixin"):
                mixin_methods.update(
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                )

    assert original_methods == mixin_methods


def test_refactored_packages_import():
    importlib.import_module("dialogs_parts")
    importlib.import_module("kubernetes_tab_parts")
    importlib.import_module("dashboard_tab_parts")
    importlib.import_module("main_window_parts")


def test_main_window_import():
    importlib.import_module("main_window")


def test_main_window_facade_has_expected_class():
    module = importlib.import_module("main_window")
    assert hasattr(module, "EC2FileManager")
