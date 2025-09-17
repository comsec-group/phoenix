import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


def parse_row_range(row_range: str):
    start_row, end_row = map(int, row_range.split(":"))
    if start_row > end_row:
        raise ValueError("Start row must be less than or equal to end row.")
    return start_row, end_row


def convert_to_32bit_patterns(patterns: List[int]):
    patterns_32bit = []

    for p in patterns:
        repeated_pattern = convert_byte_to_32bit_pattern(p)
        patterns_32bit.append(repeated_pattern)

    return patterns_32bit


def convert_byte_to_32bit_pattern(pattern: int):
    masked_byte = pattern & 0xFF  # Ensure it's an 8-bit value
    repeated_pattern = int(f"{masked_byte:02x}" * 4, 16)  # Repeat the byte 4 times

    return repeated_pattern


def load_pyram_program(program_arg: Path) -> str:
    if not program_arg.is_file():
        raise FileNotFoundError(
            f"The file {program_arg} does not exist or is not a regular file."
        )

    try:
        with program_arg.open(mode="r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise OSError(f"Could not read the file '{program_arg}': {e}") from e


NAMED_DATA_PATTERNS = {
    "00": 0x00000000,
    "33": 0x33333333,
    "44": 0x44444444,
    "55": 0x55555555,
    "AA": 0xAAAAAAAA,
    "BB": 0xBBBBBBBB,
    "CC": 0xCCCCCCCC,
    "FF": 0xFFFFFFFF,
    "55AA": 0x55AA55AA,
    "AA55": 0xAA55AA55,
}


def parse_data_pattern(x: str) -> int:
    x = x.strip().upper()
    if x in NAMED_DATA_PATTERNS:
        return NAMED_DATA_PATTERNS[x]
    return int(x, 16) & 0xFFFFFFFF

@dataclass(frozen=True)
class PatternPair:
    victim: int
    aggressor: int


def get_pattern_pairs(victim_patterns: List[int]) -> List[PatternPair]:
    aggressor_patterns = [~p & 0xFFFFFFFF for p in victim_patterns]
    return [
        PatternPair(victim=v, aggressor=a)
        for v, a in zip(victim_patterns, aggressor_patterns)
    ]


def build_help_text() -> str:
    text = (
        "Specify one or more victim patterns in 32-bit hex (e.g., 0xDEADBEEF), "
        "or use any of these shortcuts:\n"
    )
    for name, val in NAMED_DATA_PATTERNS.items():
        text += f"  - {name:<4} => 0x{val:08X}\n"
    text += (
        "\nProvide multiple patterns separated by spaces if needed. "
        "The aggressor pattern is always the bitwise inversion of the victim pattern."
    )
    return text
