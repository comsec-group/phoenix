#!/usr/bin/env python3

import os
import csv
import re

# Path to the LaTeX file converting \dimm{id} to H_x
dimm_mapper = "./dimm_mapper.tex"

# Directory containing the CSV files
data_dir = "data_sweep"

# Directory containing JSON files for exploit simulation
exploit_data_dir = "data_exploitation"

# Pattern to extract DIMM ID from filename
dimm_pattern = re.compile(r"system_sweep_(\d{3})\.csv$")

# Dictionary to store results per DIMM
results = {}


def find_dimm_id_order(tex_file: str) -> list:
    with open(tex_file, 'r') as f:
        content = f.read()

    # Find all entries like: {522}{\dimmSkhynix{0}}
    pattern = re.compile(r"{(\d+)}\s*{\s*\\dimmSkhynix{(\d+)}\s*}")
    matches = pattern.findall(content)

    # Sort by the index inside \dimmSkhynix{i}
    sorted_matches = sorted(matches, key=lambda x: int(x[1]))

    # Extract only the DIMM IDs
    ordered_ids = [int(dimm_id) for dimm_id, _ in sorted_matches]
    return ordered_ids


def format_number(num: str) -> str:
    return f"\\num{{{num}}}"


def count_bitflips(expected_hex, actual_hex):
    """Count 1→0 and 0→1 bit flips between two hex values."""
    expected = int(expected_hex, 16)
    actual = int(actual_hex, 16)
    xor = expected ^ actual
    one_to_zero = expected & xor
    zero_to_one = actual & xor
    return (
        bin(one_to_zero).count("1"),
        bin(zero_to_one).count("1")
    )

   
def get_sweep_results():
    # Iterate over all CSV files in the data directory
    for filename in os.listdir(data_dir):
        match = dimm_pattern.match(filename)
        if not match:
            continue

        dimm_id = int(match.group(1))
        file_path = os.path.join(data_dir, filename)

        one_to_zero_bf = 0
        zero_to_one_bf = 0

        with open(file_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                e_hex = row["expected_hex"]
                a_hex = row["actual_hex"]

                if e_hex == a_hex:
                    continue  # no flip

                one_to_zero, zero_to_one = count_bitflips(e_hex, a_hex)
                one_to_zero_bf += one_to_zero
                zero_to_one_bf += zero_to_one

        results[dimm_id] = (one_to_zero_bf, zero_to_one_bf)

    return results


def convert_csvs_to_json():
    for filename in os.listdir(data_dir):
        match = dimm_pattern.match(filename)
        if not match:
            continue

        file_path = os.path.join(data_dir, filename)
        output_dir = "data_exploitation"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{filename.replace('.csv', '.json')}")

        cmd = f"python3 csv_to_json.py --csv {file_path} -o {output_path}"
        os.system(cmd)


def determine_exploitability():
    cmd = f"python3 exploit-simulator/exploit_sim.py {exploit_data_dir} zen4"
    os.system(cmd)

    summary_file = "export_zen4.csv"
    if not os.path.exists(summary_file):
        print(f"[!] Expected file {summary_file} not found.")
        return {}

    exploit_results = {}
    with open(summary_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            dimm_id = int(row["dimm_id"])
            expl_name = row["expl_name"]
            mean_ttf = row["mean_ttf"]
            if dimm_id not in exploit_results:
                exploit_results[dimm_id] = {}
            exploit_results[dimm_id][expl_name] = mean_ttf

    return exploit_results


def format_time(time: str) -> str:
    try:
        # convert time from seconds into minutes and seconds
        t_fp = float(time)
        minutes = int(t_fp // 60)
        seconds = t_fp % 60
        if minutes > 0:
            return f"\\SI{{{minutes}}}{{\\minute}}\\;\\SI{{{round(seconds,None)}}}{{\\second}}"
        else:
            return f"\\SI{{{round(seconds,None)}}}{{\\second}}"
        # return f"{minutes:02}:{seconds:05.2f}"
    except:
        return "--" 


if __name__ == "__main__":
    print("[+] Processing sweep results...")
    results = get_sweep_results()
    dimm_order = find_dimm_id_order(dimm_mapper)
    
    print("[+] Converting CSV files to JSON...")
    convert_csvs_to_json()

    print("[+] Determining exploitability...")
    exploitation = determine_exploitability()

    print("[+] Generating content for LaTeX table...")
    # Print results in the order defined in dimm_mapper.tex
    with open("data.tex", "w") as texfile:
        for dimm_id in dimm_order:
            if dimm_id not in results:
                continue
            one_to_zero_bf, zero_to_one_bf = results[dimm_id]
            dimm_id_str = f"\\dimm{{{dimm_id:03}}}"
            mean_ttf_pte = exploitation[dimm_id]['FlipPFN(16GB)']
            mean_ttf_rsa = exploitation[dimm_id]['GPGFlip']
            mean_ttf_sudo = exploitation[dimm_id]['OpcodeFlip']
            row = (f"{dimm_id_str:14s}  "
                   f"& {format_number(one_to_zero_bf):14s} "
                   f"& {format_number(zero_to_one_bf):14s} "
                   f"& {(mean_ttf_pte):} "
                   f"& {(mean_ttf_rsa):} "
                   f"& {(mean_ttf_sudo):} "
                   f"\\\\")
            print(row)
            row = (f"{dimm_id_str:14s}  "
                   f"& {format_number(one_to_zero_bf):14s} "
                   f"& {format_number(zero_to_one_bf):14s} "
                   f"& {format_time(mean_ttf_pte):50s} "
                   f"& {format_time(mean_ttf_rsa):50s} "
                   f"& {format_time(mean_ttf_sudo):50s} "
                   f"\\\\")
            # texfile.write(row + "\n")
