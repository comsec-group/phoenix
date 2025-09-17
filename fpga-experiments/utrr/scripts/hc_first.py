"""
This script runs a binary search to estimate the minimum hammer count (hc_first)
at which bit flips appear in DRAM rows.

Example:
    python3 utrr/scripts/hc_first.py \
        --rdimm 310 \
        --dram-mapping direct \
        --bank 0 \
        --row-range 1000:1010 \
        --victim-patterns FF 00 \
        --max-hammer-count 500000 \
        --update-diff 1 \
        --repeat 1

Output:
    A CSV file named:
        hc_first_results_<timestamp>.csv
    containing per-row results with hammer count, bit flip count,
    and indices of flipped bytes and bits.
"""

import argparse
import csv
import itertools
import logging
from datetime import datetime

from tqdm import tqdm

from utrr.dram.dram_controller import DramController
from utrr.dram.dram_row_mapping import get_dram_row_mapping
from utrr.scripts.args_utils import (
    parse_row_range,
    parse_data_pattern,
    build_help_text,
    get_pattern_pairs,
)
from utrr.scripts.hammer_utils import find_hc_ecc_ds
from utrr.setup_logging import setup_logging


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Perform hc_first characterization for Rowhammer (binary search only).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--bank",
        type=int,
        default=0,
        help="Specify the bank ID to test (e.g., 0, 1, 2, ...).",
    )
    parser.add_argument(
        "--row-range",
        type=str,
        default="1000:1010",
        help="Specify the range of rows to test in the format start:end (e.g., 100:200).",
    )
    parser.add_argument(
        "--victim-patterns",
        type=parse_data_pattern,
        nargs="+",
        default=["FF"],  # 0xFFFFFFFF
        help=build_help_text(),
    )
    parser.add_argument(
        "--rdimm",
        type=int,
        required=True,
        help="Specify the RDIMM identifier to test (e.g., 310).",
    )
    parser.add_argument(
        "--dram-mapping",
        type=str,
        choices=["direct", "samsung", "micron"],
        required=True,
        help="Specify the internal DRAM row mapping strategy ('direct', 'samsung' or 'micron').",
    )
    parser.add_argument(
        "--max-hammer-count",
        type=int,
        default=500_000,
        help="Specify the initial maximum hammer count for the binary search (default: 500000).",
    )
    parser.add_argument(
        "--update-diff",
        type=int,
        default=1,
        help="Specify the threshold difference for the stopping condition during binary search.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="Specify how many times to execute the hc_first calculation for each row (default: 3).",
    )

    args = parser.parse_args()
    return args


def create_csv_filename() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"hc_first_results_{timestamp}.csv"


def main():
    args = parse_arguments()
    setup_logging()

    pattern_pairs = get_pattern_pairs(args.victim_patterns)
    for pair in pattern_pairs:
        logging.info(
            f"Victim pattern: 0x{pair.victim:08X}, "
            f"Aggressor pattern: 0x{pair.aggressor:08X}"
        )

    start_row, end_row = parse_row_range(args.row_range)

    row_mapping = get_dram_row_mapping(args.dram_mapping)
    print(f"Using DRAM mapping: {args.dram_mapping}")
    controller = DramController(dram_row_mapping=row_mapping)

    csv_filename = create_csv_filename()
    with open(csv_filename, mode="w", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(
            [
                "rdimm_id",
                "bank_id",
                "row_id",
                "victim_pattern",
                "aggressor_pattern",
                "hammer_count",
                "bit_flips_count",
                "bit_flip_byte_indices",
                "bit_flip_bit_indices",
            ]
        )

        tqdm.write(f"RDIMM ID: {args.rdimm}")
        tqdm.write(f"Bank ID: {args.bank}")
        tqdm.write(f"Row Range: {start_row}:{end_row}")
        tqdm.write(f"DRAM Mapping: {args.dram_mapping}")
        tqdm.write(f"Results will be saved to {csv_filename}")
        tqdm.write(f"Update Diff Threshold: {args.update_diff}")
        tqdm.write(f"Max Hammer Count: {args.max_hammer_count}")
        tqdm.write(f"Repeat Count: {args.repeat}")

        combinations = list(
            itertools.product(pattern_pairs, range(start_row, end_row + 1))
        )

        for pattern_pair, row in tqdm(combinations, desc="BS Mode", unit="test"):
            tqdm.write(
                f"Testing RDIMM={args.rdimm}, bank={args.bank}, row={row} "
                f"with victim=0x{pattern_pair.victim:08X}, "
                f"aggressor=0x{pattern_pair.aggressor:08X}"
            )

            hc_eccs = []
            for _ in range(args.repeat):
                hc_ecc = find_hc_ecc_ds(
                    controller=controller,
                    bank=args.bank,
                    row=row,
                    victim_pattern_32bit=pattern_pair.victim,
                    aggressor_pattern_32bit=pattern_pair.aggressor,
                    update_diff=args.update_diff,
                    hc_max=args.max_hammer_count,
                )
                hc_eccs.append(hc_ecc)

            min_hammer_result = min(hc_eccs, key=lambda r: r.hammer_count)
            bit_flips = min_hammer_result.bit_flips

            bit_flip_count = len(bit_flips)
            bit_flip_byte_indices = (
                ";".join(str(bf.byte_index()) for bf in bit_flips) if bit_flips else ""
            )
            bit_flip_bit_indices = (
                ";".join(str(bf.bit_index) for bf in bit_flips) if bit_flips else ""
            )

            csv_writer.writerow(
                [
                    args.rdimm,
                    args.bank,
                    row,
                    hex(pattern_pair.victim),
                    hex(pattern_pair.aggressor),
                    min_hammer_result.hammer_count,
                    bit_flip_count,
                    bit_flip_byte_indices,
                    bit_flip_bit_indices,
                ]
            )

            tqdm.write(
                f"  [BS] Row={row}, Victim={hex(pattern_pair.victim)}, "
                f"Aggressor={hex(pattern_pair.aggressor)}, "
                f"Hammer Count={min_hammer_result.hammer_count}, "
                f"Bitflips={bit_flip_count}"
            )


if __name__ == "__main__":
    main()
