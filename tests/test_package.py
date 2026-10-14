"""Every module imports, and the command-line interface lists the experiments."""
import importlib
import os
import pkgutil
import subprocess
import sys

import gapslice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_all_modules_import():
    names = [m.name for m in pkgutil.walk_packages(gapslice.__path__, "gapslice.")]
    assert len(names) > 30
    for name in names:
        if name != "gapslice.__main__":
            importlib.import_module(name)


def test_cli_lists_experiments():
    r = subprocess.run([sys.executable, "-m", "gapslice", "list"], cwd=ROOT,
                       capture_output=True, text=True, check=True)
    for exp in ("e1", "e4", "e8", "e9", "type-b-table"):
        assert exp in r.stdout


if __name__ == "__main__":
    test_all_modules_import()
    test_cli_lists_experiments()
    print("package checks passed")
