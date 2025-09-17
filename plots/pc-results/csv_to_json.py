#!/usr/bin/env python3
"""
Convert a DRAM-sweep CSV to the JSON layout expected by the exploit simulator.

Key additions
-------------
* flips.total  – number of flips
* pattern      – UUID4 string
* mapping      – UUID4 string
* --csv flag   – required for input CSV
"""

import argparse
import csv
import json
import os
import time
import uuid
from typing import Dict, List


def flatten_bank(bg: int, bank: int, banks_per_bg: int = 4) -> int:
    """Map (bank-group, bank) → flat bank id."""
    return bg * banks_per_bg + bank


def csv_to_json_dict(csv_rows: List[Dict[str, str]],
                     dimm_id: int,
                     start_ts: int,
                     sweep_minutes: int = 90) -> Dict:
    total_flips = len(csv_rows)
    if total_flips == 0:
        raise ValueError("CSV contains no flips")

    interval = (sweep_minutes * 60) / total_flips  # seconds between flips

    flip_details = []
    for idx, row in enumerate(csv_rows):
        observed = int(start_ts + idx * interval)

        expected = int(row["expected_hex"], 16)
        actual   = int(row["actual_hex"], 16)
        addr_int = int(row["virt_addr"],     16)

        flip_details.append({
            "addr": row["virt_addr"].lower(),
            "bitmask": expected ^ actual,
            "data": actual,
            "dram_addr": {
                "bank": flatten_bank(int(row["bg"]), int(row["bank"])),
                "col":  int(row["col"]),
                "row":  int(row["row"]),
            },
            "observed_at": observed,
            "page_offset": addr_int & 0xFFF,
        })

    return {
        "metadata": {
            "dimm_id": dimm_id,
            "end":   start_ts + sweep_minutes * 60,
            "memory_config": None,
            "num_patterns": 1,
            "start": start_ts,
        },
        "sweeps": [
            {
                "pattern": uuid.uuid4().hex,     # new field
                "mapping": uuid.uuid4().hex,     # new field
                "flips": {
                    "total": total_flips,
                    "details": flip_details
                }
            }
        ],
    }


def convert(csv_path: str, json_path: str | None = None) -> str:
    dimm_id = int(os.path.splitext(os.path.basename(csv_path))[0].split("_")[-1])

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    start_ts = int(time.time())
    json_obj = csv_to_json_dict(rows, dimm_id, start_ts)

    if json_path is None:
        json_path = os.path.splitext(csv_path)[0] + ".json"

    with open(json_path, "w", encoding="utf-8") as out_f:
        json.dump(json_obj, out_f, indent=2)

    return json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert sweep CSV to JSON")
    parser.add_argument("--csv", required=True, help="Input CSV file")
    parser.add_argument("-o", "--output", help="Output JSON file")
    args = parser.parse_args()

    out_path = convert(args.csv, args.output)
    print(f"✓ JSON written to {out_path}")


if __name__ == "__main__":
    main()
