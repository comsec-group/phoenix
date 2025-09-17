from typing import List

from utrr.dram.dram_address import DramAddress
from utrr.dram.row_group import RowGroup
from utrr.dram.subarray import Subarray
from utrr.dram.utils import sort_addresses_ascending, get_same_bank_or_raise


def find_row_groups(
    addresses: List[DramAddress],
    group_size: int,
    subarrays: List[Subarray],
    skip_middle: bool = True,
    min_distance: int = 1,
) -> List[RowGroup]:
    """
    Generates, filters, and de-overlaps row groups based on a minimum distance.

    Args:
        addresses (List[DramAddress]): List of DRAM addresses to process.
        group_size (int): Size of each row group.
        subarrays (List[Subarray]): Subarrays to filter row groups against.
        skip_middle (bool): Whether to skip the middle row in groups (default: True).
        min_distance (int): Minimum distance between the start rows of consecutive row groups.

    Returns:
        List[RowGroup]: De-overlapped row groups after processing.
    """

    # Step 1: Generate all overlapping row groups
    row_groups = generate_all_overlapping_row_groups(
        addresses=addresses, group_size=group_size, skip_middle=skip_middle
    )

    # Step 2: Filter row groups within the given subarrays
    filtered_row_groups = filter_rowgroups_within_subarrays(
        row_groups=row_groups, subarrays=subarrays
    )

    # Step 3: De-overlap the row groups
    de_overlapped_row_groups = []
    last_row_group_end = -1  # Initialize to an invalid row index for comparison

    for rg in filtered_row_groups:
        if rg.start_row >= last_row_group_end + min_distance:
            de_overlapped_row_groups.append(rg)
            last_row_group_end = rg.end_row  # Update the end of the last included group

    return de_overlapped_row_groups


def generate_all_overlapping_row_groups(
    addresses: List[DramAddress],
    group_size: int,
    skip_middle: bool = True,
) -> List[RowGroup]:
    if not addresses:
        return []

    unique_addresses = set(addresses)
    sorted_addresses = sort_addresses_ascending(unique_addresses)
    validated_bank = get_same_bank_or_raise(sorted_addresses)

    all_groups: List[RowGroup] = []
    total = len(sorted_addresses)

    for i in range(total):
        start_row = sorted_addresses[i].row
        expected_rows = [start_row + offset for offset in range(group_size)]

        if skip_middle and group_size > 2:
            middle_offset = group_size // 2
            expected_rows.remove(start_row + middle_offset)

        # Efficiently find matching rows by leveraging sorted order
        matching = [addr for addr in sorted_addresses if addr.row in expected_rows]

        if len(matching) == len(expected_rows):
            # Ensure rows are in the expected order
            ordered_rows = sorted(matching, key=lambda addr: addr.row)
            row_group = RowGroup(bank=validated_bank, rows=ordered_rows)
            all_groups.append(row_group)

    return all_groups


def filter_rowgroups_within_subarrays(
    row_groups: List[RowGroup], subarrays: List[Subarray]
) -> List[RowGroup]:
    return [
        rg
        for rg in row_groups
        if any(
            rg.start_row >= subarray.start_row and rg.end_row <= subarray.end_row
            for subarray in subarrays
        )
    ]
