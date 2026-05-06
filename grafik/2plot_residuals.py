"""
plot_residuals.py
-----------------
Parse an OpenFOAM log.foamRun and plot residuals, Courant numbers, and deltaT.

Usage:
    python grafik/2plot_residuals.py grafik/log.run --output grafik/output --linear --dpi 150
"""

import re
import sys
import argparse
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D
import numpy as np


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
RE_TIME       = re.compile(r"^Time = ([\d.eE+\-]+)\s*$")
RE_SOLVE      = re.compile(r"Solving for (\w+),\s+Initial residual = ([\d.eE+\-]+)")
RE_COURANT    = re.compile(r"Courant Number mean:\s*([\d.eE+\-]+)\s+max:\s*([\d.eE+\-]+)")
RE_DELTAT     = re.compile(r"^deltaT\s*=\s*([\d.eE+\-]+)")
RE_EXECTIME   = re.compile(r"^ExecutionTime = ([\d.eE+\-]+)")

SKIP_FIELDS   = {"rho"}
RESIDUAL_ORDER = ["Ux", "Uy", "Uz", "p_rgh", "h", "k", "omega"]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def parse_log(log_path: Path) -> dict:
    """
    Returns a dict with:
        residuals  : {field: {"time": [], "initial": []}}
        courant    : {"time": [], "mean": [], "max": []}
        deltaT     : {"time": [], "value": []}
        exec_time  : {"time": [], "wall": []}
    """
    res   = defaultdict(lambda: {"time": [], "initial": []})
    co    = {"time": [], "mean": [], "max": []}
    dt    = {"time": [], "value": []}
    et    = {"time": [], "wall": []}

    current_time   = None
    seen_in_step   = set()

    # Buffered values that arrive before "Time ="
    buf_co_mean    = None
    buf_co_max     = None
    buf_dt         = None

    with log_path.open("r", errors="replace") as fh:
        for line in fh:
            # ----- Courant (arrives before Time =) -----
            m = RE_COURANT.search(line)
            if m:
                buf_co_mean = float(m.group(1))
                buf_co_max  = float(m.group(2))
                continue

            # ----- deltaT (arrives before Time =) -----
            m = RE_DELTAT.match(line)
            if m:
                buf_dt = float(m.group(1))
                continue

            # ----- New time step -----
            m = RE_TIME.match(line)
            if m:
                current_time = float(m.group(1))
                seen_in_step.clear()

                if buf_co_mean is not None:
                    co["time"].append(current_time)
                    co["mean"].append(buf_co_mean)
                    co["max"].append(buf_co_max)
                    buf_co_mean = buf_co_max = None

                if buf_dt is not None:
                    dt["time"].append(current_time)
                    dt["value"].append(buf_dt)
                    buf_dt = None
                continue

            # ----- Solver residuals -----
            m = RE_SOLVE.search(line)
            if m and current_time is not None:
                field = m.group(1)
                if field in SKIP_FIELDS:
                    continue
                if field not in seen_in_step:
                    res[field]["time"].append(current_time)
                    res[field]["initial"].append(float(m.group(2)))
                    seen_in_step.add(field)
                continue

            # ----- Execution time -----
            m = RE_EXECTIME.match(line)
            if m and current_time is not None:
                et["time"].append(current_time)
                et["wall"].append(float(m.group(1)))

    return {
        "residuals": dict(res),
        "courant":   co,
        "deltaT":    dt,
        "exec_time": et,
    }


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------
STYLE = {
    "figure.facecolor":     "#f8f8f8",
    "axes.facecolor":       "#ffffff",
    "axes.edgecolor":       "#555555",
    "axes.linewidth":       0.8,
    "axes.grid":            True,
    "axes.grid.which":      "both",
    "grid.color":           "#dddddd",
    "grid.linewidth":       0.5,
    "grid.linestyle":       "--",
    "xtick.labelsize":      7,
    "ytick.labelsize":      7,
    "axes.labelsize":       8,
    "axes.titlesize":       9,
    "axes.titleweight":     "bold",
    "legend.fontsize":      7,
    "legend.framealpha":    0.7,
    "legend.edgecolor":     "#cccccc",
    "font.family":          "DejaVu Sans",
    "lines.linewidth":      0.9,
    "lines.antialiased":    True,
}

PALETTE = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e",
    "#9467bd", "#8c564b", "#e377c2", "#17becf",
]

def _color(i: int) -> str:
    return PALETTE[i % len(PALETTE)]


def _plot_series(ax, times, values, label, color, log_scale):
    ax.plot(times, values, color=color, lw=0.9, label=label)
    if log_scale and all(v > 0 for v in values):
        ax.set_yscale("log")
        ax.yaxis.set_minor_locator(
            ticker.LogLocator(base=10.0, subs=np.arange(2, 10) * 0.1, numticks=10)
        )
    ax.yaxis.set_major_formatter(ticker.LogFormatterSciNotation() if log_scale else ticker.ScalarFormatter())


def _label_ax(ax, title, ylabel):
    ax.set_title(title, pad=4)
    ax.set_ylabel(ylabel, labelpad=3)


# ---------------------------------------------------------------------------
# Single-panel figure helper
# ---------------------------------------------------------------------------
def _make_fig(title: str) -> tuple:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    fig.patch.set_facecolor(STYLE["figure.facecolor"])
    ax.set_facecolor(STYLE["axes.facecolor"])
    fig.suptitle(title, fontsize=12, fontweight="bold", color="#222222", y=1.01)
    return fig, ax


def _finalise(fig, ax, out_path: Path, dpi: int) -> None:
    ax.tick_params(axis="both", which="both", direction="in", length=3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.7)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=6, prune="both"))
    ax.grid(True, which="both", ls="--", lw=0.5, color="#dddddd")
    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
def plot(data: dict, out_dir: Path, log_scale: bool, dpi: int) -> None:
    residuals = data["residuals"]
    co        = data["courant"]
    dt_data   = data["deltaT"]

    out_dir.mkdir(parents=True, exist_ok=True)

    fields    = [f for f in RESIDUAL_ORDER if f in residuals]
    extra     = [f for f in residuals if f not in RESIDUAL_ORDER]
    all_fields = fields + extra

    with plt.rc_context(STYLE):

        # ----- One figure per residual field -----
        for idx, field in enumerate(all_fields):
            times = residuals[field]["time"]
            vals  = residuals[field]["initial"]
            color = _color(idx)

            fig, ax = _make_fig(f"Residual — {field}")
            _plot_series(ax, times, vals, field, color, log_scale)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Initial residual")
            ax.legend(loc="upper right")
            _finalise(fig, ax, out_dir / f"residual_{field}.png", dpi)

        # ----- Courant number -----
        if co["time"]:
            fig, ax = _make_fig("Courant Number")
            ax.plot(co["time"], co["mean"], color=_color(0), lw=0.9, label="Co mean")
            ax.plot(co["time"], co["max"],  color=_color(1), lw=0.9, label="Co max", ls="--")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Co")
            ax.legend(loc="upper right")
            _finalise(fig, ax, out_dir / "courant.png", dpi)

        # ----- deltaT -----
        if dt_data["time"]:
            fig, ax = _make_fig("Time Step Size")
            ax.plot(dt_data["time"], dt_data["value"], color=_color(2), lw=0.9)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel(r"$\Delta t$ (s)")
            _finalise(fig, ax, out_dir / "deltaT.png", dpi)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Plot OpenFOAM diagnostics from log.foamRun")
    parser.add_argument("log_file", nargs="?", default="log.foamRun")
    parser.add_argument("--output-dir", "-o", default="plots",
                        help="Directory to save individual PNG files (default: plots/)")
    parser.add_argument("--linear", action="store_true",
                        help="Linear y-axis for residuals (default: log)")
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"ERROR: {log_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {log_path} ...")
    data = parse_log(log_path)

    res = data["residuals"]
    if not res:
        print("No solver residuals found.")
        sys.exit(1)

    print(f"Residual fields : {', '.join(res)}")
    print(f"Courant points  : {len(data['courant']['time'])}")
    print(f"deltaT points   : {len(data['deltaT']['time'])}")
    for f, d in res.items():
        t = d["time"]
        print(f"  {f:8s}: {len(t)} pts, t = [{t[0]:.5g}, {t[-1]:.5g}]")

    out_dir = Path(args.output_dir)
    print(f"\nWriting plots to: {out_dir}/")
    plot(data, out_dir, log_scale=not args.linear, dpi=args.dpi)


if __name__ == "__main__":
    main()
