import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Rectangle
import argparse

import plot_settings

def main():
    parser = argparse.ArgumentParser(description="Plot HC analysis SKH 128.")
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="../hc_analysis_skh_128.pdf",
        help="Output file path (default: ../hc_analysis_skh_128.pdf)"
    )
    args = parser.parse_args()

    # # Constants and data
    acts_per_trefi = [50, 40]
    pattern_reps = list(range(1, 150))
    avg_hcmin = 51657 * 2
    highlight_min = 20.5 * 2 * 1000
    highlight_max = 91.8 * 2 * 1000
    pattern_length = 128 # trefis
    vline_x0 = 8192
    vline_x1 = 11054

    width_in_inches = (243.911*0.97) / 72
    height_in_inches = 6 * 0.20

    # Create figure
    fig, ax = plt.subplots(figsize=(width_in_inches, height_in_inches))
    lines = []
    labels = []

    # Plot lines
    for K in acts_per_trefi:
        x_values = [x * pattern_length for x in pattern_reps]
        y_values = [x * 32 * K for x in pattern_reps]
        # line, = ax.plot(pattern_reps, y_values, label=str(K), zorder=3)
        line, = ax.plot(x_values, y_values, label=str(K), zorder=3)
        lines.append(line)
        labels.append(str(K))

    # Background and reference lines
    ax.axhspan(highlight_min, highlight_max, facecolor='lightgray', alpha=0.5, zorder=1)
    ax.axhline(y=avg_hcmin, color='black', linestyle='--', linewidth=1, zorder=2)
    ax.axvline(x=vline_x0, color='black', linestyle='--', linewidth=1, zorder=2)
    ax.axvline(x=vline_x1, color='black', linestyle='--', linewidth=1, zorder=2)

    # Annotations
    ax.text(200, highlight_max - 9000, "Min/Max HCmin", ha='left', va='top', color='#555555')
    ax.text(200, avg_hcmin + 1000, "Avg. HCmin", va='bottom', color='black')
    ax.text(vline_x0 - 0.5, 5000, f"{vline_x0}", ha='right', va='bottom', color='black', rotation=90)
    ax.text(vline_x1 - 0.5, 5000, f"{vline_x1}", ha='right', va='bottom', color='black', rotation=90)

    # Axis labels and limits
    # ax.set_xlabel(r"$\#$tREFIs in Sync (Pattern Reps.)")
    ax.set_xlabel(r"$\#$tREFIs in Sync [x1000]", labelpad=1.5)
    ax.set_ylabel("Hammer Count\n[x1000]", labelpad=1.5)
    # ax.set_xlim(0, 91)
    ax.set_ylim(0, 200000)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    # Format y-axis with "k"
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x / 1000:.0f}' if x >= 1000 else str(int(x))))
    # Format x-axis with "k"
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x / 1000:.0f}' if x >= 1000 else str(int(x))))

    # Show ticks every 10 pattern repetitions up to 90
    # x_ticks = list(range(0, 91, 20))  # 10, 20, ..., 90
    # x_labels = [f"{x * 128}\n({x})" for x in x_ticks]
    # x_labels = [f"{x * 128}" for x in x_ticks]

    # ax.set_xticks(x_ticks)
    # ax.set_xticklabels(x_labels)
    ax.set_xlim(0, 13500)

    # Top x-axis (pattern repetitions)
    # secax = ax.secondary_xaxis('top', functions=(lambda x: x, lambda x: x))
    # secax.set_xticks(x_ticks)
    # secax.set_xticklabels([str(int(x)) for x in x_ticks])
    # secax.set_xlabel(r"$\#$Pattern Repetitions")

    # Minor ticks
    # ax.xaxis.set_minor_locator(mticker.MultipleLocator(base=(x_ticks[1] - x_ticks[0]) / 2))
    # y_major_ticks = ax.get_yticks()
    # if len(y_major_ticks) >= 2:
    #     y_step = y_major_ticks[1] - y_major_ticks[0]
    #     ax.yaxis.set_minor_locator(mticker.MultipleLocator(base=y_step / 2))
    # secax.xaxis.set_minor_locator(mticker.MultipleLocator(base=(x_ticks[1] - x_ticks[0]) / 2))

    # Tick appearance: outside
    # Tick appearance: outside
    ax.tick_params(axis='both', which='major', direction='out')
    ax.tick_params(axis='both', which='minor', length=3, width=0.8, color='gray', direction='out')
    # Add minor ticks between major ticks
    ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    # secax.tick_params(axis='x', which='major', length=8, direction='out')
    # secax.tick_params(axis='x', which='minor', length=4, direction='out')




    # Legend with inline title
    dummy_handle = Rectangle((0, 0), 1, 1, facecolor='none', edgecolor='none')
    custom_handles = [dummy_handle] + lines[::-1]
    custom_labels = ["ACTs/tREFI"] + labels[::-1]

    ax.legend(
        custom_handles, custom_labels,
        loc='upper center',
        bbox_to_anchor=(0.47, 1.22),
        ncol=len(acts_per_trefi) + 1,
        frameon=False,
        handlelength=1.2,
        handletextpad=0.5,
        columnspacing=0.7
    )

    # Save to PDF for LaTeX inclusion
    plt.savefig(args.output, bbox_inches='tight', pad_inches=0.01, dpi=72)

if __name__ == "__main__":
    main()
