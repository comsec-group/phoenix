from typing import List

from bitarray import bitarray


class BitUtil:
    @staticmethod
    def find_differing_bit_positions(bits1: bitarray, bits2: bitarray) -> List[int]:
        # Ensure both bitarrays are of the same length
        if len(bits1) != len(bits2):
            raise ValueError("Bitarrays must be of the same length for comparison.")

        # XOR the two bitarrays to get a bitarray where differences are marked with 1s
        difference = bits1 ^ bits2

        # Record positions where there is a 1 in the difference bitarray
        differing_positions = [i for i, bit in enumerate(difference) if bit == 1]

        return differing_positions

    @staticmethod
    def int_list_to_bitarray(int_list: List[int]) -> bitarray:
        # Convert each 32-bit integer to a 32-bit binary string with reversed bits
        binary_str = "".join(f"{num:032b}"[::-1] for num in int_list)

        # Create a bitarray from the combined reversed binary string
        bits = bitarray(binary_str)
        return bits

    @staticmethod
    def bitarray_to_int_list(bits: bitarray) -> List[int]:
        # Ensure the bitarray length is a multiple of 32
        if len(bits) % 32 != 0:
            bits.extend([0] * (32 - (len(bits) % 32)))

        int_list = [
            int(bits[i : i + 32][::-1].to01(), 2)  # Reverse bits in each 32-bit chunk
            for i in range(0, len(bits), 32)
        ]
        return int_list

    @staticmethod
    def repeat_32bit_int_to_bitarray(pattern_32bit: int) -> bitarray:
        # Create a list with the integer repeated the required number of times
        int_list = [pattern_32bit & 0xFFFFFFFF] * 1024
        return BitUtil.int_list_to_bitarray(int_list)

    @staticmethod
    def row_bitarray_zero(bytes_per_row: int = 4096) -> bitarray:
        int_list = [0x0] * (bytes_per_row // 4)
        return BitUtil.int_list_to_bitarray(int_list)

    @staticmethod
    def row_bitarray_one(bytes_per_row: int = 4096) -> bitarray:
        int_list = [0xFFFFFFFF] * (bytes_per_row // 4)
        return BitUtil.int_list_to_bitarray(int_list)

    @staticmethod
    def invert_bitarray_copy(bits: bitarray) -> bitarray:
        """
        Returns a *new* bitarray that is the inverted version of 'bits'.
        The original 'bits' remains unchanged.
        """
        inverted = bits.copy()
        inverted.invert()
        return inverted
