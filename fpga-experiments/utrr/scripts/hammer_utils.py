import logging
from dataclasses import dataclass
from typing import Optional, List

from bitarray import bitarray

from utrr.dram.bitflip_location import BitFlipLocation
from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_controller import DramController
from utrr.dram.dram_row_mapping import DramRowMapping
from utrr.dsl.compile import compile_code

logger = logging.getLogger(__name__)


def hammer_victim_double_sided_payload(
    victim: DramAddress, hammer_count: int, dram_row_mapping: DramRowMapping
):
    addresses_lookup = {"addresses": [victim]}
    code = f"""
for _ in range({hammer_count}):
    act(bank=addresses[0].bank, row=addresses[0].row + 1)
    pre()
    act(bank=addresses[0].bank, row=addresses[0].row - 1)
    pre()
        """
    payload = compile_code(
        code=code, addresses_lookup=addresses_lookup, dram_row_mapping=dram_row_mapping
    )
    return payload


def act_pre_payload(
    address: DramAddress, dram_row_mapping: DramRowMapping, hammer_count: int = 1
):
    addresses_lookup = {"addresses": [address]}
    code = f"""
for _ in range({hammer_count}):
    act(bank=addresses[0].bank, row=addresses[0].row)
    pre()
        """
    payload = compile_code(
        code=code, addresses_lookup=addresses_lookup, dram_row_mapping=dram_row_mapping
    )
    return payload


@dataclass
class HcEccDsResult:
    hammer_count: int
    bit_flips: List[BitFlipLocation]


def find_hc_ecc_ds(
    controller: DramController,
    bank: int,
    row: int,
    victim_pattern_32bit: int,
    aggressor_pattern_32bit: int,
    update_diff: int = 1,
    hc_min: int = 0,
    hc_max: int = 500_000,
) -> Optional[HcEccDsResult]:
    low_hc = hc_min
    high_hc = hc_max
    hc_first = -1

    # 1) Binary Search in [hc_min, hc_max]
    while high_hc - low_hc > update_diff:
        mid_hc = (low_hc + high_hc) // 2

        hammer_double_sided(
            controller=controller,
            bank=bank,
            row=row,
            victim_pattern=victim_pattern_32bit,
            attacker_pattern=aggressor_pattern_32bit,
            hammer_count=mid_hc,
        )

        row_flipped = controller.dma_memtest_row_flipped(
            bank=bank, row=row, pattern_32bit=victim_pattern_32bit
        )

        if row_flipped:
            high_hc = mid_hc
            hc_first = mid_hc
        else:
            low_hc = mid_hc + 1

    # 2) If 'hc_first' != -1, we've found a flipping region.
    #    Then increment from hc_first until we actually see flips
    if hc_first != -1:
        bit_flips = []
        while not bit_flips and hc_first < hc_max:
            hc_first += 1

            hammer_double_sided(
                controller=controller,
                bank=bank,
                row=row,
                victim_pattern=victim_pattern_32bit,
                attacker_pattern=aggressor_pattern_32bit,
                hammer_count=hc_first,
            )
            bit_flips = controller.dma_memtest_row(
                bank=bank, row=row, pattern_32bit=victim_pattern_32bit
            )

        return HcEccDsResult(hammer_count=hc_first, bit_flips=bit_flips)

    return None


def hammer_double_sided(
    controller: DramController,
    bank: int,
    row: int,
    victim_pattern: int,
    attacker_pattern: int,
    hammer_count: int,
):
    victim = DramAddress(bank=bank, row=row)
    dram_row_mapping = controller.dram_row_mapping

    attackers = [
        DramAddress(bank=victim.bank, row=victim.row + 1),
        DramAddress(bank=victim.bank, row=victim.row - 1),
    ]

    controller.dma_memset_dram_addresses(
        addresses=attackers, pattern_32bit=attacker_pattern
    )
    controller.dma_memset_dram_address(address=victim, pattern_32bit=victim_pattern)

    payload = hammer_victim_double_sided_payload(victim, hammer_count, dram_row_mapping)

    controller.disable_refresh()
    controller.execute_payload(payload=payload, verbose=False)
    controller.enable_refresh()


def init_aggressors_and_ds_hammer(
    controller: DramController,
    victim: DramAddress,
    aggressor_bits: bitarray,
    hammer_count: int,
) -> None:
    """
    Initializes the two aggressor rows (above and below 'victim') with
    'aggressor_bits' and then performs a double-sided hammer (ds_hammer)
    at 'hammer_count', leaving the victim row untouched.
    """
    # Build a double-sided hammer payload for the victim row
    payload = hammer_victim_double_sided_payload(
        victim=victim,
        hammer_count=hammer_count,
        dram_row_mapping=controller.dram_row_mapping,
    )

    # Identify aggressor rows
    aggressors = [
        DramAddress(bank=victim.bank, row=victim.row + 1),
        DramAddress(bank=victim.bank, row=victim.row - 1),
    ]

    # Write the specified bit pattern to each aggressor row
    controller.write_rows_bits(addresses=aggressors, bits=aggressor_bits)

    # Hammer: disable refresh, run payload, then re-enable refresh
    controller.disable_refresh()
    controller.execute_payload(payload=payload, verbose=False)
    controller.enable_refresh()

