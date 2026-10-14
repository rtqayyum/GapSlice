"""Where GapSlice reads and writes its files.

By default everything lives in the repository: stored results in
``results/``, figures in ``figures/`` and LaTeX tables in ``tables/``.

Environment variables change this without touching the code:

``GAPSLICE_ROOT``
    Repository root (default: the folder that contains ``results/``).
``GAPSLICE_RESULTS``
    Folder from which result files are read (default: ``<repo>/results``).
``GAPSLICE_OUTPUT``
    If set, new results, figures and tables are written to
    ``$GAPSLICE_OUTPUT/results``, ``/figures`` and ``/tables`` instead of the
    repository folders. The stored files of the paper are then never
    overwritten, which is how the test suite checks reproducibility.
"""
import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[1]
# repository root: the folder that holds results/ (the package folder's parent
# in a checkout or an editable install, else the working directory)
ROOT = Path(os.environ.get("GAPSLICE_ROOT",
                           _PKG_ROOT if (_PKG_ROOT / "results").is_dir() else Path.cwd()))
RESULTS = Path(os.environ.get("GAPSLICE_RESULTS", ROOT / "results"))
FIGURES = ROOT / "figures"
TABLES = ROOT / "tables"


def _output_root():
    v = os.environ.get("GAPSLICE_OUTPUT")
    return Path(v) if v else None


def inp(name):
    """Path of a stored result file that is read."""
    return str(RESULTS / name)


def _target(kind, default, name):
    root = _output_root()
    folder = (root / kind) if root is not None else default
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / name)


def out(name):
    """Path of a result file that is written."""
    return _target("results", RESULTS, name)


def figure(name):
    """Path of a figure file that is written."""
    return _target("figures", FIGURES, name)


def table(name):
    """Path of a LaTeX table that is written."""
    return _target("tables", TABLES, name)
