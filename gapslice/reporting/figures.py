"""Publication figures for the GapSlice evaluation (IEEE column/page width).
Every figure is drawn from the stored result files in results/.

Usage:  python -m gapslice.reporting.figures [name ...]
Output: figures/fig_*.pdf and figures/fig_*.png
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from gapslice import params as P
from gapslice import paths
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
C = dict(blue="#2a78d6", orange="#eb6834", aqua="#1baf7a", yellow="#eda100",
         magenta="#e87ba4", gray="#52514e")
ORD3 = ["#86b6ef", "#2a78d6", "#104281"]          # ordinal ramp (light -> dark)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7.5, "axes.titlesize": 7.5,
    "axes.labelsize": 7.5, "legend.fontsize": 6.8, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "axes.edgecolor": AXIS, "axes.linewidth": 0.6,
    "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.5, "grid.linestyle": "-", "lines.linewidth": 1.5,
    "lines.markersize": 4, "legend.frameon": False, "savefig.dpi": 300,
    "figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
    "pdf.fonttype": 42,
})
W1, W2 = 3.5, 7.16   # IEEE column / page width [in]
BN = {0.0: "i.i.d.", 2.0: r"$\beta$ = 2", 4.0: r"$\beta$ = 4"}


def save(fig, name):
    fig.savefig(paths.figure(name + ".pdf"), bbox_inches="tight")
    fig.savefig(paths.figure(name + ".png"), bbox_inches="tight")
    plt.close(fig)


def fig_descriptor():
    from gapslice.descriptor.tables import p_c, p_tail
    G = dict(np.load(paths.inp("gain_curves.npz")))
    T = dict(np.load(paths.inp("tail_table.npz")))
    fig, ax = plt.subplots(1, 2, figsize=(W2, 2.2))
    q = G["Q"]; j = list(G["BETAS"]).index(2.0); m = list(G["ETAS"]).index(0.3)
    for col, h in zip(ORD3, [0.5, 0.8, 1.2]):
        i = list(np.round(G["H"], 2)).index(h)
        g = G["G"][i, j, m]
        ok = np.isfinite(g)
        ax[0].plot(q[ok], g[ok], color=col, label=f"$h$ = {h} s")
    ax[0].axhline(P.GAMMA_LINK, color=INK2, lw=0.8)
    ax[0].text(1.2e-4, P.GAMMA_LINK + 0.01, r"contract, per vehicle", color=INK2, fontsize=6.5)
    ax[0].set_xscale("log"); ax[0].set_ylim(0.98, 1.4)
    ax[0].set_xlabel(r"loss probability $1-p$ (mean burst $\beta$ = 2)")
    ax[0].set_ylabel(r"certified mean-square gain $\gamma$")
    ax[0].set_title("(a) Certificate vs. delivery probability", loc="left")
    ax[0].legend(loc="upper left")
    H = [float(h) for h in G["H"] if h < P.H_ACC - 1e-9]
    HB = [float(h) for h in T["H"]]
    for col, b in zip(ORD3, [0.0, 2.0, 4.0]):
        pa = np.array([p_c(h, b, P.GAMMA_LINK) for h in H])
        ax[1].plot(H, 1 - pa, color=col, marker="o", ms=3, label=f"A, {BN[b]}")
        pb = np.array([p_tail(h, b, 0.3, 5) for h in HB])
        ax[1].plot(HB, 1 - pb, color=col, marker="s", ms=3, mfc="white", lw=1.0, ls="--",
                   label=f"B ($N$=5), {BN[b]}")
    ax[1].axhline(1 - P.P_URLLC, color=C["orange"], lw=1.0)
    ax[1].text(0.3, 1.35e-4, "99.99 % per link", color=C["orange"], fontsize=6.5)
    ax[1].set_yscale("log"); ax[1].set_ylim(5e-5, 1)
    ax[1].set_xlabel("time gap $h$ [s]")
    ax[1].set_ylabel("tolerable loss probability")
    ax[1].set_title("(b) Control descriptors, contract types A and B", loc="left")
    ax[1].legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.30),
                 fontsize=6.2, handlelength=2.0, columnspacing=1.0)
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig_descriptor")


def fig_ceb():
    F = json.load(open(paths.inp("feas.json")))
    rows = F["rows"]
    fig, ax = plt.subplots(1, 2, figsize=(W2, 2.2), sharey=True)
    for a, typ, ttl in [(ax[0], "A", "(a) Type A (certified, mean square)"),
                        (ax[1], "B", "(b) Type B (per event, 1 %, $N$ = 5)")]:
        H = [r["h"] for r in rows if r["beta"] == "iid"]
        url = [r["urllc"] for r in rows if r["beta"] == "iid"]
        a.plot(H, url, color=C["orange"], marker="^", ms=3, label="99.99 % slice")
        for col, bn, b in [(C["blue"], "iid", 0.0), ("#104281", "burst2", 2.0)]:
            rr = [r for r in rows if r["beta"] == bn]
            ce = [np.nan if r[f"ceb_{typ}"] is None else r[f"ceb_{typ}"] for r in rr]
            cl = [np.nan if r[f"cls_{typ}"] is None else r[f"cls_{typ}"] for r in rr]
            a.plot(H, ce, color=col, marker="o", ms=3, label=f"GapSlice CEB, {BN[b]}")
            a.plot(H, cl, color=col, marker="s", ms=3, mfc="white", ls="--", lw=1.0,
                   label=f"reliability class, {BN[b]}")
        a.set_xlabel("time gap $h$ [s]")
        a.set_title(ttl, loc="left")
        a.set_xlim(0.25, 2.55); a.set_ylim(0, 1000)
    ax[0].set_ylabel("PRB-slots per link per CAM period")
    ax[0].legend(loc="upper right", fontsize=6.0)
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig_ceb")


def fig_tail():
    from gapslice.stats import wilson
    T = dict(np.load(paths.inp("tail_table.npz")))
    e1 = json.load(open(paths.inp("e1.json")))
    R = int(T["R"]); q = T["Q"]
    iN = list(T["NS"]).index(5); im = list(T["ETAS"]).index(0.3)
    names = {"iid": 0.0, "burst2": 2.0, "burst4": 4.0}
    fig, ax = plt.subplots(1, 2, figsize=(W2, 2.1), sharey=True)
    for a, h, lab in zip(ax, [0.6, 1.0], "ab"):
        ih = list(np.round(T["H"], 2)).index(h)
        for col, b in zip(ORD3, [0.0, 2.0, 4.0]):
            k = T["K"][ih, list(T["BETAS"]).index(b), im, iN]
            ok = k >= 0
            ci = np.array([wilson(int(x), R) for x in k[ok]])
            a.fill_between(q[ok], 100 * ci[:, 0], 100 * ci[:, 1], color=col, alpha=0.25, lw=0)
            a.plot(q[ok], 100 * k[ok] / R, color=col, marker="o", ms=2.5, label=BN[b])
            bn = {0.0: "iid", 2.0: "burst2", 4.0: "burst4"}[b]
            pc = [r for r in e1["B"] if r["h"] == h and r["beta"] == bn and r.get("tag") == "p_c"]
            if pc:
                a.plot([1 - pc[0]["p"]], [100 * pc[0]["growth_viol105"]], marker="*", ms=8, color=col,
                       mec=INK, mew=0.5, ls="none")
        a.axhline(1.0, color=INK2, lw=0.8)
        a.set_xscale("log"); a.set_yscale("symlog", linthresh=1.0); a.invert_xaxis()
        a.set_xlabel("loss probability $1-p$")
        a.set_title(f"({lab}) $h$ = {h} s, 5 trucks", loc="left")
    ax[0].set_ylabel("P(peak error growth > 5 %) [%]")
    ax[0].legend(loc="upper right", title="loss model", title_fontsize=6.5)
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig_tail")


def fig_channel():
    E = json.load(open(paths.inp("e5.json")))
    cv = E["curves"]
    fig, ax = plt.subplots(1, 3, figsize=(W2, 2.15))
    for col, m in zip(ORD3, ["1", "2", "4"]):
        r = np.array([x for x in cv[m] if 0 < x[1] < 1 - 1e-6 and x[2] < 50])
        ax[0].plot(r[:, 0], 1 - r[:, 1], color=col, label=f"$m$ = {m} attempt" + ("s" if m != "1" else ""))
        ax[1].plot(1 - r[:, 1], r[:, 2], color=col, marker="o", ms=2, label=f"$m$ = {m}")
    ax[0].set_yscale("log"); ax[0].set_ylim(1e-4, 1); ax[0].set_xlim(0, 260)
    ax[0].set_xlabel("PRB-slots per CAM period"); ax[0].set_ylabel(r"time-averaged loss $1-\bar p$")
    ax[0].set_title("(a) Loss vs. reservation", loc="left"); ax[0].legend(loc="upper right")
    ax[1].set_xscale("log"); ax[1].set_xlim(1e-4, 0.3)
    ax[1].set_xlabel(r"time-averaged loss $1-\bar p$"); ax[1].set_ylabel(r"mean loss-run length $\bar\beta$ [CAMs]")
    ax[1].set_title("(b) Burstiness at equal loss", loc="left"); ax[1].legend(loc="upper left")
    rows = [r for r in E["rows"] if r["link"] == "LOS" and abs(r["dc"] - 10.0) < 1e-9]
    H = [r["h"] for r in rows]
    for rule, col, mk, lb in [("slice", C["orange"], "^", "99.99 % slice"),
                              ("time_avg", C["magenta"], "v", r"time average $(\bar p,\bar\beta)$"),
                              ("per_state", C["blue"], "o", "per slow state (GapSlice)")]:
        g = [np.nan if r[rule] is None else min(r[rule]["gain"], 1.3) for r in rows]
        ax[2].plot(H, g, color=col, marker=mk, ms=3.5, label=lb)
    ax[2].axhline(P.GAMMA_LINK, color=INK2, lw=0.8)
    ax[2].text(H[0], P.GAMMA_LINK + 0.003, "contract", color=INK2, fontsize=6.2)
    ax[2].set_ylim(0.995, 1.09)
    ax[2].set_xlabel("time gap $h$ [s]"); ax[2].set_ylabel("certified gain over joint modes")
    ax[2].set_title("(c) Contract check by planning rule", loc="left")
    ax[2].legend(loc="upper left", fontsize=5.9)
    fig.tight_layout(w_pad=1.0)
    save(fig, "fig_channel")


def fig_waterfill():
    rows = json.load(open(paths.inp("e2.json")))
    fig, ax = plt.subplots(1, 1, figsize=(W1, 2.0))
    Ns = [3, 5, 7, 9]
    for col, (b, h) in zip([C["blue"], "#104281", C["aqua"]], [(2.0, 0.6), (2.0, 1.0), (0.0, 0.6)]):
        for nb, mk in [(1, "o"), (2, "s")]:
            y = []
            for N in Ns:
                r = next(r for r in rows if r["beta"] == b and r["h"] == h and r["N"] == N and r["blocked"] == nb)
                y.append(100 * (1 - r["waterfill"] / r["uniform"]))
            lb = ("i.i.d." if b == 0 else r"$\beta$=2") + f", $h$={h}, {nb} blocked"
            ax.plot(Ns, y, color=col, marker=mk, ms=3.5, mfc="white" if nb == 2 else col, label=lb)
    ax.set_xticks(Ns); ax.set_xlabel("platoon length $N$ [trucks]")
    ax.set_ylabel("saving vs. per-vehicle split [%]"); ax.set_ylim(0, 16)
    ax.legend(fontsize=6.0, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.25), columnspacing=0.8)
    save(fig, "fig_waterfill")


POL3 = [("Market (CEB)", C["blue"], "o", "GapSlice market (Alg. 1)"),
        ("Market (classes)", C["aqua"], "s", "market, reliability classes"),
        ("CEB-fixed", C["yellow"], "D", "CEB-fixed"),
        ("99.99%-fixed", C["orange"], "^", "99.99 %-fixed"),
        ("Equal share", C["magenta"], "v", "equal share")]


def fig_market():
    fig, ax = plt.subplots(1, 3, figsize=(W2, 2.15))
    for a, tag, ttl in [(ax[0], "A", "(a) Utility, type A"), (ax[1], "B", "(b) Utility, type B")]:
        E = json.load(open(paths.inp(f"e3_{tag}.json")))
        S, N = E["summary"], E["N"]
        for p, col, mk, lb in POL3:
            y = np.array([S[p][str(n)]["util_ratio"] for n in N])
            lo = np.array([S[p][str(n)]["util_ratio_lo"] for n in N])
            hi = np.array([S[p][str(n)]["util_ratio_hi"] for n in N])
            a.fill_between(N, lo, hi, color=col, alpha=0.25, lw=0)
            a.plot(N, y, color=col, marker=mk, ms=3, label=lb)
        a.set_xlabel("platoon tenants in the cell"); a.set_title(ttl, loc="left")
        a.set_ylim(0.3, 1.03)
    ax[0].set_ylabel("total utility / optimum of P1")
    ax[0].legend(loc="lower left", fontsize=5.8)
    E = json.load(open(paths.inp("e3_A.json"))); S, N = E["summary"], E["N"]
    for p, col, mk, lb in POL3:
        ax[2].plot(N, [100 * S[p][str(n)]["cacc_frac"] for n in N], color=col, marker=mk, ms=3, label=lb)
    opt, = ax[2].plot(N, [100 * S["Oracle"][str(n)]["cacc_frac"] for n in N], color=C["gray"], lw=1.0,
                      marker="x", ms=3.5, label="optimum of P1 (other colours as in (a))")
    ax[2].set_xlabel("platoon tenants in the cell"); ax[2].set_ylabel("tenants in CACC [%]")
    ax[2].set_title("(c) Platoons kept in CACC, type A", loc="left"); ax[2].set_ylim(0, 105)
    ax[2].legend(handles=[opt], loc="upper right", fontsize=5.8)
    fig.tight_layout(w_pad=1.0)
    save(fig, "fig_market")


SPOL = [("LTR (Alg. 2)", C["blue"], "LTR (Alg. 2)"), ("Wait-for-maneuver", C["yellow"], "wait for maneuver"),
        ("Graduated", C["aqua"], "graduated"), ("Naive preemption", C["orange"], "naive preemption"),
        ("Static", C["magenta"], "static (next epoch)")]


def fig_surge():
    """Priority surge of 30 %: service curve (type A) and three grouped
    metrics for both contract types: time to serve 95 %, unserved share in
    the first 10 s, and increase of the lenders' per-event risk."""
    fig, ax = plt.subplots(1, 4, figsize=(W2, 2.15), gridspec_kw=dict(width_ratios=[1.3, 1, 1, 1]))
    E = json.load(open(paths.inp("e4_A.json")))
    tg = np.arange(0, 90.0, 0.05)[::4] - 5.0
    for p, col, lb in SPOL:
        cur = np.mean([np.array(s["curve"]) for s in E["service"]["0.3"][p]], axis=0)
        ax[0].plot(tg, 100 * cur, color=col, label=lb, lw=1.3)
    ax[0].set_xlim(-0.5, 40); ax[0].set_ylim(0, 103)
    ax[0].set_xlabel("time since surge [s]"); ax[0].set_ylabel("surge demand served [%]")
    ax[0].set_title("(a) Service, type A", loc="left")
    ax[0].legend(loc="lower right", fontsize=5.4, handlelength=1.4)
    pols = ["LTR (Alg. 2)", "Wait-for-maneuver", "Graduated", "Naive preemption", "Static"]
    labs = ["LTR", "wait", "grad.", "naive", "static"]
    x = np.arange(len(pols)); w = 0.38
    for off, tag, col in [(-w / 2, "A", C["blue"]), (w / 2, "B", C["aqua"])]:
        Es = json.load(open(paths.inp(f"e4_{tag}.json")))["summary"]
        t95 = [Es["service"]["0.3"][p]["t95"] for p in pols]
        un = [100 * Es["service"]["0.3"][p]["unserved10"] for p in pols]
        ax[1].bar(x + off, t95, width=w - 0.04, color=col, label=f"type {tag}")
        ax[2].bar(x + off, un, width=w - 0.04, color=col, label=f"type {tag}")
        ref = Es["sim"]["No surge (reference)"]
        d, hw_ = [], []
        for p in pols[:4]:
            s_ = Es["sim"][p]
            d.append(100 * (s_["risk"] - ref["risk"]))
            # interval of the difference: combine the two Wilson half-widths
            hw_.append(100 * np.hypot((s_["ci"][1] - s_["ci"][0]) / 2, (ref["ci"][1] - ref["ci"][0]) / 2))
        ax[3].bar(np.arange(4) + off, d, width=w - 0.04, color=col, label=f"type {tag}",
                  yerr=[hw_, hw_], error_kw=dict(lw=0.6, capsize=1.2, ecolor=INK2))
    for a in ax[1:3]:
        a.set_xticks(x); a.set_xticklabels(labs, fontsize=5.8, rotation=35, ha="right", rotation_mode="anchor")
        a.grid(axis="x", visible=False)
    ax[1].set_ylabel("time to serve 95 % [s]"); ax[1].set_title("(b) Time to serve 95 %", loc="left")
    ax[2].set_ylabel("unserved in first 10 s [%]"); ax[2].set_title("(c) Unserved after 10 s", loc="left")
    ax[1].legend(loc="upper left", fontsize=5.8)
    ax[3].set_xticks(np.arange(4)); ax[3].grid(axis="x", visible=False)
    ax[3].set_xticklabels(labs[:4], fontsize=5.8, rotation=35, ha="right", rotation_mode="anchor")
    ax[3].axhline(0, color=INK2, lw=0.8)
    ax[3].set_ylabel("risk increase [pp]"); ax[3].set_title("(d) Lenders' per-event risk", loc="left")
    fig.tight_layout(w_pad=0.5)
    save(fig, "fig_surge")


CMP = [("GapSlice", C["blue"], "GapSlice"),
       ("Yan-Harri (matched)", C["orange"], "Yan-Härri"),
       ("Zhang (matched)", C["aqua"], "Zhang et al."),
       ("Lu (matched)", C["magenta"], "Lu et al."),
       ("99.99% slice", C["gray"], "99.99 % slice")]


def fig_compare():
    """Comparison with three published methods (adapted implementations).
    Rows: contract type A and B. Columns: per-link PRBs at fixed gaps
    (outcome-matched modes), delivered utility and platoons kept in CACC
    versus the number of tenants (both modes)."""
    fig, ax = plt.subplots(2, 3, figsize=(W2, 4.3), gridspec_kw=dict(width_ratios=[1.1, 1, 1]))
    LINES = [("GapSlice", C["blue"], "-", "GapSlice"),
             ("Yan-Harri (matched)", C["orange"], "-", "Yan-Härri, matched"),
             ("Yan-Harri (original)", C["orange"], ":", "Yan-Härri, original"),
             ("Zhang (matched)", C["aqua"], "-", "Zhang et al., matched"),
             ("Zhang (original)", C["aqua"], ":", "Zhang et al., original"),
             ("Lu (matched)", C["magenta"], "-", "Lu et al., matched"),
             ("Lu (original)", C["magenta"], ":", "Lu et al., original")]
    for r, tag in enumerate("AB"):
        E = json.load(open(paths.inp(f"e8_{tag}.json")))
        PL, S, N = E["per_link"], E["summary"], E["N"]
        a = ax[r, 0]
        H = list(PL.keys())
        w = 0.16
        for i, (m, col, lb) in enumerate(CMP):
            x = np.arange(len(H)) + (i - 2) * w
            v = np.array([PL[h][m]["mean"] if PL[h][m] else np.nan for h in H])
            lo = np.array([PL[h][m]["lo"] if PL[h][m] else np.nan for h in H])
            hi = np.array([PL[h][m]["hi"] if PL[h][m] else np.nan for h in H])
            a.bar(x, v, width=w * 0.92, color=col, label=lb, yerr=[v - lo, hi - v],
                  error_kw=dict(lw=0.6, capsize=1.2, ecolor=INK2))
        a.set_yscale("log"); a.set_ylim(0.8, 30)
        a.set_yticks([1, 2, 5, 10, 20]); a.set_yticklabels(["1", "2", "5", "10", "20"])
        a.set_xticks(np.arange(len(H))); a.set_xticklabels([f"{float(h):.1f} s" for h in H])
        a.set_xlabel("time gap"); a.grid(axis="x", visible=False)
        a.set_ylabel("PRBs per link / GapSlice")
        a.set_title(f"({'ad'[r]}) PRBs per link, type {tag}", loc="left")
        for m, col, ls, lb in LINES + [("Oracle", C["gray"], "-", "optimum of P1")]:
            y = np.array([S[m][str(n)]["util"] for n in N])
            lo = np.array([S[m][str(n)]["util_lo"] for n in N]); hi = np.array([S[m][str(n)]["util_hi"] for n in N])
            if m != "Oracle":
                ax[r, 1].fill_between(N, lo, hi, color=col, alpha=0.2, lw=0)
                ax[r, 1].plot(N, y, color=col, ls=ls, marker="o", ms=2.5, label=lb)
            mk = "x" if m == "Oracle" else "o"
            ax[r, 2].plot(N, [100 * S[m][str(n)]["cacc_delivered"] for n in N], color=col, ls=ls,
                          lw=1.0 if m == "Oracle" else 1.5, marker=mk, ms=3 if m == "Oracle" else 2.5, label=lb)
        ax[r, 1].set_ylim(0, 1.05); ax[r, 1].set_xticks(N)
        ax[r, 1].set_xlabel("platoon tenants in the cell"); ax[r, 1].set_ylabel("delivered utility / optimum")
        ax[r, 1].set_title(f"({'be'[r]}) Multi-tenant utility, type {tag}", loc="left")
        ax[r, 2].set_ylim(0, 72); ax[r, 2].set_xticks(N)
        ax[r, 2].set_xlabel("platoon tenants in the cell"); ax[r, 2].set_ylabel("in CACC, contract met [%]")
        ax[r, 2].set_title(f"({'cf'[r]}) Platoons kept in CACC, type {tag}", loc="left")
    ax[0, 0].legend(loc="upper left", fontsize=5.6, ncol=2, columnspacing=0.8)
    h_, l_ = ax[0, 2].get_legend_handles_labels()
    fig.tight_layout(h_pad=0.8, w_pad=0.8, rect=(0, 0.07, 1, 1))
    fig.legend(h_, l_, loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=4, fontsize=5.8,
               columnspacing=1.2, handlelength=2.0)
    save(fig, "fig_compare")


def fig_compare_outcome():
    """Outcome of every policy at 20 tenants: platoons meeting the contract,
    platoon-level availability, per-event risk and smallest bumper distance
    (both contract types)."""
    M = [("GapSlice", "Gap-\nSlice"), ("Yan-Harri (original)", "Y-H\nor."), ("Yan-Harri (matched)", "Y-H\nma."),
         ("Zhang (original)", "Zh.\nor."), ("Zhang (matched)", "Zh.\nma."),
         ("Lu (original)", "Lu\nor."), ("Lu (matched)", "Lu\nma."), ("Oracle", "Opt.")]
    fig, ax = plt.subplots(2, 2, figsize=(W2, 3.6))
    ax = ax.ravel()
    x = np.arange(len(M)); w = 0.38
    for off, tag, col in [(-w / 2, "A", C["blue"]), (w / 2, "B", C["aqua"])]:
        S = json.load(open(paths.inp(f"e8_{tag}.json")))["summary"]
        met = [100 * (S[m]["20"]["met"] or 0) for m, _ in M]
        av = [100 * (S[m]["20"]["avail_mean"] or np.nan) for m, _ in M]
        avmin = [100 * (S[m]["20"]["avail_min"] or np.nan) for m, _ in M]
        rk = np.array([100 * S[m]["sim"]["risk"] for m, _ in M])
        lo = np.array([100 * S[m]["sim"]["ci"][0] for m, _ in M]); hi = np.array([100 * S[m]["sim"]["ci"][1] for m, _ in M])
        dm = [S[m]["sim"]["dmin1"] for m, _ in M]
        ax[0].bar(x + off, met, width=w - 0.04, color=col, label=f"type {tag}")
        ax[1].bar(x + off, av, width=w - 0.04, color=col, label=f"type {tag}")
        ax[1].plot(x + off, avmin, ls="none", marker="_", ms=6, mew=1.2, color=INK)
        ax[2].bar(x + off, rk, width=w - 0.04, color=col, label=f"type {tag}",
                  yerr=[rk - lo, hi - rk], error_kw=dict(lw=0.6, capsize=1.2, ecolor=INK2))
        ax[3].bar(x + off, dm, width=w - 0.04, color=col, label=f"type {tag}")
    ax[1].axhline(95, color=INK2, lw=0.8, ls="--"); ax[1].set_ylim(0, 102)
    ax[0].set_ylim(0, 105); ax[3].set_ylim(0, 8.5)
    ax[0].set_ylabel("contract met [%]"); ax[1].set_ylabel("platoon availability [%]")
    ax[2].set_ylabel("per-event risk [%]"); ax[3].set_ylabel("bumper distance [m]")
    for a, t in zip(ax, ["(a) Platoons meeting the string-stability target",
                         "(b) Platoon-level availability (bar: mean, tick: min.)",
                         "(c) Per-event error growth > 5 %",
                         "(d) Smallest bumper distance (1st percentile)"]):
        a.set_xticks(x); a.set_xticklabels([l for _, l in M], fontsize=6.0)
        a.set_title(t, loc="left", fontsize=7.0); a.grid(axis="x", visible=False)
    h_, l_ = ax[0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.035), fontsize=6.6)
    fig.tight_layout(h_pad=0.8, w_pad=1.0)
    save(fig, "fig_compare_outcome")


def fig_desc_ceb():
    """Main-paper figure: control descriptors (types A and B) and the
    resulting PRBs per link (CEB) against the outcome-matched reliability
    class and the 99.99 % slice."""
    from gapslice.descriptor.tables import p_c, p_tail
    G = dict(np.load(paths.inp("gain_curves.npz")))
    T = dict(np.load(paths.inp("tail_table.npz")))
    F = json.load(open(paths.inp("feas.json")))["rows"]
    fig, ax = plt.subplots(1, 3, figsize=(W2, 2.75), gridspec_kw=dict(width_ratios=[1.1, 1, 1]))
    H = [float(h) for h in G["H"] if h < P.H_ACC - 1e-9]
    HB = [float(h) for h in T["H"]]
    for col, b in zip(ORD3, [0.0, 2.0, 4.0]):
        pa = np.array([p_c(h, b, P.GAMMA_LINK) for h in H])
        ax[0].plot(H, 1 - pa, color=col, marker="o", ms=2.6, label=f"A, {BN[b]}")
        pb = np.array([p_tail(h, b, 0.3, 5) for h in HB])
        ax[0].plot(HB, 1 - pb, color=col, marker="s", ms=2.6, mfc="white", lw=1.0, ls="--",
                   label=f"B, {BN[b]}")
    ax[0].axhline(1 - P.P_URLLC, color=C["orange"], lw=1.0)
    ax[0].text(0.3, 1.4e-4, "99.99 %", color=C["orange"], fontsize=6.2)
    ax[0].set_yscale("log"); ax[0].set_ylim(5e-5, 1)
    ax[0].set_xlabel("time gap [s]"); ax[0].set_ylabel("tolerable loss probability")
    ax[0].set_title("(a) Control descriptor", loc="left")
    ha, la = ax[0].get_legend_handles_labels()
    for a, typ, ttl in [(ax[1], "A", "(b) PRBs per link, type A"), (ax[2], "B", "(c) PRBs per link, type B")]:
        Hs = [r["h"] for r in F if r["beta"] == "iid"]
        url = [r["urllc"] for r in F if r["beta"] == "iid"]
        a.plot(Hs, url, color=C["orange"], marker="^", ms=2.6, label="99.99 % slice")
        for col, bn, b in [(C["blue"], "iid", 0.0), ("#104281", "burst2", 2.0)]:
            rr = [r for r in F if r["beta"] == bn]
            ce = [np.nan if r[f"ceb_{typ}"] is None else r[f"ceb_{typ}"] for r in rr]
            cl = [np.nan if r[f"cls_{typ}"] is None else r[f"cls_{typ}"] for r in rr]
            a.plot(Hs, ce, color=col, marker="o", ms=2.6, label=f"GapSlice, {BN[b]}")
            a.plot(Hs, cl, color=col, marker="s", ms=2.6, mfc="white", ls="--", lw=1.0,
                   label=f"rel. class, {BN[b]}")
        a.set_xlabel("time gap [s]"); a.set_title(ttl, loc="left")
        a.set_xlim(0.25, 2.55); a.set_ylim(0, 1000)
    ax[1].set_ylabel("PRB-slots per CAM period")
    hb, lb_ = ax[1].get_legend_handles_labels()
    fig.tight_layout(w_pad=0.8, rect=(0, 0.15, 1, 1))
    fig.legend(ha, la, loc="lower left", bbox_to_anchor=(0.03, 0.0), ncol=3, fontsize=5.6,
               title="(a): contract type, loss model", title_fontsize=5.6, columnspacing=0.8, handlelength=2.0)
    fig.legend(hb, lb_, loc="lower right", bbox_to_anchor=(0.99, 0.0), ncol=3, fontsize=5.6,
               title="(b), (c)", title_fontsize=5.6, columnspacing=0.8, handlelength=2.0)
    save(fig, "fig_desc_ceb")


def fig_compare_main():
    """Main-paper comparison figure: PRBs per link at the same target (matched
    modes) and delivered utility (both modes), types A and B."""
    fig, ax = plt.subplots(1, 4, figsize=(W2, 2.55))
    LINES = [("GapSlice", C["blue"], "-", "GapSlice"),
             ("Yan-Harri (matched)", C["orange"], "-", "Yan-Härri, matched"),
             ("Zhang (matched)", C["aqua"], "-", "Zhang et al., matched"),
             ("Lu (matched)", C["magenta"], "-", "Lu et al., matched"),
             ("Yan-Harri (original)", C["orange"], ":", "Yan-Härri, original"),
             ("Zhang (original)", C["aqua"], ":", "Zhang et al., original"),
             ("Lu (original)", C["magenta"], ":", "Lu et al., original")]
    for r, tag in enumerate("AB"):
        E = json.load(open(paths.inp(f"e8_{tag}.json")))
        PL, S, N = E["per_link"], E["summary"], E["N"]
        a = ax[r]
        Hh = list(PL.keys()); w = 0.16
        for i, (m, col, lb) in enumerate(CMP):
            x = np.arange(len(Hh)) + (i - 2) * w
            v = np.array([PL[h][m]["mean"] if PL[h][m] else np.nan for h in Hh])
            lo = np.array([PL[h][m]["lo"] if PL[h][m] else np.nan for h in Hh])
            hi = np.array([PL[h][m]["hi"] if PL[h][m] else np.nan for h in Hh])
            a.bar(x, v, width=w * 0.92, color=col, label=lb, yerr=[v - lo, hi - v],
                  error_kw=dict(lw=0.5, capsize=1.0, ecolor=INK2))
        a.set_yscale("log"); a.set_ylim(0.8, 30)
        a.set_yticks([1, 2, 5, 10, 20]); a.set_yticklabels(["1", "2", "5", "10", "20"])
        a.set_xticks(np.arange(len(Hh))); a.set_xticklabels([f"{float(h):.1f} s" for h in Hh])
        a.set_xlabel("time gap"); a.grid(axis="x", visible=False)
        a.set_title(f"({'ab'[r]}) PRBs per link, type {tag}", loc="left", fontsize=6.8)
        b_ = ax[2 + r]
        for m, col, ls, lb in LINES:
            y = np.array([S[m][str(n)]["util"] for n in N])
            lo = np.array([S[m][str(n)]["util_lo"] for n in N]); hi = np.array([S[m][str(n)]["util_hi"] for n in N])
            b_.fill_between(N, lo, hi, color=col, alpha=0.2, lw=0)
            b_.plot(N, y, color=col, ls=ls, marker="o", ms=2.2, lw=1.3, label=lb)
        b_.set_ylim(0, 1.05); b_.set_xticks(N)
        b_.set_xlabel("platoon tenants in the cell")
        b_.set_title(f"({'cd'[r]}) Utility, type {tag}", loc="left", fontsize=6.8)
    ax[0].set_ylabel("PRBs per link / GapSlice")
    ax[2].set_ylabel("delivered utility / optimum")
    hb, lb_ = ax[0].get_legend_handles_labels()
    hl, ll = ax[2].get_legend_handles_labels()
    fig.tight_layout(w_pad=0.6, rect=(0, 0.16, 1, 1))
    fig.legend(hb, lb_, loc="lower left", bbox_to_anchor=(0.02, 0.0), ncol=2, fontsize=5.6,
               title="(a), (b): outcome-matched", title_fontsize=5.6, columnspacing=0.8, handlelength=1.4)
    fig.legend(hl, ll, loc="lower right", bbox_to_anchor=(0.99, 0.0), ncol=3, fontsize=5.6,
               title="(c), (d)", title_fontsize=5.6, columnspacing=0.8, handlelength=1.8)
    save(fig, "fig_compare_main")


ALL = ["descriptor", "ceb", "tail", "channel", "waterfill", "market", "surge",
       "compare", "compare_outcome", "desc_ceb", "compare_main"]


def main(names=None):
    for name in names or ALL:
        globals()["fig_" + name]()
        print("ok", name)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
