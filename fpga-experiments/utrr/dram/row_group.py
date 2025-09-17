from dataclasses import dataclass
from typing import List

from utrr.dram.dram_address import DramAddress


@dataclass(frozen=True)
class RowGroup:
    """
    Represents a group of DRAM addresses within the same bank.

    Attributes:
        bank (int): The bank number shared by all addresses in the group.
        rows (List[DramAddress]): The list of DramAddress instances in the group.
    """

    bank: int
    rows: List[DramAddress]

    @property
    def start_row(self) -> int:
        """Returns the smallest row number in the group."""
        if not self.rows:
            raise ValueError("RowGroup has no addresses.")
        return self.rows[0].row

    @property
    def end_row(self) -> int:
        """Returns the largest row number in the group."""
        if not self.rows:
            raise ValueError("RowGroup has no addresses.")
        return self.rows[-1].row

    def get_present_addresses(self) -> List[DramAddress]:
        return self.rows.copy()

    def get_absent_addresses(self) -> List[DramAddress]:
        existing_rows = set(addr.row for addr in self.rows)
        full_range = set(range(self.start_row, self.end_row + 1))

        absent_rows = sorted(full_range - existing_rows)

        absent_addresses: List[DramAddress] = [
            DramAddress(bank=self.bank, row=row) for row in absent_rows
        ]

        return absent_addresses
