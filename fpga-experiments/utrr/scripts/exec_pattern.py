#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import sys
import time
from itertools import islice, product
from pathlib import Path
from typing import Dict, Iterator, List

from tqdm import tqdm

from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_controller import DramController, write_payload_detail_to_file
from utrr.dram.dram_row_mapping import get_dram_row_mapping
from utrr.dram.utils import select_random_excluding_addresses
from utrr.dsl.compile import compile_code
from utrr.scripts.args_utils import convert_byte_to_32bit_pattern, load_pyram_program

# ───────────────────────── regex helpers ──────────────────────────
_SLICE_RE = re.compile(r"^(\d+):(\d+)(?::(\d+))?$")


def expand_row_slice(text: str) -> List[int]:
    """
    Parse 'START:END[:STEP]' (inclusive) into a list of ints
    or return a single integer if just a number is supplied.
    """
    m = _SLICE_RE.match(text)
    if m:
        start, end, step = map(int, (m.group(1), m.group(2), m.group(3) or "1"))
        if start > end or step <= 0:
            raise argparse.ArgumentTypeError("Invalid slice values.")
        return list(range(start, end + 1, step))
    # fall back: single int
    try:
        return [int(text)]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected int or START:END[:STEP]") from exc


def chunked(seq: List[int], size: int) -> Iterator[List[int]]:
    it = iter(seq)
    while (block := list(islice(it, size))):
        yield block


# ───────────────────────── CLI ───────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="RowHammer sweep over multiple DRAM banks",
    )

    # NEW: accept multiple banks / slice
    p.add_argument(
        "--banks",
        type=expand_row_slice,
        metavar="BANKS",
        required=True,
        help="Banks to test (e.g. 0 1 2 or 0:7:2).",
    )

    p.add_argument("--victim-rows", type=expand_row_slice, required=True)
    p.add_argument("--aggressor-offsets", type=int, nargs="+", default=(-1, 1))
    p.add_argument("--victims-per-run", type=int, default=1)

    p.add_argument("--patterns", type=lambda x: int(x, 16), nargs="+", required=True)
    p.add_argument("--modulus", type=int, required=True)
    p.add_argument("--modulo", type=int, nargs="+", required=True)
    p.add_argument("--iterations", type=int, required=True)

    p.add_argument("--dram-mapping", choices=["direct", "samsung", "micron"], required=True)
    p.add_argument("--pattern-code-path", type=Path, required=True)

    p.add_argument("--pattern-repetitions", type=int, nargs="+", default=[1])

    # ──────── changed: allow *several* execution counts ────────
    p.add_argument(
        "--payload-executions",
        type=int,
        nargs="+",
        default=[1],
        metavar="N",
        help="Number of times each compiled payload is executed per run "
             "(you can pass several values, e.g. 1 4 8).",
    )
    # ───────────────────────────────────────────────────────────

    p.add_argument("--acts-per-trefi", type=int, nargs="+", required=True)
    p.add_argument("--refs-per-pattern", type=int, required=True,
                   help="REF commands issued per pattern execution")

    p.add_argument("--decoy-rows", type=int, default=0)
    p.add_argument("--output-dir", default="test_output")
    p.add_argument("--save-compiled-code", action="store_true")

    return p.parse_args()


# ───────────────────────── main ──────────────────────────────────

def main() -> None:  # noqa: C901  (complexity)
    args = parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    if len(args.victim_rows) % args.victims_per_run:
        sys.exit("--victims-per-run does not divide victim count")

    template_text = args.pattern_code_path.read_text("utf-8")
    dram_row_mapping = get_dram_row_mapping(mapping_type=args.dram_mapping)
    controller = DramController(dram_row_mapping=dram_row_mapping)

    victim_blocks = list(chunked(args.victim_rows, args.victims_per_run))

    # progress-bar denominator — one “iteration” is a single parameter point
    total_iters = (
            len(args.banks)
            * len(args.acts_per_trefi)
            * len(args.pattern_repetitions)
            * len(args.payload_executions)  # ← accounts for the new sweep dimension
            * len(victim_blocks)
            * len(args.patterns)
            * len(args.modulo)
            * args.iterations
    )

    csv_rows: list[tuple] = []
    total_flips = 0

    timers: Dict[str, float] = {k: 0.0 for k in (
        "template_render", "payload_compile", "victim_memset",
        "execute_payload", "memtest",
    )}

    with tqdm(total=total_iters, unit="iter", desc="DRAM Test") as bar:
        for acts, reps in product(args.acts_per_trefi, args.pattern_repetitions):

            if acts > 59:
                sys.exit(f"acts_per_trefi {acts} exceeds 59")
            hammer_cnt = acts // 2
            decoy_cnt = 59 - acts
            if decoy_cnt < 0:
                sys.exit("decoy_hammer_count negative")

            # render the template once per (acts,reps) combination
            t0 = time.perf_counter()
            filled_code = template_text.format(
                pattern_repetitions=reps,
                hammer_count=hammer_cnt,
                decoy_hammer_count=decoy_cnt,
                hammer_count_remainder=acts % 2,
            )
            timers["template_render"] += time.perf_counter() - t0

            payload_src = Path(args.output_dir) / f"payload_{acts}acts_{reps}reps.pyram"
            payload_src.write_text(filled_code, "utf-8")
            pattern_template = load_pyram_program(payload_src)

            # NEW outer loop: sweep over execution-counts
            for exec_cnt in args.payload_executions:

                for bank in args.banks:
                    for victims in victim_blocks:
                        victim_addrs = [DramAddress(bank, r) for r in victims]
                        aggr_rows = {r + off for r in victims for off in args.aggressor_offsets}
                        if overlap := aggr_rows & set(victims):
                            sys.exit(f"Row overlap: {sorted(overlap)}")
                        attacker_addrs = [DramAddress(bank, r) for r in sorted(aggr_rows)]

                        decoys = select_random_excluding_addresses(
                            addresses_exclude=victim_addrs + attacker_addrs,
                            count=args.decoy_rows,
                            min_distance=100,
                        )

                        t0 = time.perf_counter()
                        print(attacker_addrs)
                        print(decoys)
                        payload = compile_code(
                            code=pattern_template,
                            addresses_lookup={"addresses": attacker_addrs, "decoys": decoys},
                            dram_row_mapping=dram_row_mapping,
                        )
                        timers["payload_compile"] += time.perf_counter() - t0

                        if args.save_compiled_code:
                            bin_name = (
                                f"compiled_b{bank}_{acts}acts_{reps}reps_"
                                f"{victims[0]}-{victims[-1]}.bin"
                            )
                            write_payload_detail_to_file(payload, Path(args.output_dir) / bin_name)

                        controller.enable_refresh()

                        for pattern in args.patterns:
                            vict_pat = convert_byte_to_32bit_pattern(pattern)
                            aggr_pat = (~vict_pat) & 0xFFFFFFFF
                            patt_hex = f"0x{pattern:02X}"

                            print(f"{vict_pat}")
                            print(f"{aggr_pat}")

                            for modulo in args.modulo:
                                for iteration in range(args.iterations):
                                    # memset patterns
                                    t0 = time.perf_counter()
                                    controller.dma_memset_dram_addresses(victim_addrs, vict_pat)
                                    controller.dma_memset_dram_addresses(attacker_addrs, aggr_pat)
                                    timers["victim_memset"] += time.perf_counter() - t0

                                    controller.disable_refresh()
                                    controller.issue_refs(ref_cmd_count=4000)
                                    controller.align_mod_refresh(args.modulus, modulo)

                                    t0 = time.perf_counter()
                                    for _ in range(exec_cnt):
                                        controller.execute_payload(payload, verbose=False)
                                    timers["execute_payload"] += time.perf_counter() - t0

                                    controller.enable_refresh()

                                    t0 = time.perf_counter()
                                    flips = controller.dma_memtest_addresses(victim_addrs, vict_pat)
                                    timers["memtest"] += time.perf_counter() - t0

                                    total_flips += len(flips)
                                    refs_executed = reps * args.refs_per_pattern
                                    for f in flips:
                                        csv_rows.append(
                                            (
                                                iteration, modulo, bank, f.row, patt_hex,
                                                f.bit_index, f.byte_index(), str(payload_src),
                                                acts, refs_executed, exec_cnt,
                                            )
                                        )

                                    bar.set_postfix(
                                        bank=bank, acts=acts, reps=reps,
                                        execs=exec_cnt, modulo=modulo,
                                        flips=total_flips
                                    )
                                    bar.update(1)

    # timing summary
    print("\nTiming summary (seconds)")
    for name, sec in timers.items():
        print(f"{name:18s}: {sec:8.2f}")

    # CSV output
    if csv_rows:
        csv_name = f"bitflips_{dt.datetime.now():%Y%m%d_%H%M%S_%f}.csv"
        out_csv = Path(args.output_dir) / csv_name
        with out_csv.open("w", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow([
                "iteration", "modulo", "bank", "row", "pattern",
                "bit_flip_bit", "bit_flip_byte", "code_path",
                "acts_per_trefi", "refs_executed", "payload_exec_cnt",
            ])
            writer.writerows(csv_rows)
        print(f"\nCSV saved → {out_csv}")
    else:
        print("\nNo bit flips detected; no CSV produced.")

    print(f"\nTotal bit flips: {total_flips}")


if __name__ == "__main__":
    main()
