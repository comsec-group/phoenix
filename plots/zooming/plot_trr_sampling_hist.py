#!/usr/bin/env python3
import json
import os
from collections import Counter
import matplotlib.pyplot as plt
import numpy as np
import argparse

import plot_settings


def main():
    parser = argparse.ArgumentParser(description="Plot TRR sampling histograms.")
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="../histogram_combined.pdf",
        help="Output file path for histograms (default: ../histogram_combined.pdf)"
    )
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))

    trefis_folders = {
        "32": os.path.join(current_dir, "trr_sampling_skh304/20250604_213158_tREFIS=32"),
        "64": os.path.join(current_dir, "trr_sampling_skh304/20250604_210955_tREFIS=64"),
        "128": os.path.join(current_dir, "trr_sampling_skh304/20250604_203217_tREFIS=128"),
        "256": os.path.join(current_dir, "trr_sampling_skh304/20250604_205659_tREFIS=256"),
    }

    # Store histogram data for each tREFIS
    histogram_data = {}

    # Process each folder
    for trefis, folder in trefis_folders.items():
        filepath = os.path.join(folder, "no_modulo", "results.jsonl")
        
        if not os.path.isfile(filepath):
            print(f"Warning: File not found: {filepath}")
            continue

        # Count how often each row appears across repetitions
        row_counter = Counter()

        with open(filepath, "r") as file:
            for line in file:
                data = json.loads(line)
                rc_before = data["data"]["refresh_counter_before"]
                indices = data["data"]["indices_not_bitflipped"]
                modulus = int(trefis)
                for idx in indices:
                    row_counter[(rc_before + idx) % modulus] += 1

        # Count how many rows had each appearance count
        count_histogram = Counter(row_counter.values())
        histogram_data[trefis] = count_histogram


    # Plot all histograms in a 4x1 subplot with shared axes
    fig, axs = plt.subplots(4, 1, figsize=(3.3, 2.5), sharex=True, sharey=True)
    for ax, trefis in zip(axs, ["32", "64", "128", "256"]):
        count_histogram = histogram_data[trefis]
        x = sorted(count_histogram.keys())
        y = [count_histogram[val] for val in x]
        total = sum(y) if y else 1
        y = [val / total for val in y]
        colors = ['C0'] * len(x)
        ax.bar(x, y, color=colors)
        
        ax.set_xlim(left=0)
        # Top-right of axes for title
        ax.text(0.97, 0.85, f"{trefis} tREFIS ", ha='right', va='top', transform=ax.transAxes)
        ax.set_axisbelow(True)
        ax.grid(axis='y', linestyle='--')
        
        # ax.minorticks_on()
        # ax.set_xticks(range(min(x), max(x)+1), minor=True)
        # ax.set_yticks(np.arange(0, 0.41, 0.1), minor=True)
        
        ax.set_yticks([0.0, 0.2, 0.4])  # major ticks with labels
        ax.set_yticks(np.arange(0, 0.41, 0.1), minor=True)  # minor ticks
        ax.tick_params(axis='y', which='minor', labelleft=False)  # hide minor tick labels

        ax.tick_params(axis='x', which='minor', labelbottom=False)
        ax.tick_params(axis='y', which='minor', labelleft=False)
        ax.grid(which='minor', axis='y', linestyle=':', color='lightgray')

        # Set minor x-ticks for every integer in range
        ax.set_xticks(range(min(x), max(x) + 1), minor=True)

        # Hide minor x-tick labels
        ax.tick_params(axis='x', which='minor', labelbottom=False)

        # ax.set_ylim(0)
        # ax.set_ylim(0, 55)

    # Shared axis labels
    fig.text(0.5, 0.0, "#TRRs Received", ha='center')
    fig.text(0.00, 0.5, "Unique Rows [%]", va='center', rotation='vertical')

    # plt.tight_layout(rect=[0.05, 0.05, 0.5, 0.5], h_pad=0.4)
    plt.tight_layout(h_pad=0.2, rect=[0.1, 0.05, 1, 0.95])
    plt.savefig(args.output)
    print(f"Saved combined histogram as {args.output}")


    # Compute normalization baseline from 256 tREFIS
    norm_total = 1
    filepath_256 = os.path.join(trefis_folders["256"], "no_modulo", "results.jsonl")
    if os.path.isfile(filepath_256):
        values_256 = []
        with open(filepath_256, "r") as file:
            for line in file:
                data = json.loads(line)
                rc_before = data["data"]["refresh_counter_before"]
                indices = data["data"]["indices_not_bitflipped"]
                values_256.extend((rc_before + idx) % 256 for idx in indices)
        norm_total = sum(Counter(values_256).values()) or 1


    # Second figure: histogram per refresh counter position
    fig2, axs2 = plt.subplots(4, 1, figsize=(3.45, 2.3), sharex=True)
    # Define per-tREFIS y-axis limits
    ylim_map = {
        "32": (0.0, 17),
        "64": (0.0, 17),
        "128": (0.0, 30),
        "256": (0.0, 30),
    }
    for ax, trefis in zip(axs2, ["32", "64", "128", "256"]):
        filepath = os.path.join(trefis_folders[trefis], "no_modulo", "results.jsonl")
        if not os.path.isfile(filepath):
            continue

        values = []
        modulus = int(trefis)
        with open(filepath, "r") as file:
            for line in file:
                data = json.loads(line)
                rc_before = data["data"]["refresh_counter_before"]
                indices = data["data"]["indices_not_bitflipped"]
                values.extend((rc_before + idx) % modulus for idx in indices)

        counter = Counter(values)
        bin_size = 2
        num_bins = (modulus + bin_size - 1) // bin_size
        x = list(range(num_bins))
        y = [sum(counter.get(i, 0) for i in range(b * bin_size, min((b + 1) * bin_size, modulus))) for b in x]
        # No normalization applied

        bar_positions = [b * bin_size for b in x]
        if trefis == "128":
            colors = ['tab:orange'] * len(bar_positions)
        elif trefis == "256":
            colors = ['tan' if pos < 129 else 'darkorange' for pos in bar_positions]
        elif trefis in ["32", "64"]:
            colors = ['dimgray'] * len(bar_positions)
        else:
            colors = ['C0'] * len(bar_positions)
        ax.bar(bar_positions, y, width=bin_size, align='edge', color=colors)
        ax.set_xlim(left=-2, right=modulus + 2)
        ax.set_xticks(np.arange(0, modulus + 1, 32))
        ax.set_xticks(np.arange(0, modulus + 1, 8), minor=True)
        ax.tick_params(axis='x', which='minor', labelbottom=False)
        # ax.text(0.97, 0.7, f"{trefis} tREFIS", ha='right', va='top', transform=ax.transAxes)
        ax.set_axisbelow(True)
        ax.grid(axis='y', linestyle='--', linewidth=0.5)
        # ax.set_yticks([0.0, 0.02])
        # Ensure minor y-ticks at 0, 0.01, 0.02 (including 0.01)
        # ax.set_yticks(np.arange(0, 0.021, 0.01), minor=True)
        ax.tick_params(axis='y', which='minor', labelleft=False)
        # ax.grid(which='minor', axis='y', linestyle=':', color='lightgray')
        ax.tick_params(axis='x', which='minor', labelbottom=False)
        ax.set_ylim(*ylim_map[trefis])
        # Set major and minor y-ticks
        y_min, y_max = ylim_map[trefis]
        ax.set_yticks(np.arange(y_min, y_max + 1, 10))  # major ticks every 10
        ax.set_yticks(np.arange(y_min, y_max + 1, 5), minor=True)  # minor ticks every 5
        ax.tick_params(axis='y', which='minor', labelleft=False)  # hide minor tick labels
        # Removed axhline at 0.01 to use minor gridline instead
        
        max_x = 257
        if trefis == "32":
            ax.axvspan(32, max_x, color='lightgray', alpha=0.3, zorder=3)
            ax.text((int(trefis) + max_x) / 2, 10.5, "not captured by experiment (32 tREFIs)", ha='center', va='top', fontsize=6, color='gray', backgroundcolor='#F1F1F1', 
                    bbox=dict(facecolor='#F1F1F1', edgecolor='gray', boxstyle='round,pad=0.3', linewidth=0.5))
        elif trefis == "64":
            ax.axvspan(64, max_x, color='lightgray', alpha=0.3, zorder=3)
            ax.text((int(trefis) + max_x) / 2, 10.5, "not captured by experiment (64 tREFIs)", ha='center', va='top', fontsize=6, color='gray', backgroundcolor='#F1F1F1',
                    bbox=dict(facecolor='#F1F1F1', edgecolor='gray', boxstyle='round,pad=0.3', linewidth=0.5))
        elif trefis == "128":
            ax.axvspan(128, max_x, color='lightgray', alpha=0.3, zorder=3)
            ax.text((int(trefis) + max_x) / 2, 23.5, "not captured by experiment\n(128 tREFIs)", ha='center', va='top', fontsize=6, color='gray', backgroundcolor='#F1F1F1',
                    bbox=dict(facecolor='#F1F1F1', edgecolor='gray', boxstyle='round,pad=0.3', linewidth=0.5))
        
    fig2.text(0.5, 0.045, "Refresh Interval Index", ha='center')
    fig2.text(0.005, 0.54, "#TRRs Across Repetitions", va='center', rotation='vertical')
    plt.tight_layout(h_pad=0.2, rect=[0.015, 0.05, 1.0, 1.03])
    plt.savefig(args.output)
    print(f"Saved histogram as {args.output}")

if __name__ == "__main__":
    main()
    main()
