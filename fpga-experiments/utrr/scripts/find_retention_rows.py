import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Literal, Optional

import yaml
from tqdm import tqdm

from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_controller import DramController
from utrr.dram.dram_row_mapping import get_dram_row_mapping
from utrr.dram.utils import (
    sort_addresses_ascending,
    deserialize_dram_addresses,
    serialize_dram_addresses,
    generate_dram_addresses,
)
from utrr.pipeline.pipeline import Pipeline
from utrr.pipeline.stage.bitflip_check_dram_address import BitflipCheckDramAddress
from utrr.pipeline.stage.disable_refresh_stage import DisableRefresh
from utrr.pipeline.stage.enable_refresh_stage import EnableRefresh
from utrr.pipeline.stage.precharge_all import PrechargeAll
from utrr.pipeline.stage.reset_pipe_ctx import ResetPipelineContext
from utrr.pipeline.stage.wait_until_elapsed_stage import WaitUntilElapsed
from utrr.pipeline.stage.write_dram_address_dma import WriteDramAddressDma


@dataclass
class RetentionConfig:
    name: str
    dram_mapping: Literal["direct", "samsung"]
    bank: int
    start: int
    end: int
    pattern_32bit: int
    wait_lower_ms: int
    wait_upper_ms: int
    iterations: int
    flush_rows: List[int] = field(default_factory=list)
    addresses_file: Optional[Path] = None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    cfg = load_config(parser.parse_args().config)
    row_mapping = get_dram_row_mapping(cfg.dram_mapping)
    controller = DramController(dram_row_mapping=row_mapping)

    test_addresses = load_test_addresses(cfg)

    addresses = perform_retention_tests(controller, test_addresses, cfg)
    mal_addresses = identify_malicious_addresses(controller, addresses, cfg)

    addresses = set(addresses) - mal_addresses
    addresses = sort_addresses_ascending(addresses)

    save_addresses(addresses, cfg)


def load_config(path: Path) -> RetentionConfig:
    data = yaml.safe_load(path.read_text())
    if data.get("addresses_file"):
        data["addresses_file"] = Path(data["addresses_file"])
    return RetentionConfig(**data)


def save_addresses(addresses: List[DramAddress], cfg: RetentionConfig):
    if addresses:
        json_file_path = (
            f"addresses_{cfg.start}_{cfg.end}_{cfg.wait_lower_ms}_{cfg.wait_upper_ms}.json"
        )
        serialize_dram_addresses(addresses, json_file_path)
        tqdm.write(f"[+] Serialized {len(addresses)} addresses → {json_file_path}")
    else:
        tqdm.write("[!] No addresses found")


def identify_malicious_addresses(
    controller: DramController, addresses: Iterable[DramAddress], cfg: RetentionConfig
):
    controller.disable_refresh()

    mal_addresses = set()

    for address in addresses:
        refresh_counter_before = controller.read_refresh_count()

        controller.dma_memset_dram_addresses(
            addresses=[address], pattern_32bit=cfg.pattern_32bit
        )

        refresh_counter_after = controller.read_refresh_count()
        diff = refresh_counter_after - refresh_counter_before
        if diff > 0:
            mal_addresses.add(address)

    controller.enable_refresh()

    if mal_addresses:
        tqdm.write(f"[!] Identified {len(mal_addresses)} malicious addresses that affect refresh counter")
    return mal_addresses


def perform_retention_tests(
    controller: DramController, test_addresses: List[DramAddress], cfg: RetentionConfig
):
    tqdm.write(f"[i] Starting retention test with {len(test_addresses)} candidate addresses")

    flush_rows = [DramAddress(bank=cfg.bank, row=row) for row in cfg.flush_rows]

    controller.disable_refresh()

    flips_upper = run_fixed_iterations_update_intersection(
        controller=controller,
        addresses=test_addresses,
        flush_rows=flush_rows,
        pattern_32bit=cfg.pattern_32bit,
        wait_ms=cfg.wait_upper_ms,
        num_iterations=cfg.iterations,
    )
    tqdm.write(f"[i] Upper bound flips identified: {len(flips_upper)}")

    flips_lower = run_fixed_iterations_update_union(
        controller=controller,
        addresses=flips_upper,
        flush_rows=flush_rows,
        pattern_32bit=cfg.pattern_32bit,
        wait_ms=cfg.wait_lower_ms,
        num_iterations=cfg.iterations,
    )
    controller.enable_refresh()

    tqdm.write(f"[i] Lower bound flips identified: {len(flips_lower)}")

    addresses = set(flips_upper) - set(flips_lower)
    tqdm.write(f"[i] Candidate retention rows after filtering: {len(addresses)}")

    return addresses


def load_test_addresses(cfg: RetentionConfig) -> List[DramAddress]:
    if cfg.addresses_file:
        test_addresses = deserialize_dram_addresses(json_file_path=cfg.addresses_file)
        tqdm.write(f"[i] Loaded {len(test_addresses)} test addresses from {cfg.addresses_file}")
    else:
        test_addresses = generate_dram_addresses(
            bank=cfg.bank, start=cfg.start, end=cfg.end
        )
        tqdm.write(f"[i] Generated {len(test_addresses)} test addresses for bank {cfg.bank}, "
                   f"rows {cfg.start}..{cfg.end}")
    return test_addresses


def create_retention_pipe_check_bitflips(
    addresses: Iterable[DramAddress],
    flush_rows: List[DramAddress],
    pattern_32bit: int,
    wait_ms: int,
):
    stages = [
        PrechargeAll(),
        EnableRefresh(),
        WriteDramAddressDma(
            rows=flush_rows + list(addresses) + flush_rows,
            pattern_32bit=pattern_32bit,
        ),
        ResetPipelineContext(),
        DisableRefresh(),
        WaitUntilElapsed(wait_time=wait_ms, units="milliseconds"),
        EnableRefresh(),
        PrechargeAll(),
        BitflipCheckDramAddress(
            addresses=flush_rows + list(addresses) + flush_rows,
            pattern_32bit=pattern_32bit,
            ignore_addresses=flush_rows,
        ),
    ]
    pipe = Pipeline(stages=stages)
    return pipe


def run_fixed_iterations_update_intersection(
    controller: DramController,
    addresses: Iterable,
    flush_rows: Iterable,
    wait_ms: int,
    pattern_32bit: int,
    num_iterations: int,
):
    flush_rows = list(flush_rows)
    all_addresses = set(addresses)

    controller.disable_refresh()

    desc = f"[Upper bound] Wait {wait_ms} ms → keep only rows that *always* flip"
    with tqdm(desc=desc, unit="iter") as pbar:
        for iteration in range(1, num_iterations + 1):
            pipe = create_retention_pipe_check_bitflips(
                addresses=all_addresses,
                flush_rows=flush_rows,
                wait_ms=wait_ms,
                pattern_32bit=pattern_32bit,
            )
            pipe_ctxt = pipe.run_with_new_ctxt(controller=controller)
            all_addresses = all_addresses.intersection(pipe_ctxt.addresses_bitflipped)

            pbar.update(1)
            pbar.set_postfix(
                iteration=iteration,
                surviving=len(all_addresses),
            )

    controller.enable_refresh()
    return sort_addresses_ascending(all_addresses)


def run_fixed_iterations_update_union(
    controller: DramController,
    addresses: Iterable,
    flush_rows: Iterable,
    wait_ms: int,
    pattern_32bit: int,
    num_iterations: int,
):
    flush_rows = list(flush_rows)
    flipped_addresses = set()

    controller.disable_refresh()

    desc = f"[Lower bound] Wait {wait_ms} ms → collect rows that ever flip"
    with tqdm(desc=desc, unit="iter") as pbar:
        for iteration in range(1, num_iterations + 1):
            pipe = create_retention_pipe_check_bitflips(
                addresses=set(addresses) - flipped_addresses,
                flush_rows=flush_rows,
                wait_ms=wait_ms,
                pattern_32bit=pattern_32bit,
            )
            pipe_ctxt = pipe.run_with_new_ctxt(controller=controller)
            flipped_addresses.update(pipe_ctxt.addresses_bitflipped)

            pbar.update(1)
            pbar.set_postfix(
                iteration=iteration,
                total_flipped=len(flipped_addresses),
            )

    controller.enable_refresh()
    return sort_addresses_ascending(flipped_addresses)


if __name__ == "__main__":
    main()
