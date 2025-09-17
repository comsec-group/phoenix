#!/usr/bin/env python3
"""
Rowhammer heat-map generator
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors

# ---------------------------------------------------------------------------
# Global plotting style
# ---------------------------------------------------------------------------

try:
    import plot_settings  # noqa: F401 – rcParams set on import
except ModuleNotFoundError:
    mpl.rcParams.update({
        "font.family": "serif",
        "font.size": 11,
        "text.usetex": mpl.rcParams.get("text.usetex", False),
        "axes.labelsize": 11,
        "axes.titlesize": 11,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
    })

DEFAULT_CMAP = "Blues"
DEFAULT_WIDTH_PT = 243.91125  # IEEE single-column width
PT_PER_IN = 72.27  # TeX points per inch
DEFAULT_TREFW = 8192  # default tREFW window size (in tREFI)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Rowhammer heat-map (percentage of flipped rows per setting)"
    )
    p.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Path to the input CSV file",
    )

    # ── iteration flag ─────────────────────────────────────────────────────
    p.add_argument(
        "--iteration",
        type=int,
        metavar="N",
        help="Only consider results from iteration number N",
    )
    # ───────────────────────────────────────────────────────────────────────

    # Output & format
    p.add_argument("-o", "--output", type=Path, help="Image output path [combined.png]")
    p.add_argument("--pdf", action="store_true", help="Also save a PDF next to the image")
    p.add_argument("--cmap", default=DEFAULT_CMAP, help=f"Matplotlib colormap [{DEFAULT_CMAP}]")

    # Sizing
    p.add_argument(
        "--width-pt",
        type=float,
        default=DEFAULT_WIDTH_PT,
        help="Figure width in TeX points [%(default).2f] — matches \\columnwidth",
    )
    p.add_argument(
        "--height-pt",
        type=float,
        default=None,
        help="Figure height in TeX points [auto: square cells]",
    )
    p.add_argument(
        "--auto-height",
        choices=["on", "off"],
        default="on",
        help="When --height-pt is omitted: adjust height to get square cells [on]",
    )

    # Filters
    p.add_argument("--acts", type=int, nargs="+", metavar="ACT", help="Filter by ACTs/tREFI values")
    p.add_argument("--trefi", type=int, nargs="+", metavar="TREFI",
                   help="Filter by tREFI multiples (refs_executed column)")

    # tREFW window size
    p.add_argument(
        "--trefw",
        type=int,
        default=DEFAULT_TREFW,
        help="Size of tREFW window in tREFI (x-axis labels are refs_executed/--trefw)",
    )

    return p.parse_args()


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def load(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"CSV file not found: {path}")
    print(f"loading data from {path} …")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------

def validate(df: pd.DataFrame) -> None:
    need = {"row", "bit_flip_bit", "refs_executed", "acts_per_trefi", "iteration"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"missing columns: {', '.join(sorted(missing))}")


def best_setting_per_row(df: pd.DataFrame) -> pd.DataFrame:
    per_iter = (
        df.groupby(["row", "acts_per_trefi", "refs_executed", "iteration"])["bit_flip_bit"]
        .nunique()
        .reset_index(name="bit_flips")
    )
    idx = per_iter.groupby(["row", "acts_per_trefi", "refs_executed"])["bit_flips"].idxmax()
    return per_iter.loc[idx].copy()


def summarise(best: pd.DataFrame) -> pd.DataFrame:
    total_rows = best["row"].nunique()
    s = (
        best.groupby(["acts_per_trefi", "refs_executed"])
        .agg(rows_flipped=("row", "nunique"))
        .reset_index()
    )
    s["percent_rows"] = 100.0 * s["rows_flipped"] / total_rows
    return s


def pivot_percent(s: pd.DataFrame) -> pd.DataFrame:
    return (
        s.pivot(index="acts_per_trefi", columns="refs_executed", values="percent_rows")
        .sort_index()
        .sort_index(axis=1)
    )


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------

def _contrast(val: float, cmap, norm) -> str:
    r, g, b, _ = cmap(norm(val))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "black" if lum > 0.55 else "white"


def _figure_size(width_pt: float, rows: int, cols: int,
                 height_pt: Optional[float], auto_height: bool) -> tuple[float, float]:
    width_in = width_pt / PT_PER_IN
    if height_pt is not None:
        height_in = height_pt / PT_PER_IN
    else:
        height_in = width_in * rows / cols * 0.68 if auto_height else width_in * 6 / 10
    return width_in, height_in


def _format_trefw_labels(refs: list[int], trefw: int) -> list[str]:
    labels = []
    for r in refs:
        val = r / trefw
        labels.append(str(int(val)) if abs(val - round(val)) < 1e-6 else f"{val:.2f}")
    return labels


def plot(mat: pd.DataFrame, stats: pd.DataFrame, dst: Path,
         *, cmap_name: str, save_pdf: bool,
         width_pt: float, height_pt: Optional[float], auto_height: bool, trefw: int) -> None:
    width_in, height_in = _figure_size(width_pt, mat.shape[0], mat.shape[1],
                                       height_pt, auto_height)

    cmap = plt.get_cmap(cmap_name)
    norm = mcolors.Normalize(vmin=0, vmax=100)

    fig, ax = plt.subplots(figsize=(width_in, height_in))
    im = ax.imshow(mat.values, cmap=cmap, norm=norm, aspect="auto")

    for i, acts in enumerate(mat.index):
        for j, reps in enumerate(mat.columns):
            cell = stats[(stats["acts_per_trefi"] == acts) & (stats["refs_executed"] == reps)]
            if cell.empty:
                label, colour = "–", "white"
            else:
                pct = cell["percent_rows"].iloc[0]
                label = f"{pct:.1f}".rstrip("0").rstrip(".")
                colour = _contrast(pct, cmap, norm)
            ax.text(j, i, label, ha="center", va="center", color=colour, fontsize=8)

    ax.set_xticks(np.arange(len(mat.columns)),
                  labels=_format_trefw_labels(list(mat.columns), trefw))
    ax.set_xlabel("#tREFWs")
    ax.set_yticks(np.arange(len(mat.index)), labels=mat.index)
    ax.set_ylabel("ACTs/tREFI")

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.set_ylabel("#Rows flipped\n[%]", rotation=90)

    fig.tight_layout()
    fig.savefig(dst, dpi=300)
    if save_pdf:
        fig.savefig(dst.with_suffix(".pdf"), format="pdf")
    print(f"saved → {dst.resolve()}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    df = load(args.csv)
    validate(df)

    # ── iteration flag use ─────────────────────────────────────────────────
    if args.iteration is not None:
        df = df[df["iteration"] == args.iteration]
        if df.empty:
            raise SystemExit(f"No data for iteration {args.iteration}.")
    # ───────────────────────────────────────────────────────────────────────

    if args.acts:
        df = df[df["acts_per_trefi"].isin(args.acts)]
        if df.empty:
            raise SystemExit("No data left after filtering by --acts.")

    if args.trefi:
        df = df[df["refs_executed"].isin(args.trefi)]
        if df.empty:
            raise SystemExit("No data left after filtering by --trefi.")

    best = best_setting_per_row(df)
    stats = summarise(best)
    mat = pivot_percent(stats)

    out = args.output or Path("combined.png")
    if out.suffix.lower() not in {".png", ".pdf", ".svg", ".eps"}:
        out = out.with_suffix(".png")

    plot(
        mat,
        stats,
        out,
        cmap_name=args.cmap,
        save_pdf=args.pdf,
        width_pt=args.width_pt,
        height_pt=args.height_pt,
        auto_height=(args.auto_height == "on"),
        trefw=args.trefw,
    )


if __name__ == "__main__":
    main()
