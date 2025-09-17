# Plots

This directory contains both the scripts and data that we used to generate the plots and tables of our paper. The data needed to generate a plot can be found in the plot script's respective directory.

| **Reference** | **Description**                                 | **Script** |
|---------------|-------------------------------------------------|---------------|
| Fig. 6        | Zooming out                                     | [plot_trr_sampling_hist.py](./zooming-out/plot_trr_sampling_hist.py) |
| Fig. 7        | Zooming in: lightly sampled intervals           | [plot_trr_sampling_hist_zoomedin.py](./zooming-out/plot_trr_sampling_hist_zoomedin.py)               |
| Fig. 8        | Zooming in: ACT-based analysis                  | [plot_zoomin_exp.py](./act-based-analysis/plot_zoomin_exp.py)              |
| Fig. 11       | Activation rate vs. hammering duration          | [plot_trefi_time.py](./act-rate-heatmap/plot_trefi_time.py)              |
| Fig. 12       | Required #tREFIs in sync for pattern P128       | [plot_hc_analysis_skh_128.py](./num-trefis-in-sync/plot_hc_analysis_skh_128.py)              |
| Fig. 13       | Comparison of refresh synchronization methods   | [plot_prob_skh128_unified.py](./refsync/plot_prob_skh128_unified.py)              |

## Regenerating all plots

We provide a single script `plot-all.sh` that regenerates all the plots of our paper and saves them into the `output/` directory. 

### Requirements

- Python 3 (recommended: 3.8+)
- Bash shell
- The Python packages listed in `requirements.txt`
- The script will automatically create and use a virtual environment in the `plots/` directory
- All plot scripts expect their data files to be present in the respective subdirectories

### Running

Regenerate all plots by running:

```bash
chmod +x plot_all.sh
./plot_all.sh
```

# Tables

| **Reference** | **Description**                                 | **Data**                         |
| ------------- | ----------------------------------------------- | -------------------------------- |
| Table 4       | DDR5 RDIMMs: Pattern coverage and effectiveness | [fpga-results/](./fpga-results/) |
| Table 5       | Evaluation of DDR5 UDIMMs                       | [pc-results/](./pc-results/)     |


