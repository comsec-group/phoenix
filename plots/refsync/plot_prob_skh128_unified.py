from matplotlib.ticker import FuncFormatter, MultipleLocator

import matplotlib.pyplot as plt
import numpy as np
import matplotlib.ticker as mticker
import plot_settings
import argparse

def compute_survival_data(p_fail_list, activation_rate):
    max_hc = 160_000*4
    pattern_trefis_hammered = 32
    pattern_length_trefis = 128
    num_trefis = (max_hc // round(pattern_trefis_hammered * activation_rate)) * pattern_length_trefis
    print(f"Number of tREFIs: {num_trefis}")

    # Initialize dictionary to store survival data
    survival_data = {}

    # Loop over each failure probability
    for p_fail in p_fail_list:
        x_vals = []
        y_vals = []
        # for cur_trefi in range(0, num_trefi, pattern_length_trefis*5):
        for cur_trefi in range(0, num_trefis):
            survival_prob = (1 - p_fail) ** cur_trefi
            hammer_count = (cur_trefi//pattern_length_trefis) * pattern_trefis_hammered * activation_rate
            if p_fail > 0 and survival_prob > 0.0000001:
                print(f"pfail {p_fail:.5f} | cur_trefi {cur_trefi:6d} | hammer_count {hammer_count:6d} | survival_prob {survival_prob*100:.6f}%")
            if cur_trefi % (pattern_length_trefis*5) == 0:
                x_vals.append(survival_prob)
                y_vals.append(hammer_count/1000)
        survival_data[p_fail] = (x_vals, y_vals)
    return survival_data

def main():
    parser = argparse.ArgumentParser(description="Plot survival probability comparison for SKH128.")
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="../refsync_comparison.pdf",
        help="Output file path (default: ../refsync_comparison.pdf)"
    )
    args = parser.parse_args()

    fig_width_pt = 580
    fig_width_in = fig_width_pt / 72
    fig_height_in = fig_width_in * 0.15  # slightly taller for bars

    error_probs = [0.00125, 0.00234] # unused
    labels = [
        "40 ACTs/tREFI",
        "50 ACTs/tREFI"
    ]

    line_labels = [
        ["Zenhammer (0.125%)", "Multi-thrd. (0.129%)", "Self-correcting (0%)"],
        ["Zenhammer (0.234%)", "Multi-thrd. (0.195%)", "Self-correcting (0%)"]
    ]

    # x-values to plot lines for (hammer counts)
    x_vals = 30 * 32 * np.array([1, 2, 3, 4, 5, 6])

    fig, axs = plt.subplots(1, 2, figsize=(fig_width_in*0.45, fig_height_in), sharex=True, sharey=True)

    for i, (error, title) in enumerate(zip(error_probs, labels)):
        axs[i].axvline(x=51657*2/1000, color='black', linestyle=':', linewidth=0.8, zorder=1)
        probs = []
        if i == 0:
            probs = [0.00125, 0.00129, 0]
            survival_data = compute_survival_data(probs, 40)
        elif i == 1:
            probs = [0.00234, 0.00195, 0]
            survival_data = compute_survival_data(probs, 50)
        
        print(f"\nSubplot {i+1} ({title}):")
        for idx in range(len(survival_data[probs[0]][1])):
            hc = survival_data[probs[0]][1][idx]
            sp1 = survival_data[probs[0]][0][idx]
            sp2 = survival_data[probs[1]][0][idx]
            sp3 = survival_data[probs[2]][0][idx]
            print(f"{hc*1000:8,.0f}: {sp1*100:.3f}% {sp2*100:.3f}% {sp3*100:.3f}%")
        
        line_width = 0.8
        marker_size = 2
        markers = ['o', 'x', 'o']
        for j, prob in enumerate(probs):
            xvals = survival_data[prob][1]
            yvals = survival_data[prob][0]
            # Find the first index where survival probability drops below X
            below_thresh = np.where(np.array(yvals) < 0.000009)[0]
            if below_thresh.size > 0:
                idx = below_thresh[0]
            else:
                idx = len(yvals)
            # Plot up to idx with markers, after that without markers
            if j == 0:
                fillstyle = 'none'
            else:
                fillstyle = 'full'
            axs[i].plot(
                xvals[:idx], yvals[:idx],
                marker=markers[j], label=line_labels[i][j], linewidth=line_width,
                markersize=3.8 if j == 0 else (2.6 if j == 1 else marker_size), 
                fillstyle=fillstyle
            )
            if idx < len(yvals):
                axs[i].plot(
                    xvals[idx-1:], yvals[idx-1:],
                    marker='', linestyle='-', linewidth=line_width,
                    color=axs[i].lines[-1].get_color()
                )

        axs[i].text(1, 1.12, title, transform=axs[i].transAxes, ha='right', va='top', fontsize='small', fontweight='bold')
        axs[i].text(0.91, 0.9, "Avg. HCmin", transform=axs[i].transAxes, ha='right', va='top', rotation=90, fontsize='small')
        axs[i].legend(
            loc='upper center',
            bbox_to_anchor=(0.47, 1.55),
            frameon=False,
            labelspacing=0.1,
            handlelength=1.5,
            handletextpad=1.0,
            ncol=1,
            columnspacing=1.5,
            fontsize='small'
        )

    # Y-axis setup
    for ax in axs:
        ax.set_ylim(-0.05, 1.05)
        ax.set_xlim(0, 112)
        ax.yaxis.set_major_locator(MultipleLocator(0.25))
        ax.yaxis.set_minor_locator(MultipleLocator(0.125))
        major_tick_spacing = 32
        ax.xaxis.set_major_locator(MultipleLocator(major_tick_spacing))
        ax.xaxis.set_minor_locator(MultipleLocator(major_tick_spacing / 2))
        # ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x/1000)}"))
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        ax.tick_params(axis='y', which='minor', length=3, width=0.8, color='gray')

    axs[0].set_ylabel("Survival Prob.")
    fig.text(0.5, -0.13, "Hammer Count [x1000]", ha='center', va='center', fontsize='medium')

    plt.subplots_adjust(wspace=0.07)

    plt.savefig(args.output, dpi=72, bbox_inches='tight', pad_inches=0.01)

if __name__ == "__main__":
    main()
