from dataclasses import dataclass, field
from typing import Tuple

from utrr.dram.dram_address import DramAddress


@dataclass(frozen=True)
class ExperimentResult:
    refresh_counter: int
    addresses_not_bitflipped: Tuple[DramAddress, ...] = field(default_factory=tuple)
    indices_not_bitflipped: Tuple[int, ...] = field(default_factory=tuple)
