from dataclasses import dataclass


@dataclass(frozen=True)
class DramAddress:
    bank: int
    row: int

    def neighbor(self, distance: int) -> "DramAddress":
        """
        Returns a new DramAddress with the same bank but row offset by 'distance'.
        For example, neighbor(1) is one row after the current row;
        neighbor(-1) is one row before.
        """
        return DramAddress(bank=self.bank, row=self.row + distance)

    def to_dict(self):
        return {
            "bank": self.bank,
            "row": self.row,  # Decimal value
            "row_hex": f"0x{self.row:x}",  # Hex value
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"bank={self.bank}, "
            f"row={self.row} (0x{self.row:x})"
            f")"
        )
