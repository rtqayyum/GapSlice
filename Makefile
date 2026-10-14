# Common tasks. Run from the repository root.
PY ?= python3

.PHONY: install test figures tables reproduce verify clean

install:            ## install the package and its pinned dependencies
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e .

test:               ## fast checks (about 30 s): model, channel, tables, reports
	$(PY) -m pytest -q

figures:            ## redraw all figures from the stored results
	$(PY) -m gapslice figures

tables:             ## rewrite all LaTeX tables from the stored results
	$(PY) -m gapslice tables

reproduce:          ## run every experiment from scratch (about 3.5 h on 2 cores)
	bash scripts/run_all.sh

verify:             ## rerun everything into ./rerun and leave the stored results untouched
	GAPSLICE_OUTPUT=$(CURDIR)/rerun bash scripts/run_all.sh

clean:
	rm -rf rerun .pytest_cache build *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
