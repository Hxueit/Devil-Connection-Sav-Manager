"""每个模块都要能单独导入（在全新的解释器里），用来发现循环导入"""
import pathlib
import subprocess
import sys

import pytest

pytest.importorskip("tkinter")

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULES = sorted(
    ".".join(part for part in path.relative_to(ROOT).with_suffix("").parts if part != "__init__")
    for path in (ROOT / "src").rglob("*.py")
)


@pytest.mark.parametrize("module", MODULES)
def test_module_imports_on_its_own(module):
    result = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
