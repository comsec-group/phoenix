#!/usr/bin/env python3
import argparse
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Dict

from tqdm import tqdm

from rowhammer_tester.gateware.payload_executor import Encoder
from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_controller import DramController, write_payload_detail_to_file
from utrr.dram.dram_row_mapping import get_dram_row_mapping
from utrr.dram.utils import (
    deserialize_dram_addresses,
    serialize_dram_addresses,
    filter_min_distance_addresses,
    group_indices_by_address,
    select_random_excluding_addresses,
)
from utrr.dsl.compile import compile_code
from utrr.pipeline.experiment_result_dir import ExperimentResultDir
from utrr.pipeline.pipeline import Pipeline
from utrr.pipeline.stage.align_mod_refresh import AlignModRefresh
from utrr.pipeline.stage.annotate_index_not_bitflipped import AnnotateIndexNotBitflipped
from utrr.pipeline.stage.bitflip_check_dram_address import BitflipCheckDramAddress
from utrr.pipeline.stage.disable_refresh_stage import DisableRefresh
from utrr.pipeline.stage.emit_refresh_counter import EmitRefreshCounter
from utrr.pipeline.stage.enable_refresh_stage import EnableRefresh
from utrr.pipeline.stage.execute_payload import ExecutePayload
from utrr.pipeline.stage.export_pipe_context import ExportPipeContext
from utrr.pipeline.stage.issue_random_refresh import IssueRandomRefresh
from utrr.pipeline.stage.no_bitflip_check_dram_address import NoBitflipCheckDramAddress
from utrr.pipeline.stage.precharge_all import PrechargeAll
from utrr.pipeline.stage.reset_pipe_ctx import ResetPipelineContext
from utrr.pipeline.stage.wait_until_elapsed_stage import WaitUntilElapsed
from utrr.pipeline.stage.write_dram_address_dma import WriteDramAddressDma
from utrr.scripts.args_utils import convert_byte_to_32bit_pattern, load_pyram_program
from utrr.setup_logging import setup_logging

logger = logging.getLogger(__name__)

###############################################################################
# Argument Parsing
###############################################################################


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a U-TRR experiment")

    parser.add_argument(
        "--addresses-file",
        type=Path,
        required=True,
        help="Path to the JSON file containing DRAM addresses.",
    )
    parser.add_argument(
        "--num-rows",
        type=int,
        required=True,
        help="Number of rows to take from the addresses file.",
    )
    parser.add_argument(
        "--min-row-distance",
        type=int,
        required=True,
        help="Minimum distance (in rows) between selected DRAM addresses.",
    )
    parser.add_argument(
        "--retention-pattern",
        type=lambda x: int(x, 16),
        default=0xFF,
        help="Retention pattern in hexadecimal format (e.g., 0xFF, 0xAA).",
    )
    parser.add_argument(
        "--pre-wait-ms",
        type=int,
        required=True,
        help="Time in milliseconds to wait before executing the payload.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        required=True,
        help="Time in milliseconds to wait after executing the payload.",
    )
    parser.add_argument(
        "--modulus",
        type=int,
        help="Modulus value for aligning the refresh counter before payload execution.",
    )

    # Mutually exclusive group for specifying modulo values directly or via a file
    modulo_group = parser.add_mutually_exclusive_group()
    modulo_group.add_argument(
        "--modulo",
        type=int,
        nargs="+",
        help="One or more integer values for aligning the refresh counter.",
    )
    modulo_group.add_argument(
        "--modulo-file",
        type=Path,
        help="Path to a file containing modulo values (one per line or space-separated).",
    )

    parser.add_argument(
        "--dram-mapping",
        type=str,
        choices=["direct", "samsung"],
        required=True,
        help="Specify the internal DRAM row mapping strategy.",
    )
    parser.add_argument(
        "--execute-payload",
        action="store_true",
        default=False,
        help="Execute the payload during the experiment.",
    )
    parser.add_argument(
        "--program",
        type=Path,
        required=True,
        nargs="+",
        help="One or more DSL programs as file paths or inline strings.",
    )
    parser.add_argument(
        "--num-runs",
        type=int,
        required=True,
        help="Number of experiment runs.",
    )
    parser.add_argument(
        "--disable-refresh-for-all-runs",
        action="store_true",
        help="Disable refresh for the entire duration of all runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the experiment results will be saved.",
    )
    parser.add_argument(
        "--payload-only",
        action="store_true",
        help="Generate the payload without executing the pipeline.",
    )
    parser.add_argument(
        "--check-bitflips",
        action="store_true",
        help="Use BitflipCheckDramAddress instead of NoBitflipCheckDramAddress.",
    )
    parser.add_argument(
        "--random-sample",
        action="store_true",
        help="Select victim addresses randomly instead of taking the first N addresses.",
    )
    parser.add_argument(
        "--log-file-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="DEBUG",
        help="Set the logging level for the log file (default: DEBUG).",
    )
    parser.add_argument(
        "--log-console-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="DEBUG",
        help="Set the logging level for the console output (default: DEBUG).",
    )
    parser.add_argument(
        "--decoy-count",
        type=int,
        default=100,
        help="Number of decoy rows to generate (default: 100).",
    )
    parser.add_argument(
        "--template-var",
        type=str,
        nargs="+",
        metavar="KEY=VALUE",
        help=(
            "Optional template variables to substitute inside the DSL program. "
            "Each must be given as KEY=VALUE with VALUE an integer "
            "(for example: --template-var hammer_count=29 reps=4)."
        ),
    )

    return parser.parse_args()


###############################################################################
# Argument Storage
###############################################################################


def save_arguments_to_file(args: argparse.Namespace, file_path: Path) -> None:
    def convert_value(value):
        if isinstance(value, Path):
            return str(value)
        elif isinstance(value, list):
            return [str(item) if isinstance(item, Path) else item for item in value]
        return value

    args_dict = {key: convert_value(value) for key, value in vars(args).items()}
    with open(file_path, "w") as file:
        json.dump(args_dict, file, indent=4)


###############################################################################
# Template Vars
###############################################################################


def parse_template_vars(vars_list: Optional[List[str]]) -> Dict[str, int]:
    if not vars_list:
        return {}
    result = {}
    for item in vars_list:
        if "=" not in item:
            raise ValueError(f"Invalid template variable format: {item}")
        key, val = item.split("=", 1)
        try:
            result[key] = int(val)
        except ValueError:
            raise ValueError(f"Template variable {key} must be an integer, got {val}")
    return result


###############################################################################
# Address Handling
###############################################################################


def load_and_filter_addresses(
    addresses_file: Path,
    num_rows: int,
    min_row_distance: int,
    random_sample: bool,
) -> Tuple[List, List]:
    """
    Load addresses from file and filter them according to the command-line arguments.
    Returns a tuple of (bitflip_check_addresses, program_addresses).
    """

    addresses = deserialize_dram_addresses(json_file_path=addresses_file)

    if random_sample:
        raise NotImplementedError("Random sampling not yet implemented.")

    addresses = filter_min_distance_addresses(
        addresses=addresses, min_row_distance=min_row_distance
    )
    bitflip_check_addresses = addresses[:num_rows]
    program_addresses = bitflip_check_addresses

    return bitflip_check_addresses, program_addresses


###############################################################################
# Payload Handling
###############################################################################


def compile_all_payloads(
    programs: List[Path],
    addresses_lookup: Dict[str, List[DramAddress]],
    row_mapping,
    result_dir,
    template_vars: Dict[str, int],
) -> List[List[Encoder.Instruction]]:
    payloads = []

    for i, program in enumerate(programs):
        pyram_program = load_pyram_program(program)
        if template_vars:
            pyram_program = pyram_program.format(**template_vars)

        payload = compile_code(pyram_program, addresses_lookup, row_mapping)
        logger.debug(f"Generated payload with {len(payload)} instructions.")

        program_out_path = result_dir.get_pyram_path(program_id=i)
        program_out_path.write_text(pyram_program)

        payload_path = result_dir.get_payload_path(payload_id=i)
        write_payload_detail_to_file(payload=payload, file_path=str(payload_path))
        logger.info(f"Payload written to file: {payload_path}")

        payloads.append(payload)

    return payloads


def build_bitflip_stages(
    bitflip_check_addresses, pattern_32bit, check_bitflips, flush_rows
):
    victim_indices = group_indices_by_address(bitflip_check_addresses)

    if check_bitflips:
        return [
            BitflipCheckDramAddress(
                addresses=flush_rows + bitflip_check_addresses + flush_rows,
                pattern_32bit=pattern_32bit,
                ignore_addresses=flush_rows,
            )
        ]
    else:
        return [
            NoBitflipCheckDramAddress(
                addresses=flush_rows + bitflip_check_addresses + flush_rows,
                pattern_32bit=pattern_32bit,
                ignore_addresses=flush_rows,
            ),
            AnnotateIndexNotBitflipped(addresses=victim_indices),
        ]


def create_stages_disable_refresh_all_runs(
    payloads,
    execute_payload: bool,
    bitflip_check_addresses,
    pattern_32bit: int,
    pre_wait_ms: int,
    wait_ms: int,
    modulus: Optional[int],
    mod_value: Optional[int],
    check_bitflips: bool,
    export_path: Path,
):
    flush_rows = [DramAddress(bank=0, row=780), DramAddress(bank=0, row=800)]

    prologue = [PrechargeAll(), DisableRefresh()]
    if modulus is not None and mod_value is not None:
        prologue.append(AlignModRefresh(modulus=modulus, mod_value=mod_value))

    main_stages = [
        ResetPipelineContext(),
        WriteDramAddressDma(
            rows=flush_rows + bitflip_check_addresses + flush_rows,
            pattern_32bit=pattern_32bit,
        ),
        EmitRefreshCounter("refresh_counter_before", modulus=modulus),
        WaitUntilElapsed(wait_time=pre_wait_ms, units="milliseconds"),
    ]

    if execute_payload:
        for payload in payloads:
            main_stages.append(ExecutePayload(payload=payload, verbose=False))

    main_stages.extend(
        [
            WaitUntilElapsed(wait_time=wait_ms, units="milliseconds"),
            EmitRefreshCounter("refresh_counter_after", modulus=modulus),
            PrechargeAll(),
        ]
    )

    bitflip_stages = build_bitflip_stages(
        bitflip_check_addresses, pattern_32bit, check_bitflips, flush_rows
    )
    main_stages.extend(bitflip_stages)
    main_stages.append(ExportPipeContext(filepath=export_path))

    return prologue + main_stages


def create_stages_enable_refresh_between_runs(
    payloads,
    execute_payload: bool,
    bitflip_check_addresses,
    pattern_32bit: int,
    pre_wait_ms: int,
    wait_ms: int,
    modulus: Optional[int],
    mod_value: Optional[int],
    check_bitflips: bool,
    export_path: Path,
):
    flush_rows = [DramAddress(bank=0, row=780), DramAddress(bank=0, row=800)]

    main_stages = (
        [
            PrechargeAll(),
            DisableRefresh(),
            EnableRefresh(),
            WriteDramAddressDma(
                rows=flush_rows + bitflip_check_addresses + flush_rows,
                pattern_32bit=pattern_32bit,
            ),
        ]
        + [IssueRandomRefresh(random_refresh_range=range(1000, 4000)) for _ in range(5)]
        + [
            ResetPipelineContext(),
            DisableRefresh(),
        ]
    )

    if modulus is not None and mod_value is not None:
        main_stages.append(AlignModRefresh(modulus=modulus, mod_value=mod_value))

    main_stages.append(EmitRefreshCounter("refresh_counter_before", modulus=modulus))
    main_stages.append(WaitUntilElapsed(wait_time=pre_wait_ms, units="milliseconds"))

    if execute_payload:
        for payload in payloads:
            main_stages.append(ExecutePayload(payload=payload, verbose=False))

    main_stages.extend(
        [
            WaitUntilElapsed(wait_time=wait_ms, units="milliseconds"),
            EmitRefreshCounter("refresh_counter_after", modulus=modulus),
            PrechargeAll(),
            EnableRefresh(),
        ]
    )

    bitflip_stages = build_bitflip_stages(
        bitflip_check_addresses, pattern_32bit, check_bitflips, flush_rows
    )
    main_stages.extend(bitflip_stages)
    main_stages.append(ExportPipeContext(filepath=export_path))

    return main_stages


def main():
    args = parse_args()

    base_result_dir = ExperimentResultDir.from_base(args.output_dir)
    setup_logging(
        log_file_path=base_result_dir.get_log_file_path(),
        file_level=args.log_file_level,
        console_level=args.log_console_level,
    )
    logger.info("Starting experiment.")

    save_arguments_to_file(args=args, file_path=base_result_dir.path / "args.json")

    row_mapping = get_dram_row_mapping(args.dram_mapping)
    logger.info(f"Using DRAM mapping: {args.dram_mapping}")
    pattern_32bit = convert_byte_to_32bit_pattern(args.retention_pattern)
    logger.info(f"Converted retention pattern to 32-bit: 0x{pattern_32bit:08X}")

    bitflip_check_addresses, program_addresses = load_and_filter_addresses(
        addresses_file=args.addresses_file,
        num_rows=args.num_rows,
        min_row_distance=args.min_row_distance,
        random_sample=args.random_sample,
    )
    logger.info(
        f"Collected {len(bitflip_check_addresses)} addresses for bitflip checking and "
        f"{len(program_addresses)} addresses for programming."
    )

    decoys = select_random_excluding_addresses(
        addresses_exclude=program_addresses,
        count=args.decoy_count,
        min_distance=100,
    )
    addresses_lookup = {"addresses": program_addresses, "decoys": decoys}

    template_vars = parse_template_vars(args.template_var)

    payloads = compile_all_payloads(
        programs=args.program,
        addresses_lookup=addresses_lookup,
        row_mapping=row_mapping,
        result_dir=base_result_dir,
        template_vars=template_vars,
    )

    serialize_dram_addresses(
        dram_addresses=bitflip_check_addresses,
        json_file_path=str(base_result_dir.path / "bitflip_check_addresses.json"),
    )
    serialize_dram_addresses(
        dram_addresses=program_addresses,
        json_file_path=str(base_result_dir.path / "program_addresses.json"),
    )

    modulo_values = args.modulo if args.modulo else [None]
    total_experiments = len(modulo_values) * args.num_runs

    controller = DramController(dram_row_mapping=row_mapping)
    pbar = tqdm(total=total_experiments, desc="Overall experiment progress")

    for current_modulo in modulo_values:
        mod_label = (
            f"modulo_{current_modulo}" if current_modulo is not None else "no_modulo"
        )
        pbar.set_description(f"Testing {mod_label}")

        run_result_dir = base_result_dir.get_subdirectory(mod_label)

        if args.disable_refresh_for_all_runs:
            stages = create_stages_disable_refresh_all_runs(
                payloads=payloads,
                execute_payload=args.execute_payload,
                bitflip_check_addresses=bitflip_check_addresses,
                pattern_32bit=pattern_32bit,
                pre_wait_ms=args.pre_wait_ms,
                wait_ms=args.wait_ms,
                modulus=args.modulus,
                mod_value=current_modulo,
                check_bitflips=args.check_bitflips,
                export_path=run_result_dir.get_result_export_path(),
            )
        else:
            stages = create_stages_enable_refresh_between_runs(
                payloads=payloads,
                execute_payload=args.execute_payload,
                bitflip_check_addresses=bitflip_check_addresses,
                pattern_32bit=pattern_32bit,
                pre_wait_ms=args.pre_wait_ms,
                wait_ms=args.wait_ms,
                modulus=args.modulus,
                mod_value=current_modulo,
                check_bitflips=args.check_bitflips,
                export_path=run_result_dir.get_result_export_path(),
            )

        for run in range(args.num_runs):
            pbar.set_postfix({"modulo run": f"{run + 1}/{args.num_runs}"})
            pipe = Pipeline(stages=stages)
            pipe.run_with_new_ctxt(controller=controller, use_progress_bar=False)
            pbar.update(1)

    pbar.close()
    logger.info("All experiments completed.")


if __name__ == "__main__":
    main()
