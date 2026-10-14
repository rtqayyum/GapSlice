"""Command-line interface.

    python -m gapslice list                 list the experiments
    python -m gapslice run e7 A             run one experiment (contract A or B)
    python -m gapslice figures [name ...]   redraw figures from stored results
    python -m gapslice tables [name ...]    rewrite LaTeX tables from stored results

Set GAPSLICE_OUTPUT=<folder> to write new files there instead of into the
repository (the stored results of the paper are then left untouched).
"""
import runpy
import sys

from gapslice.experiments import REGISTRY


def _list():
    print(f"{'name':14s} {'module':52s} {'outputs':28s} time")
    for name, (mod, needs_c, outs, t) in REGISTRY.items():
        print(f"{name:14s} {mod:52s} {', '.join(outs):28s} {t}")


def _run(args):
    if not args or args[0] not in REGISTRY:
        sys.exit(f"unknown experiment; choose from: {', '.join(REGISTRY)}")
    mod, needs_c, _, _ = REGISTRY[args[0]]
    rest = args[1:]
    if needs_c and (not rest or rest[0] not in ("A", "B")):
        sys.exit(f"{args[0]} needs the contract type: A or B")
    sys.argv = [mod] + rest
    runpy.run_module(mod, run_name="__main__", alter_sys=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        _list()
    elif cmd == "run":
        _run(args)
    elif cmd == "figures":
        from gapslice.reporting import figures
        figures.main(args)
    elif cmd == "tables":
        from gapslice.reporting import tables
        tables.main(args)
    else:
        sys.exit(f"unknown command {cmd!r}; see 'python -m gapslice help'")


if __name__ == "__main__":
    main()
