"""Figures and tables redrawn from the stored results are identical to the
stored ones (PDFs are compared without their creation date)."""
import filecmp
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _strip_date(b):
    return re.sub(rb"/CreationDate \(D:[^)]*\)", b"", b)


def test_figures_and_tables_reproduce():
    with tempfile.TemporaryDirectory() as out:
        env = dict(os.environ, GAPSLICE_OUTPUT=out, OMP_NUM_THREADS="1")
        for cmd in ("figures", "tables"):
            subprocess.run([sys.executable, "-m", "gapslice", cmd], cwd=ROOT, env=env,
                           check=True, capture_output=True)
        for kind in ("figures", "tables"):
            for name in sorted(os.listdir(os.path.join(ROOT, kind))):
                a, b = os.path.join(ROOT, kind, name), os.path.join(out, kind, name)
                if name.endswith(".pdf"):
                    assert _strip_date(open(a, "rb").read()) == _strip_date(open(b, "rb").read()), name
                else:
                    assert filecmp.cmp(a, b, shallow=False), name


if __name__ == "__main__":
    test_figures_and_tables_reproduce()
    print("figures and tables reproduce")
