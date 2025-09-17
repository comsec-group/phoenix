import json
import random
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, List, Dict

import pandas as pd

from utrr.dram.dram_address import DramAddress
from utrr.dram.row_group import RowGroup
from utrr.dram.subarray import Subarray


# ------------------------- Sorting and Filtering -------------------------


def sort_addresses_ascending(addresses: Iterable[DramAddress]) -> List[DramAddress]:
    return sorted(list(addresses), key=lambda x: (x.bank, x.row))


def filter_min_distance_addresses(
    addresses: Iterable[DramAddress], min_row_distance: int
) -> List[DramAddress]:
    if not addresses:
        return []

    addresses = sort_addresses_ascending(addresses)
    filtered = [addresses[0]]

    for num in addresses[1:]:
        if all(abs(num.row - x.row) >= min_row_distance for x in filtered):
            filtered.append(num)

    return filtered


# ------------------------- Address Validation and Generation -------------------------


def get_same_bank_or_raise(addresses: List[DramAddress]) -> int:
    banks = {addr.bank for addr in addresses}
    if len(banks) != 1:
        raise ValueError("All addresses must have the same bank.")
    return banks.pop()


def generate_dram_addresses(bank: int, start: int, end: int) -> List[DramAddress]:
    addresses = []
    for row in range(start, end):
        addresses.append(DramAddress(bank=bank, row=row))
    return addresses


def get_rows(addresses: List[DramAddress]) -> List[int]:
    return [address.row for address in addresses]


def collect_present_addresses(row_groups: List[RowGroup]) -> List[DramAddress]:
    result = []
    for rg in row_groups:
        result.extend(rg.get_present_addresses())
    return result


def collect_absent_addresses(row_groups: List[RowGroup]) -> List[DramAddress]:
    result = []
    for rg in row_groups:
        result.extend(rg.get_absent_addresses())
    return result


# ----------------------- Serialization and Deserialization -----------------------


def deserialize_dram_addresses(json_file_path: Path) -> List[DramAddress]:
    with json_file_path.open("r") as file:
        data = json.load(file)
    return [DramAddress(bank=item["bank"], row=item["row"]) for item in data]


def serialize_dram_addresses(
    dram_addresses: Iterable[DramAddress], json_file_path: str
):
    with open(json_file_path, "w") as file:
        json.dump([address.to_dict() for address in dram_addresses], file, indent=4)


def deserialize_subarrays(file_path: Path) -> List[Subarray]:
    """Deserialize a CSV file into a list of Subarray objects."""
    # Read the CSV file
    df = pd.read_csv(file_path)

    # Create Subarray objects from the DataFrame
    subarrays = [
        Subarray(start_row=int(row["start_row"]), end_row=int(row["end_row"]))
        for _, row in df.iterrows()
    ]

    return subarrays


# ------------------------- Random Selection -------------------------


def select_random_excluding_addresses(
    addresses_exclude: List[DramAddress],
    count: int,
    min_distance: int,
    seed: int = None,
    max_row_limit: int = None,
    subarrays: Iterable[Subarray] = None,
):
    bank = get_same_bank_or_raise(addresses=addresses_exclude)
    rows = get_rows(addresses=addresses_exclude)

    return select_random_addresses(
        exclude_rows=rows,
        count=count,
        min_distance=min_distance,
        seed=seed,
        bank=bank,
        max_row_limit=max_row_limit,
        subarrays=subarrays,
    )


def select_random_addresses(
    exclude_rows: Iterable[int],
    count: int = 1,
    min_distance: int = 0,
    seed: int = None,
    bank: int = 0,
    max_row_limit: int = None,
    subarrays: Iterable[Subarray] = None,
) -> List[DramAddress]:
    if seed is None:
        seed = int(time.time_ns())

    rng = random.Random(seed)

    max_row = min(2**16, max_row_limit) if max_row_limit is not None else 2**16
    exclude_rows = set(exclude_rows)

    # Determine valid rows within the subarray boundaries
    if subarrays is None:
        subarrays = [Subarray(0, max_row - 1)]

    # Initialize a list to hold valid rows for each subarray
    subarray_valid_rows = []

    for boundary in subarrays:
        # Clamp the range within the global max_row limit
        start = max(0, boundary.start_row)
        end = min(max_row, boundary.end_row + 1)

        # Exclude rows within the min_distance range
        valid_rows = set(range(start, end))
        for exclude_row in exclude_rows:
            exclude_start = max(start, exclude_row - min_distance)
            exclude_end = min(end, exclude_row + min_distance + 1)
            valid_rows -= set(range(exclude_start, exclude_end))

        subarray_valid_rows.append(list(valid_rows))

    # Check if there are enough valid rows to distribute evenly
    total_valid_rows = sum(len(rows) for rows in subarray_valid_rows)
    if total_valid_rows < count:
        raise ValueError(
            "Not enough rows available to select the requested number of random rows."
        )

    # Evenly distribute the row selection across subarrays
    selected_rows = []
    remaining_count = count

    while remaining_count > 0:
        for rows in subarray_valid_rows:
            if not rows or remaining_count <= 0:
                continue
            # Pick one random row from this subarray
            selected_row = rng.choice(rows)
            selected_rows.append(selected_row)
            rows.remove(selected_row)
            remaining_count -= 1
            if remaining_count <= 0:
                break

    addresses = []
    for row in selected_rows:
        addresses.append(DramAddress(bank=bank, row=row))

    return addresses


def group_indices_by_address(
    victim_addresses: List[DramAddress],
) -> Dict[DramAddress, List[int]]:
    grouped_indices = defaultdict(list)
    for index, address in enumerate(victim_addresses):
        grouped_indices[address].append(index)
    return grouped_indices
