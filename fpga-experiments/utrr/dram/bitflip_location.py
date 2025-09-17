from dataclasses import dataclass


@dataclass(frozen=True)
class BitFlipLocation:
    bank: int
    row: int
    bit_index: int

    def byte_index(self) -> int:
        """Which byte does this bit belong to?"""
        return self.bit_index // 8

    def surrounding_byte_bit_indices(self) -> list[int]:
        """
        Returns all bit indices (absolute) belonging to the same byte
        that contains this bit_index.
        """
        start = self.byte_index() * 8
        return list(range(start, start + 8))

    def __eq__(self, other):
        if not isinstance(other, BitFlipLocation):
            return NotImplemented
        return (self.bank, self.row, self.bit_index) == (
            other.bank,
            other.row,
            other.bit_index,
        )

    def __lt__(self, other):
        if not isinstance(other, BitFlipLocation):
            return NotImplemented
        return (self.bank, self.row, self.bit_index) < (
            other.bank,
            other.row,
            other.bit_index,
        )

    def __repr__(self):
        return f"(bank={self.bank}, row={self.row}, bit_index={self.bit_index}, byte_index={self.byte_index()})"
