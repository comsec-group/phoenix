import argparse
import logging
from datetime import datetime
from typing import List

import pandas as pd
from tqdm import tqdm

from rowhammer_tester.gateware.payload_executor import Encoder
from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_controller import DramController, write_payload_detail_to_file
from utrr.dram.dram_row_mapping import (
    get_dram_row_mapping,
    DramRowMapping,
)
from utrr.dsl.compile import compile_code
from utrr.setup_logging import setup_logging
from utrr.scripts.args_utils import convert_byte_to_32bit_pattern

logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Perform double-sided Rowhammer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--bank",
        type=int,
        required=True,
        help="Specify the bank ID to test (e.g., 0, 1, 2, ...).",
    )
    parser.add_argument(
        "--row",
        type=int,
        required=True,
        help="Specify the row ID to test (e.g., 0, 1, 2, ...).",
    )
    parser.add_argument(
        "--pattern",
        type=lambda x: int(x, 16),
        default=[0xFF],
        required=True,
        help=(
            "Specify one victim pattern in hex format (e.g., 0xFF, 0xAA). "
            "The aggressor pattern will always be the bitwise inversion of the victim pattern. "
        ),
    )
    parser.add_argument(
        "--hammer-count",
        type=int,
        required=True,
        help="Specify the hammer count.",
    )
    parser.add_argument(
        "--ref-cmd-count",
        type=int,
        required=True,
        help="Specify the refresh command count to be inserted.",
    )
    parser.add_argument(
        "--modulus",
        type=int,
        required=True,
        help="Specify the modulus to align the refresh counter before executing the payload.",
    )
    parser.add_argument(
        "--modulo",
        type=int,
        required=True,
        help="Specify the modulo to align the refresh counter before executing the payload.",
    )

    parser.add_argument(
        "--iterations",
        type=int,
        required=True,
        help="Specify the number of iterations",
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
        choices=["direct", "samsung"],
        required=True,
        help="Specify the internal DRAM row mapping strategy ('direct' or 'samsung').",
    )

    args = parser.parse_args()
    return args


def generate_double_sided_payload(
    physical_victim_address: DramAddress,
    hammer_count: int,
    dram_row_mapping: DramRowMapping,
    ref_cmd_count: int,
) -> List[Encoder.Instruction]:

    addresses_lookup = {"addresses": [physical_victim_address]}

    code = f"""
for _ in range({hammer_count // 2}):
    act(bank=addresses[0].bank, row=addresses[0].row - 1)
    pre()
    act(bank=addresses[0].bank, row=addresses[0].row + 1)
    pre()
    
for _ in range({ref_cmd_count}):
    ref()
    
for _ in range({hammer_count // 2}):
    act(bank=addresses[0].bank, row=addresses[0].row - 1)
    pre()
    act(bank=addresses[0].bank, row=addresses[0].row + 1)
    pre()
    """

    payload = compile_code(
        code=code,
        addresses_lookup=addresses_lookup,
        dram_row_mapping=dram_row_mapping,
    )

    return payload


def create_csv_filename() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"double_sided_results_{timestamp}.csv"


def main():
    args = parse_arguments()
    setup_logging()

    victim_pattern = convert_byte_to_32bit_pattern(args.pattern)
    attacker_pattern = ~victim_pattern & 0xFFFFFFFF

    dram_row_mapping = get_dram_row_mapping(args.dram_mapping)
    print(f"Using DRAM mapping: {args.dram_mapping}")
    controller = DramController(dram_row_mapping=dram_row_mapping)

    tqdm.write(f"RDIMM ID: {args.rdimm}")
    tqdm.write(f"Bank ID: {args.bank}")
    tqdm.write(f"Row ID: {args.row}")
    tqdm.write(f"Victim Pattern: {hex(victim_pattern)}")
    tqdm.write(f"Hammer Count: {args.hammer_count}")

    tqdm.write("Initializing double-sided hammer attack.")
    tqdm.write(f"Target bank: {args.bank}, victim row: {args.row}")
    tqdm.write(
        f"Victim pattern: {victim_pattern :#010x}, attacker pattern: {attacker_pattern:#010x}"
    )
    tqdm.write(f"Hammer count: {args.hammer_count}")
    tqdm.write(f"Ref command count: {args.ref_cmd_count}")

    victim_addresses = [DramAddress(bank=args.bank, row=args.row)]
    attacker_addresses = [
        DramAddress(bank=args.bank, row=args.row - 1),
        DramAddress(bank=args.bank, row=args.row + 1),
    ]
    payload = generate_double_sided_payload(
        physical_victim_address=victim_addresses[0],
        hammer_count=args.hammer_count,
        dram_row_mapping=dram_row_mapping,
        ref_cmd_count=args.ref_cmd_count,
    )
    write_payload_detail_to_file(payload=payload, file_path="payload.txt")

    flush_rows = [DramAddress(bank=0, row=780), DramAddress(bank=0, row=800)]

    controller.disable_refresh()
    controller.align_mod_refresh(modulus=args.modulus, mod_value=args.modulo)

    refresh_counters_before_trr = []

    for iteration in tqdm(range(args.iterations), desc="Executing iterations"):

        controller.dma_memset_dram_addresses(
            addresses=flush_rows + victim_addresses + flush_rows,
            pattern_32bit=victim_pattern,
        )
        controller.dma_memset_dram_addresses(
            addresses=attacker_addresses, pattern_32bit=attacker_pattern
        )

        refresh_count_before = controller.read_refresh_count()
        controller.execute_payload(payload=payload, verbose=False)

        flipped_addresses = controller.dma_memtest_addresses_flipped(
            addresses=flush_rows + victim_addresses + flush_rows,
            pattern_32bit=victim_pattern,
        )
        # Exclude flush rows from flipped addresses
        flipped_addresses = set(flipped_addresses) - set(flush_rows)

        if not flipped_addresses:
            refresh_counters_before_trr.append(refresh_count_before)
            tqdm.write(
                f"Iteration {iteration}: No flipped addresses detected. "
                f"Refresh count before payload: {refresh_count_before}"
            )

    # Generate a unique filename for the results
    output_file = create_csv_filename()
    df = pd.DataFrame(
        data=refresh_counters_before_trr,
        columns=["refresh_counter_before_trr"],
    )
    df.to_csv(output_file, index=False)

    controller.enable_refresh()


if __name__ == "__main__":
    main()
