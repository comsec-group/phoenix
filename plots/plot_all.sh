#!/bin/bash

# Check if there is an existing venv
if [ -d "venv" ]; then
   echo "[+] Virtual environment already exists."
   source venv/bin/activate
else
   echo "[>] Creating virtual environment..."
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
fi

# Set PYTHONPATH so plot_settings.py is importable from all scripts
export PYTHONPATH="$(pwd)"

scripts=(
    "zooming/plot_trr_sampling_hist.py"
    "zooming/plot_trr_sampling_hist_zoomedin.py"
    "act-based-analysis/plot_zoomin_exp.py"
    "act-rate-heatmap/plot_trefi_time.py"
    "act-rate-heatmap/plot_trefi_time.py"
    "num-trefis-in-sync/plot_hc_analysis_skh_128.py"
    "refsync/plot_prob_skh128_unified.py"
)

script_params=(
    "--output output/fig6.pdf"
    "--output output/fig7.pdf"
    "act-based-analysis/indices_probabilities.csv --output output/fig8.pdf"
    "--csv act-rate-heatmap/act_time_sweep_h2.csv --pdf --output output/fig10-h2.pdf "
    "--csv act-rate-heatmap/act_time_sweep_h6.csv --pdf --output output/fig10-h6.pdf "
    "--output output/fig12.pdf"
    "--output output/fig13.pdf"
)

# Create an output directory
mkdir -p output

# Loop through the scripts and execute them
echo "[>] Executing all plotting scripts..."
for i in "${!scripts[@]}"; do
    script="${scripts[$i]}"
    params="${script_params[$i]}"
    
    # Check if the script exists
    if [ -f "$script" ]; then
        echo "[+] Running $script with params: $params"
        python3 "$script" $params > /dev/null
    else
        echo "[-] Script $script not found."
    fi
done
