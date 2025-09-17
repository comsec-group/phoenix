#!/usr/bin/env python3
"""
Extract indices_not_bitflipped from a JSON-per-line log, compute probabilities,
and save a CSV + bar-chart PNG.

New in this version
-------------------
*  --hline / -l  FLOAT   Draw a horizontal reference line at that probability.
                         You may provide the flag multiple times for several lines,
                         e.g.  -l 0.01 -l 0.05

Examples
--------
# Basic usage, add a line at 0.012
python extract_probabilities.py results.jsonl -l 0.012

# Two reference lines and custom plot filename
python extract_probabilities.py results.jsonl -l 0.012 -l 0.05 -p myplot.png
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Dict, Tuple
import sys

# import plot_settings
# from .. import plot_settings
import matplotlib.pyplot as plt


# ---------- helpers -------------------------------------------------- #
def read_json_lines(lines: Iterable[str]) -> List[Dict]:
    return [json.loads(line) for line in lines if line.strip()]


def compute_probabilities(records: List[Dict]) -> Tuple[Counter, Dict[int, float]]:
    total_records = len(records)
    flat_indices = [
        idx
        for rec in records
        for idx in rec["data"]["indices_not_bitflipped"]
    ]
    counts = Counter(flat_indices)
    probabilities = {idx: cnt / total_records for idx, cnt in counts.items()}
    return counts, probabilities


def save_csv(path: Path, counts: Counter, probs: Dict[int, float], dec: int) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "count", "probability"])
        fmt = f"{{:.{dec}f}}"
        for idx in sorted(counts):
            w.writerow([idx, counts[idx], fmt.format(probs[idx])])


def plot_probabilities(
    path: Path,
    probs: Dict[int, float],
    title: str,
    hlines: List[float] | None = None,
) -> None:
    if not probs:
        return
    fig, ax = plt.subplots(figsize=(500.4 / 72 * 0.5, 0.9))
    # subtract 0.0122 from each probability
    adj_probs = {idx: val - 0.0122 for idx, val in probs.items()}
    ax.bar(adj_probs.keys(), adj_probs.values())
    ax.set_xlabel("ACT Slot Within tREFI Interval", labelpad=1.5)
    ax.set_ylabel("Probability")
    ax.set_ylim(0, 0.155)
    # draw reference lines
    if hlines:
        for y in hlines:
            ax.axhline(y, linestyle="--", linewidth=1)
    ax.set_yticks([i * 0.05 for i in range(int(ax.get_ylim()[1] / 0.05) + 1)])
    ax.set_xticks(range(0, int(max(probs.keys()) + 1), 5), minor=True)
    ax.tick_params(axis='x', which='minor', labelbottom=False)
    for ytick in ax.get_yticks():
        ax.axhline(y=ytick, color='gray', linestyle='--', linewidth=0.5)
    ax.margins(x=0.005)
    # Arrow from top to last bar
    last_idx = max(adj_probs.keys())
    last_val = adj_probs[last_idx]
    ax.annotate(
        "",
        xy=(last_idx, ax.get_ylim()[1]-0.155),
        xytext=(last_idx, -0.055),
        arrowprops=dict(arrowstyle="simple", color="red", lw=1.2),
        annotation_clip=False,
    )
    fig.savefig(path, dpi=72, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def read_csv(path: Path) -> Dict[int, float]:
    """Read index/probability pairs from a CSV file."""
    probs = {}
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["index"])
            prob = float(row["probability"])
            probs[idx] = prob
    return probs


# ---------- CLI ------------------------------------------------------ #
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extract indices_not_bitflipped, compute probabilities, "
        "and save CSV + PNG bar chart."
    )
    p.add_argument(
        "file",
        nargs="?",
        default="-",
        type=str,
        help="Path to JSONL or CSV file (default: stdin for JSONL).",
    )
    p.add_argument(
        "-d",
        "--decimal",
        type=int,
        default=4,
        help="Decimal places for probabilities in CSV (default: 4).",
    )
    p.add_argument(
        "--output", "-o",
        metavar="FILE",
        type=Path,
        default=Path("../indices_probabilities.pdf"),
        help="Output file for plot (default: ../indices_probabilities.pdf).",
    )
    p.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip creating the PNG plot.",
    )
    p.add_argument(
        "-c",
        "--csv",
        metavar="CSV",
        type=Path,
        default=Path("indices_probabilities.csv"),
        help="Filename for CSV summary (default: indices_probabilities.csv).",
    )
    p.add_argument(
        "-l",
        "--hline",
        action="append",
        type=float,
        default=[],
        metavar="FLOAT",
        help="Draw a horizontal reference line at this probability; "
        "may be given multiple times.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.file

    # Determine file type
    if input_path == "-" or input_path.endswith(".jsonl"):
        # JSONL input
        if input_path == "-":
            lines = [line for line in sys.stdin]
        else:
            with open(input_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        records = read_json_lines(lines)
        if not records:
            print("No JSON objects found.")
            return
        counts, probs = compute_probabilities(records)
        total_records = len(records)
        # console output
        print(f"Total JSON entries: {total_records}\n")
        print("Counts per index:")
        for idx in sorted(counts):
            print(f"  {idx}: {counts[idx]}")
        fmt = f"{{:.{args.decimal}f}}"
        print("\nProbabilities:")
        for idx in sorted(probs):
            print(f"  {idx}: {fmt.format(probs[idx])}")
        # Save CSV
        save_csv(args.csv, counts, probs, args.decimal)
        print(f"\nCSV saved to: {args.csv.resolve()}")
    elif input_path.endswith(".csv"):
        # CSV input
        probs = read_csv(Path(input_path))
        print(f"Loaded probabilities from CSV: {input_path}")
    else:
        print("Unsupported file type. Please provide a .jsonl or .csv file.")
        return

    # Plot
    if not args.no_plot:
        plot_probabilities(
            args.output,
            probs,
            "Probability of indices_not_bitflipped",
            hlines=args.hline,
        )
        print(f"Plot saved to: {args.output.resolve()}")


if __name__ == "__main__":
    main()
    main()
