"""Write the LaTeX tables of the paper and its supplement from the result files.

Every number in these tables is read from results/*.json; nothing is typed
by hand.

Usage:  python -m gapslice.reporting.tables [name ...]
Output: tables/tab_*.tex
"""
import json
import numpy as np
from gapslice import params as P
from gapslice import paths


def pct(x, d=1):
    return "--" if x is None else f"{100 * x:.{d}f}"


def num(x, d=0):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "--"
    return f"{x:.{d}f}"


def ci(c, d=1):
    return f"[{100 * c[0]:.{d}f}, {100 * c[1]:.{d}f}]"


def write(name, s):
    open(paths.table(f"{name}.tex"), "w").write(s)
    print("wrote", name)


# ------------------------------------------------------------- descriptors and PRBs per link (supplement S2)
def tab_ceb():
    F = json.load(open(paths.inp("feas.json")))
    H = [0.6, 0.8, 1.0, 1.2, 1.5, 2.0]
    L = [r"\begin{tabular}{@{}l r r r r r@{}}", r"\toprule",
         r"$h$ [s] & $99.99\%$ & A: CEB & A: class & B: CEB & B: class\\", r"\midrule"]
    for bn, lab in [("iid", r"independent losses"), ("burst2", r"bursts, $\beta=2$")]:
        L.append(r"\multicolumn{6}{@{}l}{\emph{" + lab + r"}}\\")
        for h in H:
            r = next(x for x in F["rows"] if x["beta"] == bn and abs(x["h"] - h) < 1e-9)
            u = num(r["urllc"]) + ("" if r["urllc_meets_A"] else r"$^\dagger$")

            def cell(c, cls):
                if r[c] is None:
                    return "--"
                s = num(r[c])
                if cls and r[cls] is not None:
                    s += r" {\scriptsize(" + f"{100 * r[cls]:g}" + r"\%)}"
                return s
            L.append(f"{h:.1f} & {u} & {cell('ceb_A', None)} & {cell('cls_A', 'class_A')} & "
                     f"{cell('ceb_B', None)} & {cell('cls_B', 'class_B')}\\\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_ceb", "\n".join(L) + "\n")


# ------------------------------------------------------------- time-correlated channel (supplement S4)
def tab_channel():
    E = json.load(open(paths.inp("e5.json")))
    L = [r"\begin{tabular}{@{}l c r r r r r r r r@{}}", r"\toprule",
         r" & & \multicolumn{2}{c}{$99.99\%$ slice} & \multicolumn{3}{c}{Time average $(\bar p,\bar\beta)$} &"
         r" \multicolumn{3}{c}{Per slow state (GapSlice)}\\",
         r"\cmidrule(lr){3-4}\cmidrule(lr){5-7}\cmidrule(l){8-10}",
         r"Link, $d_c$ & $h$ [s] & PRB & $\gamma$ & PRB & $\gamma$ & risk [\%] & PRB & $\gamma$ & risk [\%]\\",
         r"\midrule"]
    for r in E["rows"]:
        if r["h"] not in (0.8, 1.2):
            continue

        def g(x):
            if x is None:
                return "--"
            return r"$\infty$" if not np.isfinite(x["gain"]) else f"{x['gain']:.3f}"

        def rk(x):
            return "--" if x is None else f"{100 * x['risk']:.1f}"
        s, t, p = r["slice"], r["time_avg"], r["per_state"]
        lab = f"{r['link']}, {r['dc']:g} m" if r["h"] == 0.8 else ""
        L.append(f"{lab} & {r['h']:.1f} & {num(None if s is None else s['prbs'])} & {g(s)} & "
                 f"{num(None if t is None else t['prbs'])} & {g(t)} & {rk(t)} & "
                 f"{num(None if p is None else p['prbs'])} & {g(p)} & {rk(p)}\\\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_channel", "\n".join(L) + "\n")


# ------------------------------------------------------------- wrong burst length (supplement S4)
def tab_wrongbeta():
    E = json.load(open(paths.inp("e6.json")))
    L = [r"\begin{tabular}{@{}c r c c c c c c c r c@{}}", r"\toprule",
         r" & \multicolumn{5}{c}{Declared plan ($\beta=2$)} & \multicolumn{3}{c}{Probation (gap $h_g$)} & "
         r"\multicolumn{2}{c}{Plan for $\beta=4$}\\",
         r"\cmidrule(lr){2-6}\cmidrule(lr){7-9}\cmidrule(l){10-11}",
         r"$h$ [s] & PRB & $\gamma$ & risk [\%] & 10~s & 30~s & $h_g$ [s] & $\gamma$ & 30~s & PRB & $\gamma$\\",
         r"\midrule"]
    for r in E["rows"]:
        d, c, o, p = r["declared"], r["correct"], r["online"], r["probation"]
        L.append(f"{r['h']:.1f} & {d['prbs']} & {d['gain']:.3f} & {100*d['risk']:.1f} & "
                 f"{100*o['10 s']['detection']:.0f}\\% & {100*o['30 s']['detection']:.0f}\\% & "
                 f"{p['h_g']:.1f} & {p['gain']:.3f} & {100*p['online']['30 s']['detection']:.0f}\\% & "
                 f"{c['prbs']} & {c['gain']:.3f}\\\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_wrongbeta", "\n".join(L) + "\n")


# ------------------------------------------------------------- priority surges and loans (supplement S5)
def tab_loans():
    EA = json.load(open(paths.inp("e4_A.json")))
    EB = json.load(open(paths.inp("e4_B.json")))
    pols = ["LTR (Alg. 2)", "Wait-for-maneuver", "Graduated", "Naive preemption", "Static"]
    names = {"LTR (Alg. 2)": "LTR (Alg.~2)", "Wait-for-maneuver": "Wait for maneuver",
             "Graduated": "Graduated", "Naive preemption": "Naive preemption", "Static": "Static"}
    L = [r"\begin{tabular}{@{}l r r r r c c c c r r r@{}}", r"\toprule",
         r" & \multicolumn{2}{c}{$t_{95}$ [s]} & \multicolumn{2}{c}{Unserved, $10$~s [\%]} & "
         r"\multicolumn{2}{c}{Clause exc.: loans} & \multicolumn{2}{c}{Clause exc.: maneuver} & "
         r"\multicolumn{2}{c}{Per-event risk [\%]} & $d_{1\%}$ [m]\\",
         r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(lr){8-9}\cmidrule(lr){10-11}\cmidrule(l){12-12}",
         r"Policy & A & B & A & B & A & B & A & B & A & B & B\\", r"\midrule"]
    sa, sb = EA["summary"]["service"]["0.3"], EB["summary"]["service"]["0.3"]

    def exc(d, key):
        if "n_lenders" not in d:
            return "--"
        if key == "loans":
            if d.get("lenders_with_deficit", 0) == 0:
                return "--"
            return f"{d['deficit_over_clause']}/{d['lenders_with_deficit']}"
        return f"{d['frozen_over_clause']}/{d['n_lenders']}"
    for p in pols + ["No surge (reference)"]:
        if p in sa:
            da, db = sa[p], sb[p]
            serv = f"{da['t95']:.1f} & {db['t95']:.1f} & {100*da['unserved10']:.0f} & {100*db['unserved10']:.0f}"
            cl = f"{exc(da,'loans')} & {exc(db,'loans')} & {exc(da,'all')} & {exc(db,'all')}"
        else:
            serv = "-- & -- & -- & --"
            cl = "-- & -- & -- & --"
        if p in EA["summary"]["sim"]:
            ra, rb = EA["summary"]["sim"][p], EB["summary"]["sim"][p]
            rka = f"{100*ra['risk']:.1f} {{\\scriptsize{ci(ra['ci'])}}}"
            rkb = f"{100*rb['risk']:.1f} {{\\scriptsize{ci(rb['ci'])}}}"
            dm = f"{rb['dmin1_min']:.1f}"
        else:
            rka = rkb = dm = "--"
        nm = names.get(p, "No surge (reference)")
        L.append(f"{nm} & {serv} & {cl} & {rka} & {rkb} & {dm}\\\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_loans", "\n".join(L) + "\n")


# ------------------------------------------------------------- sensitivity (supplement S7)
def tab_sens():
    S = json.load(open(paths.inp("sens.json")))
    L = [r"\begin{tabular}{@{}l r r r r@{}}", r"\toprule",
         r"Case & $h=0.6$ & $0.8$ & $1.0$ & $1.2$\\", r"\midrule",
         r"\multicolumn{5}{@{}l}{\emph{Payload: CEB / $99.99\%$ slice [PRB], $\beta=2$}}\\"]
    for LB in [300, 600, 1200]:
        cells = []
        for h in [0.6, 0.8, 1.0, 1.2]:
            r = next(x for x in S["payload"] if x["payload"] == LB and x["beta"] == 2.0 and abs(x["h"] - h) < 1e-9)
            cells.append(f"{num(r['ceb'])}\\,/\\,{num(r['urllc'])}")
        L.append(f"{LB}~B & " + " & ".join(cells) + r"\\")
    L.append(r"\multicolumn{5}{@{}l}{\emph{Contract tolerance: CEB [PRB], $\beta=2$ ($h_{\min}$)}}\\")
    for row in S["tolerance"]:
        if row["beta"] != 2.0:
            continue
        cells = [num(row["at"][str(h)]["ceb"]) for h in [0.6, 0.8, 1.0, 1.2]]
        L.append(f"$1.0025^{{{row['exp']:g}}}$ ({row['h_min']:.1f}~s) & " + " & ".join(cells) + r"\\")
    L.append(r"\multicolumn{5}{@{}l}{\emph{Radio model: saving vs.\ $99.99\%$ [\%], $\beta=2$}}\\")
    for name in ["Rician K=3 dB (nominal)", "Rayleigh", "Rician K=10 dB", "K=3 dB, 2-Rx MRC"]:
        cells = []
        for h in [0.6, 0.8, 1.0, 1.2]:
            r = next(x for x in S["radio"] if x["radio"] == name and x["beta"] == 2.0 and abs(x["h"] - h) < 1e-9)
            cells.append("--" if r["ceb"] is None else f"{100 * (1 - r['ceb'] / r['urllc']):.0f}")
        lab = {"Rician K=3 dB (nominal)": "Rician $3$~dB (nominal)", "Rayleigh": "Rayleigh",
               "Rician K=10 dB": "Rician $10$~dB", "K=3 dB, 2-Rx MRC": "Rician $3$~dB, 2-Rx MRC"}[name]
        L.append(f"{lab} & " + " & ".join(cells) + r"\\")
    L.append(r"\multicolumn{5}{@{}l}{\emph{Model error: platoon availability [\%] (detected in $30$~s)}}\\")
    for err in ["nominal", "Rayleigh fading", "large-scale std +2 dB", "interferers at 200 m", "mean SINR -3 dB"]:
        cells = []
        for h in [0.6, 0.8, 1.0, 1.2]:
            r = next(x for x in S["model_error"] if x["error"] == err and abs(x["h"] - h) < 1e-9)
            cells.append(f"{100 * r['platoon_avail']:.1f} ({100 * r['online']['30 s']['detection']:.0f}\\%)")
        lab = {"nominal": "No error", "Rayleigh fading": "Rayleigh instead of Rician",
               "large-scale std +2 dB": "Large-scale std.\\ $+2$~dB",
               "interferers at 200 m": "Interferers at $200$~m", "mean SINR -3 dB": "Mean SINR $-3$~dB"}[err]
        L.append(f"{lab} & " + " & ".join(cells) + r"\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_sens", "\n".join(L) + "\n")


# ------------------------------------------------------------- end-to-end validation (paper, Section IV-G)
def tab_e2e():
    E = {c: json.load(open(paths.inp(f"e7_{c}.json")))["summary"] for c in "AB"}
    names = {"GapSlice": "GapSlice, $\\epsilon_l=\\epsilon/L_k$", "per-link eps": "Per-link $\\epsilon_l=\\epsilon$",
             "99.99% slice": "$99.99\\%$ slice, $\\epsilon_l=\\epsilon/L_k$"}
    L = [r"\begin{tabular}{@{}l r r c c c c c c@{}}", r"\toprule",
         r" & \multicolumn{2}{c}{PRB (rel.)} & \multicolumn{2}{c}{Availability [\%]} & "
         r"\multicolumn{2}{c}{Per-event risk [\%]} & \multicolumn{2}{c}{$d_{1\%}$ [m]}\\",
         r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(l){8-9}",
         r"Rule & A & B & A & B & A & B & A & B\\", r"\midrule"]
    for rule in ["GapSlice", "per-link eps", "99.99% slice"]:
        cells = []
        for c in "AB":
            cells.append(f"{E[c][rule]['prbs'] / E[c]['GapSlice']['prbs']:.2f}")
        for c in "AB":
            s_ = E[c][rule]
            cells.append(f"{100*s_['avail_exact_mean']:.1f} {{\\scriptsize({100*s_['avail_exact_min']:.1f})}}")
        for c in "AB":
            s_ = E[c][rule]
            cells.append(f"{100*s_['risk']:.2f} {{\\scriptsize{ci(s_['ci'], 2)}}}")
        for c in "AB":
            cells.append(f"{E[c][rule]['dmin1']:.1f}")
        L.append(f"{names[rule]} & " + " & ".join(cells) + r"\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_e2e", "\n".join(L) + "\n")


def tab_e2e_short():
    """Compact end-to-end table for the main paper (one column)."""
    E = {c: json.load(open(paths.inp(f"e7_{c}.json")))["summary"] for c in "AB"}
    names = {"GapSlice": "GapSlice ($\\epsilon/L_k$)", "per-link eps": "Per link ($\\epsilon$)",
             "99.99% slice": "$99.99\\%$ slice"}
    L = [r"\begin{tabular}{@{}l r r r r r r@{}}", r"\toprule",
         r" & \multicolumn{2}{c}{PRBs (rel.)} & \multicolumn{2}{c}{Availability [\%]} & "
         r"\multicolumn{2}{c}{Event risk [\%]}\\",
         r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(l){6-7}",
         r"Planning rule & A & B & A & B & A & B\\", r"\midrule"]
    for rule in ["GapSlice", "per-link eps", "99.99% slice"]:
        cells = [f"{E[c][rule]['prbs'] / E[c]['GapSlice']['prbs']:.2f}" for c in "AB"]
        cells += [f"{100*E[c][rule]['avail_exact_mean']:.1f}" for c in "AB"]
        cells += [f"{100*E[c][rule]['risk']:.2f}" for c in "AB"]
        L.append(f"{names[rule]} & " + " & ".join(cells) + r"\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_e2e_short", "\n".join(L) + "\n")


def tab_corr():
    """Correlated slow states across the links of a platoon (E9)."""
    E = {c: json.load(open(paths.inp(f"e9_{c}.json")))["summary"] for c in "AB"}
    L = [r"\begin{tabular}{@{}c c c c c c c@{}}", r"\toprule",
         r" & \multicolumn{2}{c}{Availability [\%] (min.)} & \multicolumn{2}{c}{Event risk [\%]} & "
         r"\multicolumn{2}{c}{Max.\ amplification}\\",
         r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(l){6-7}",
         r"Correlation $\rho$ & A & B & A & B & A & B\\", r"\midrule"]
    for c in sorted(E["A"].keys(), key=float):
        a, b = E["A"][c], E["B"][c]
        cell = lambda s: f"{100*s['avail_mean']:.1f} ({100*s['avail_min']:.1f})"
        rk = lambda s: f"{100*s['risk']:.2f} {{\\scriptsize{ci(s['ci'], 2)}}}"
        L.append(f"{float(c):.1f} & {cell(a)} & {cell(b)} & {rk(a)} & {rk(b)} & "
                 f"{a['ms_amp_max']:.2f} & {b['ms_amp_max']:.2f}\\\\")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_corr", "\n".join(L) + "\n")


# ------------------------------------------------------------- comparison with published methods (paper, Section IV-F)
def tab_compare():
    """Comparison with three published methods (adapted implementations), 20
    tenants; per-link PRBs of a five-truck platoon at h = 1.0 s (matched modes)."""
    E = {c: json.load(open(paths.inp(f"e8_{c}.json"))) for c in "AB"}
    S4 = {c: json.load(open(paths.inp(f"e4_{c}.json")))["summary"]["service"]["0.3"]["LTR (Alg. 2)"] for c in "AB"}
    rows = [("GapSlice", "GapSlice", "--", "GapSlice", "descriptor tables, menu choices",
             f"{S4['A']['t95']:.1f} / {S4['B']['t95']:.1f}"),
            ("Yan-Harri (original)", "Yan--H\\\"arri~\\cite{Yan2024ICC}", "original", None, "platoon size, join requests", "n/a"),
            ("Yan-Harri (matched)", "", "matched", "Yan-Harri (matched)", "", ""),
            ("Zhang (original)", "Zhang \\emph{et al.}~\\cite{Zhang2023TIV}", "original", None, "controller model, vehicle states", "n/a"),
            ("Zhang (matched)", "", "matched", "Zhang (matched)", "", ""),
            ("Lu (original)", "Lu \\emph{et al.}~\\cite{Lu2024TNSM}", "original", None, "slice SLA, agent observations", "n/a"),
            ("Lu (matched)", "", "matched", "Lu (matched)", "", ""),
            ("Oracle", "Optimum of P1", "--", "GapSlice", "full information", "n/a")]
    pair = lambda s: r"\multicolumn{2}{c}{" + s + "}"
    L = [r"\begin{tabular}{@{}l l r r r r r r r r r r r l@{}}", r"\toprule",
         r" & & " + " & ".join(pair(s) for s in [r"PRBs/link [$\times$]", r"Target met [\%]",
                                                  r"Availability [\%]", r"Event risk [\%]", r"Utility [\%]"])
         + r" & Surge $t_{95}$ & \\",
         r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(lr){7-8}\cmidrule(lr){9-10}\cmidrule(lr){11-12}",
         r"Method & Mode & A & B & A & B & A & B & A & B & A & B & A / B [s] & Information required\\",
         r"\midrule"]
    for key, name, mode, plkey, info, surge in rows:
        a, b = E["A"]["summary"][key], E["B"]["summary"][key]
        def pl(c):
            if plkey is None:
                return "--"
            return f"{E[c]['per_link']['1.0'][plkey]['mean']:.2f}"
        met = lambda d: "--" if d["20"]["met"] is None else f"{100*d['20']['met']:.0f}"
        av = lambda d: "--" if d["20"]["avail_mean"] is None else f"{100*d['20']['avail_mean']:.1f}"
        rk = lambda d: f"{100*d['sim']['risk']:.2f}"
        ut = lambda d: f"{100*d['20']['util']:.1f}"
        L.append(f"{name} & {mode} & {pl('A')} & {pl('B')} & {met(a)} & {met(b)} & {av(a)} & {av(b)} & "
                 f"{rk(a)} & {rk(b)} & {ut(a)} & {ut(b)} & {surge} & {info}\\\\")
        if key in ("GapSlice", "Yan-Harri (matched)", "Zhang (matched)", "Lu (matched)"):
            L.append(r"\addlinespace[2pt]")
    L += [r"\bottomrule", r"\end{tabular}"]
    write("tab_compare", "\n".join(L) + "\n")


ALL = ["ceb", "channel", "wrongbeta", "loans", "sens", "e2e", "compare", "e2e_short", "corr"]


def main(names=None):
    for name in names or ALL:
        globals()["tab_" + name]()


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
