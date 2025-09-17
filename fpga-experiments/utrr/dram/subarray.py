from dataclasses import dataclass


@dataclass(frozen=True)
class Subarray:
    start_row: int
    end_row: int

    def contains(self, row: int) -> bool:
        """Check if the given row is within the subarray boundary."""
        return self.start_row <= row <= self.end_row

    def is_boundary_row(self, row: int) -> bool:
        return row == self.start_row or row == self.end_row

    def size(self) -> int:
        """Returns the number of rows in the subarray (inclusive)."""
        return self.end_row - self.start_row + 1

    def __repr__(self):
        return f"Subarray({self.start_row} to {self.end_row})"
