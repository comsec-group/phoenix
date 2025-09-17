import logging
import sys
from typing import List, Iterable, Dict, Tuple

from bitarray import bitarray

from rowhammer_tester.gateware.payload_executor import Encoder, OpCode
from rowhammer_tester.scripts.litedram_settings import LiteDramSettings
from rowhammer_tester.scripts.utils import (
    RemoteClient,
    get_generated_file,
    DRAMAddressConverter,
    memread,
    hw_memtest,
    memwrite,
    hw_memset,
    execute_payload,
    hw_memtest_count,
)
from utrr.dram.bitflip_location import BitFlipLocation
from utrr.dram.bitutil import BitUtil
from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_row_mapping import DramRowMapping

logger = logging.getLogger(__name__)


# 0001100110000010
def decode_address(addr: int, bankbits: int, nranks: int):
    """
    Decodes the address based on:
      - rank is in the least significant bits (LSB)
      - then bankbits
      - the rest of the upper bits become the row

    The function returns (bank, rank, row).
    """
    import math

    # Number of bits used to encode rank, e.g. nranks=2 => rankbits=1, nranks=4 => rankbits=2, etc.
    rankbits = int(math.log2(nranks))

    # Masks
    rank_mask = (1 << rankbits) - 1
    bank_mask = (1 << bankbits) - 1

    # 1) Extract rank from the least significant bits
    rank = addr & rank_mask

    # 2) Extract bank from the next chunk of bits
    bank = (addr >> rankbits) & bank_mask

    # 3) The remaining upper bits become the row
    row = addr >> (rankbits + bankbits)

    return bank, rank, row


def print_payload_detail(payload: List[Encoder.Instruction]):
    json_file = get_generated_file("litedram_settings.json")
    settings = LiteDramSettings.from_json_file(json_file)

    # For convenience
    bankbits = settings.geom.bankbits
    nranks = settings.phy.nranks  # e.g. 1, 2, or 4, etc.

    for instruction in payload:
        op, *args = map(lambda p: p[1], instruction._parts)

        if op == OpCode.ACT:
            # Typically the 2nd argument is your "encoded address"
            # (Double-check the actual argument order in your real code.)
            # Example: if `args` is [some_value, address], then:
            #     address = args[1]
            # or if it's just one argument after the OpCode, do `address = args[0]`
            address = args[1]

            # Decode into bank/rank/row
            bank, rank, row = decode_address(address, bankbits, nranks)

            # Print something like:
            # OpCode.ACT <rank> <bank> <row>

            # Write in detail: show row in decimal and hex
            row_str = f"{row} (0x{row:x})"
            print(
                op,
                f"address={hex(address)}",
                f"rank={rank}",
                f"bank={bank}",
                f"row={row_str}",
                sep="\t",
            )
        else:
            # For other opcodes, just print as-is (or adapt as needed).
            print(op, *map(hex, args), sep="\t")


def print_payload(payload: List[Encoder.Instruction]):
    for instruction in payload:
        op, *args = map(lambda p: p[1], instruction._parts)
        print(op, *map(hex, args), sep="\t")


OPCODE_MAP = {
    4: "OpCode.ACT",
    5: "OpCode.PRE",
    6: "OpCode.REF",
    7: "OpCode.LOOP",
    0: "OpCode.NOOP",
    # Add more mappings as needed
}


def write_payload_to_file(payload: List[Encoder.Instruction], file_path: str):
    with open(file_path, "w") as file:
        for instruction in payload:
            op, *args = map(lambda p: p[1], instruction._parts)
            op_str = OPCODE_MAP.get(
                op, f"OpCode.UNKNOWN({op})"
            )  # Handle unknown opcodes
            args_str = "\t".join(map(hex, args))
            file.write(f"{op_str}\t{args_str}\n")


def write_payload_detail_to_file(payload: List[Encoder.Instruction], file_path: str):
    """
    Writes each instruction in the payload to a file with detailed information:
      - Opcode (mapped via OPCODE_MAP)
      - Hex arguments (for non-ACT)
      - For OpCode.ACT, also decode the address as (bank, rank, row).
        Prints row in both decimal and hex.
    """
    # Load LiteDRAM settings (adapt to your environment)
    json_file = get_generated_file("litedram_settings.json")
    settings = LiteDramSettings.from_json_file(json_file)

    # For convenience
    bankbits = settings.geom.bankbits
    nranks = settings.phy.nranks

    with open(file_path, "w") as file:
        for instruction in payload:
            # Unpack opcode & arguments
            op, *args = map(lambda p: p[1], instruction._parts)

            # Look up a friendly name for the opcode
            op_str = OPCODE_MAP.get(op, f"OpCode.UNKNOWN({op})")

            if op_str == "OpCode.ACT":
                # We expect the second argument to be the "encoded address"
                # (adapt if your payload format differs)
                address = args[1]

                # Decode (bank, rank, row)
                bank, rank, row = decode_address(address, bankbits, nranks)

                # Write in detail: show row in decimal and hex
                row_str = f"{row} (0x{row:x})"
                file.write(
                    f"{op_str}\t"
                    f"address={hex(address)}\t"
                    f"rank={rank}\t"
                    f"bank={bank}\t"
                    f"row={row_str}\n"
                )
            else:
                # Otherwise, just write out the opcode and the arguments (in hex)
                args_str = "\t".join(map(hex, args))
                file.write(f"{op_str}\t{args_str}\n")


def payload_to_string(payload: List[Encoder.Instruction]) -> str:
    result = []
    for instruction in payload:
        op, *args = map(lambda p: p[1], instruction._parts)
        args_str = "\t".join(map(hex, args))
        result.append(f"{op}\t{args_str}")
    return "\n".join(result)


class DramController:
    # Class-level cache of already-created instances.
    _instances = {}

    def __new__(cls, dram_row_mapping: DramRowMapping):
        """
        Controls the creation of the object. If we already have a DramController
        for this dram_row_mapping, return it instead of creating a new one.
        """
        if dram_row_mapping in cls._instances:
            return cls._instances[dram_row_mapping]
        instance = super().__new__(cls)
        cls._instances[dram_row_mapping] = instance
        return instance

    def __init__(self, dram_row_mapping: DramRowMapping):
        """
        Actual initialization. Using the _initialized flag
        ensures this only happens once per unique instance.
        """
        if getattr(self, "_initialized", False):
            # We've already initialized this instance, so skip.
            return
        self._initialized = True

        self.dram_row_mapping = dram_row_mapping

        json_file = get_generated_file("litedram_settings.json")
        self.settings = LiteDramSettings.from_json_file(json_file)
        self.dma_data_width_bytes = self.settings.get_dram_port_width_bytes()
        self.nbanks = 2**self.settings.geom.bankbits
        self.converter = DRAMAddressConverter.load()

        self.client = RemoteClient()
        self.client.open()
        self.main_ram_base = self.client.mems.main_ram.base
        self.main_ram_size = self.client.mems.main_ram.size
        self.payload_mem_size = self.client.mems.payload.size

        self._last_payload = None
        self.encoder = Encoder(
            bankbits=self.settings.geom.bankbits, nranks=self.settings.phy.nranks
        )

    def dma_memset_rows(
        self, bank: int, rows: Iterable[int], pattern_32bit: int
    ) -> None:
        for row in rows:
            self.dma_memset_row(bank, row, pattern_32bit)

    def dma_memset_row(self, bank: int, row: int, pattern_32bit: int) -> None:
        logical_row = self.dram_row_mapping.physical_to_logical(row)
        start, end, offset = self.compute_row_address_range(
            converter=self.converter,
            bank=bank,
            row=logical_row,
            base=self.client.mems.main_ram.base,
        )
        hw_memset(
            self.client,
            offset,
            end - start,
            [pattern_32bit],
            dbg=False,
            print_progress=False,
        )

    def dma_memset_dram_address(self, address: DramAddress, pattern_32bit: int) -> None:
        self.dma_memset_row(
            bank=address.bank, row=address.row, pattern_32bit=pattern_32bit
        )

    def dma_memset_dram_addresses(
        self, addresses: Iterable[DramAddress], pattern_32bit: int
    ) -> None:
        for address in addresses:
            self.dma_memset_row(
                bank=address.bank, row=address.row, pattern_32bit=pattern_32bit
            )

    def dma_memtest_rows(
        self, bank: int, rows: Iterable[int], pattern_32bit: int
    ) -> Dict[int, List[BitFlipLocation]]:

        bitflips_per_row = {}

        for row in set(rows):
            bitflips_row = self.dma_memtest_row(bank, row, pattern_32bit)
            if bitflips_row:
                bitflips_per_row[row] = bitflips_row

        return bitflips_per_row

    def dma_memtest_address(
        self, address: DramAddress, pattern_32bit: int
    ) -> List[BitFlipLocation]:
        return self.dma_memtest_row(
            bank=address.bank, row=address.row, pattern_32bit=pattern_32bit
        )

    def dma_memtest_addresses(
        self, addresses: Iterable[DramAddress], pattern_32bit: int
    ) -> List[BitFlipLocation]:
        bit_flips = []

        for address in addresses:
            bit_flips.extend(self.dma_memtest_row(
                bank=address.bank, row=address.row, pattern_32bit=pattern_32bit
            ))

        return bit_flips

    def dma_memtest_row(
        self, bank: int, row: int, pattern_32bit: int
    ) -> List[BitFlipLocation]:
        logical_row = self.to_logical_row(row)

        start, end, offset = self.compute_row_address_range(
            converter=self.converter,
            bank=bank,
            row=logical_row,
            base=self.client.mems.main_ram.base,
        )

        errors = hw_memtest(
            self.client,
            offset,
            end - start,
            [pattern_32bit],
            dbg=False,
            print_progress=False,
        )

        bitflip_locations = []
        for error in errors:
            error_bitflip_locations = self.compute_bitflip_locations(
                base_address=self.client.mems.main_ram.base,
                offset=error.offset,
                dma_data_bytes=error.dma_data_bytes,
                data=error.data,
                expected=error.expected,
                converter=self.converter,
            )
            bitflip_locations.extend(error_bitflip_locations)

        _bitflip_locations = []
        for bitflip_location in bitflip_locations:
            row = self.dram_row_mapping.logical_to_physical(bitflip_location.row)
            _bitflip_locations.append(
                BitFlipLocation(
                    row=row,
                    bank=bitflip_location.bank,
                    bit_index=bitflip_location.bit_index,
                )
            )
        return _bitflip_locations

    def dma_memtest_rows_flipped(
        self, bank: int, rows: Iterable[int], pattern_32bit: int
    ) -> List[int]:

        bitflips_existence = []

        for row in set(rows):
            bitflips_row = self.dma_memtest_row_flipped(bank, row, pattern_32bit)
            if bitflips_row:
                bitflips_existence.append(row)

        return bitflips_existence

    def dma_memtest_addresses_flipped(
        self, addresses: Iterable[DramAddress], pattern_32bit: int
    ) -> List[DramAddress]:
        bitflips_existence = []

        for address in set(addresses):
            bitflips_row = self.dma_memtest_row_flipped(
                bank=address.bank, row=address.row, pattern_32bit=pattern_32bit
            )
            if bitflips_row:
                bitflips_existence.append(address)

        return bitflips_existence

    def dma_memtest_row_flipped(self, bank: int, row: int, pattern_32bit: int) -> bool:
        logical_row = self.to_logical_row(row)

        start, end, offset = self.compute_row_address_range(
            converter=self.converter,
            bank=bank,
            row=logical_row,
            base=self.client.mems.main_ram.base,
        )

        error_count = hw_memtest_count(
            self.client, offset, end - start, [pattern_32bit], dbg=False
        )

        return error_count > 0

    def memread_rowbits(self, bank: int, row: int) -> bitarray:
        logical_row = self.dram_row_mapping.physical_to_logical(row)
        base_address_bus = self.converter.encode_bus(bank=bank, row=logical_row, col=0)

        row_32bit_words = memread(self.client, 1024, base=base_address_bus)

        row_bits = BitUtil.int_list_to_bitarray(row_32bit_words)
        return row_bits

    def read_row_bits(self, address: DramAddress) -> bitarray:
        return self.memread_rowbits(bank=address.bank, row=address.row)

    def memwrite_rowsbits(self, bank: int, rows: Iterable[int], bits: bitarray):
        for row in rows:
            self.memwrite_rowbits(bank, row, bits)

    def memwrite_rowbits(self, bank: int, row: int, bits: bitarray):
        logical_row = self.dram_row_mapping.physical_to_logical(row)
        base_address_bus = self.converter.encode_bus(bank=bank, row=logical_row, col=0)

        row_32bit_words = BitUtil.bitarray_to_int_list(bits)

        memwrite(wb=self.client, data=row_32bit_words, base=base_address_bus)

    def write_row_bits(self, address: DramAddress, bits: bitarray) -> None:
        self.memwrite_rowbits(bank=address.bank, row=address.row, bits=bits)

    def write_rows_bits(self, addresses: List[DramAddress], bits: bitarray) -> None:
        for address in addresses:
            self.write_row_bits(address=address, bits=bits)

    def memread_32bit(self, bank: int, row: int, col: int) -> int:
        logical_row = self.dram_row_mapping.physical_to_logical(row)
        base_address_bus = self.converter.encode_bus(
            bank=bank, row=logical_row, col=col
        )

        return memread(wb=self.client, n=1, base=base_address_bus)[0] & 0xFFFFFFFF

    def memwrite_32bit(self, bank: int, row: int, col: int, pattern_32bit: int) -> None:
        logical_row = self.dram_row_mapping.physical_to_logical(row)
        base_address_bus = self.converter.encode_bus(
            bank=bank, row=logical_row, col=col
        )
        pattern = pattern_32bit & 0xFFFFFFFF

        memwrite(wb=self.client, data=[pattern], base=base_address_bus)

    def memtest_32bit(
        self, bank: int, row: int, col: int, pattern_32bit: int
    ) -> List[BitFlipLocation]:
        read_32bit = self.memread_32bit(bank=bank, row=row, col=col)
        expected_pattern = pattern_32bit & 0xFFFFFFFF

        # Calculate the bitwise difference
        diff = expected_pattern ^ read_32bit
        bitflip_locations = []

        # Identify each bit that differs
        bit_offset = 32 * col
        for bit_position in range(32):
            if diff & (1 << bit_position):
                # Calculate the bit index with the offset
                bit_index = bit_offset + bit_position
                # Create a BitFlipLocation for each flipped bit
                bitflip_locations.append(
                    BitFlipLocation(bank=bank, row=row, bit_index=bit_index)
                )

        return bitflip_locations

    def memtest_rows(
        self, bank: int, rows: Iterable[int], data_pattern: int
    ) -> List[BitFlipLocation]:
        bitflip_locations = []

        for row in rows:
            bitflip_locations_row = self.memtest_row(bank, row, data_pattern)
            bitflip_locations.extend(bitflip_locations_row)

        return sorted(bitflip_locations)

    def memtest_row(
        self, bank: int, row: int, data_pattern: int
    ) -> List[BitFlipLocation]:

        rowbits = self.memread_rowbits(bank, row)
        expectedbits = BitUtil.repeat_32bit_int_to_bitarray(data_pattern)

        bitflip_columns = BitUtil.find_differing_bit_positions(rowbits, expectedbits)

        bitflip_locations = []
        for column in bitflip_columns:
            bitflip_locations.append(BitFlipLocation(bank, row, column))

        return bitflip_locations

    def memtest_rowsbits(self, bank: int, rows: Iterable[int], expected_bits: bitarray):
        bitflips = []

        for row in rows:
            bitflips_row = self.memtest_rowbits(
                bank=bank, row=row, expected_bits=expected_bits
            )
            bitflips.extend(bitflips_row)

        return bitflips

    def memtest_rowbits(
        self, bank: int, row: int, expected_bits: bitarray
    ) -> List[BitFlipLocation]:

        rowbits = self.memread_rowbits(bank, row)
        bitflip_columns = BitUtil.find_differing_bit_positions(rowbits, expected_bits)

        bitflip_locations = []
        for column in bitflip_columns:
            bitflip_locations.append(BitFlipLocation(bank, row, column))

        return bitflip_locations

    def test_rowbits(
        self, address: DramAddress, expected_bits: bitarray
    ) -> List[BitFlipLocation]:
        return self.memtest_rowbits(
            bank=address.bank, row=address.row, expected_bits=expected_bits
        )

    def dma_memtest_rowbits(self, bank: int, row: int, expected_bits: bitarray):
        relative_pattern = 0x0
        bitflips_relative_pattern = self.dma_memtest_row(
            bank=bank, row=row, pattern_32bit=relative_pattern
        )

        rowbits = BitUtil.row_bitarray_zero()
        for bitflip in bitflips_relative_pattern:
            rowbits[bitflip.bit_index] = 1

        bitflip_columns = BitUtil.find_differing_bit_positions(rowbits, expected_bits)

        bitflip_locations = []
        for column in bitflip_columns:
            bitflip_locations.append(BitFlipLocation(bank, row, column))

        return bitflip_locations

    def align_refresh(self, target_ref_count: int):
        self.disable_refresh()
        ref_count = self.read_refresh_count()
        logger.debug(f"Refresh count before alignment: {ref_count}")

        if ref_count > target_ref_count:
            raise ValueError(
                f"Initial refresh count ({ref_count}) exceeds the target refresh count ({target_ref_count}). "
                "Ensure the initial count is within acceptable bounds."
            )
        current_ref = ref_count

        while current_ref < target_ref_count:
            increment = min(1000, target_ref_count - current_ref)
            current_ref += increment
            ref_payload = self.generate_refresh_payload(
                refresh_count=increment, verbose=False
            )
            self.execute_payload(payload=ref_payload, verbose=False)
            actual_ref_count = self.read_refresh_count()
            if current_ref != actual_ref_count:
                raise RuntimeError(
                    f"Refresh count mismatch during alignment: expected {current_ref}, "
                    f"but read {actual_ref_count}. This may indicate an issue with the refresh payload execution."
                )
            logger.debug(
                f"Aligned refresh count: incremented by {increment}, current count: {current_ref}"
            )

        final_ref_count = self.read_refresh_count()
        logger.debug(f"Refresh count after alignment: {final_ref_count}")

    def align_mod_refresh(self, modulus: int, mod_value: int):
        refresh_count = self.read_refresh_count()

        # Compute the target refresh count based on the specified modulo
        target_refresh_count = (
            refresh_count + modulus - (refresh_count % modulus) + mod_value
        )

        self.align_refresh(target_refresh_count)

    def enable_refresh(self) -> None:
        self.client.regs.controller_settings_refresh.write(1)

    def disable_refresh(self) -> None:
        self.client.regs.controller_settings_refresh.write(0)

    def read_refresh_count(self) -> int:
        self.client.regs.dfi_switch_refresh_update.write(1)
        now = self.client.regs.dfi_switch_refresh_count.read()
        return now

    def to_logical_row(self, row: int) -> int:
        return self.dram_row_mapping.physical_to_logical(row)

    def precharge_all_payload(self):
        encoder = self.encoder
        timing = self.settings.timing

        # First instruction after mode transition should be a NOOP that waits until tRFC is satisfied
        # As we include REF as first instruction we actually wait tREFI here
        payload = [
            encoder.Instruction(
                OpCode.NOOP, timeslice=max(1, timing.tRFC - 2, timing.tREFI - 2)
            ),
            encoder.Instruction(
                OpCode.PRE,
                timeslice=timing.tRP,
                address=encoder.address(col=1 << 10, rank=0),
            ),  # precharge all
            encoder.Instruction(OpCode.NOOP, timeslice=0),  # STOP
        ]

        return payload

    def issue_refs(self, ref_cmd_count: int) -> None:
        max_refs = 4000
        for _ in range(ref_cmd_count // max_refs):
            self.__issue_refs(ref_cmd_count=max_refs)
        # Issue any leftover counts (if any)
        remainder = ref_cmd_count % max_refs
        if remainder:
            self.__issue_refs(ref_cmd_count=remainder)

    def __issue_refs(self, ref_cmd_count: int):
        payload = self.generate_refresh_payload(
            refresh_count=ref_cmd_count, verbose=False
        )
        self.execute_payload(payload=payload, verbose=False)

    def payload_mem_size(self) -> int:
        return self.client.mems.payload.size

    def generate_refresh_payload(
        self, refresh_count: int = 1, verbose: bool = True
    ) -> List[Encoder.Instruction]:
        encoder = self.encoder
        timing = self.settings.timing

        payload = []

        # First instruction after mode transition should be a NOOP that waits until tRFC is satisfied
        # As we include REF as first instruction we actually wait tREFI here
        payload.extend(
            [
                encoder.Instruction(
                    OpCode.NOOP, timeslice=max(1, timing.tRFC - 2, timing.tREFI - 2)
                )
            ]
        )

        if refresh_count > 0:
            assert refresh_count <= 4096
            refresh_loop = [
                encoder.Instruction(
                    OpCode.PRE,
                    timeslice=timing.tRP,
                    address=encoder.address(col=1 << 10, rank=0),
                ),  # precharge all
                encoder.Instruction(OpCode.REF, timeslice=1),
                encoder.Instruction(OpCode.NOOP, timeslice=(timing.tREFI - timing.tRP)),
                encoder.Instruction(OpCode.LOOP, jump=3, count=refresh_count - 1),
            ]
            payload.extend(refresh_loop)
            # payload.append(encoder.Instruction(OpCode.LOOP, jump=3, count=refresh_count))

        payload.append(encoder.Instruction(OpCode.NOOP, timeslice=0))  # STOP

        payload_mem_size = self.client.mems.payload.size
        if verbose:
            print_payload(payload)

        if len(payload) > payload_mem_size // 4:
            print(
                "Memory required for payload executor instructions ({} bytes) exceeds available payload memory ({} bytes)".format(
                    len(payload) * 4, payload_mem_size
                )
            )
            print(
                "The payload memory size can be changed with '--payload-size ' option."
            )
            sys.exit(1)

        return payload

    def execute_payload(self, payload: List[Encoder.Instruction], verbose: bool = True):
        encoder = self.encoder
        assert len(payload) * 4 < self.payload_mem_size
        execute_payload(encoder(payload), self.client, verbose)

    @staticmethod
    def compute_row_address_range(
        converter: DRAMAddressConverter, bank: int, row: int, base: int = 0x40000000
    ) -> Tuple[int, int, int]:
        """
        According to https://github.com/antmicro/rowhammer-tester/issues/46#issuecomment-773915844
        """

        # Encode the start of the bus range (first column of the row)
        num_banks = 2**converter.bankbits
        start_address = converter.encode_bus(bank=bank, row=row, col=0)

        # Calculate the next bank and row to determine the end address
        next_bank = (bank + 1) % num_banks
        next_row = row + (bank + 1) // num_banks
        end_address = converter.encode_bus(bank=next_bank, row=next_row, col=0)

        # Calculate the offset from the RAM base address
        address_offset = start_address - base

        return start_address, end_address, address_offset

    @staticmethod
    def resolve_memory_address(
        base_address: int, offset: int, dma_data_bytes: int
    ) -> int:
        return base_address + offset * dma_data_bytes

    def resolve_logical_dram_address(
        self,
        base_address: int,
        offset: int,
        dma_data_bytes: int,
        converter: DRAMAddressConverter,
    ):
        address = self.resolve_memory_address(base_address, offset, dma_data_bytes)
        bank, row, col = converter.decode_bus(address=address, base=base_address)
        return bank, row, col * 4 * 8  # 4 bytes per col

    def compute_bitflip_locations(
        self,
        base_address: int,
        offset: int,
        dma_data_bytes: int,
        data: int,
        expected: int,
        converter: DRAMAddressConverter,
    ) -> List[BitFlipLocation]:
        bank, row, base_col = self.resolve_logical_dram_address(
            base_address, offset, dma_data_bytes, converter
        )

        bitflips = []
        flipped_bits = data ^ expected

        data_width_bits = dma_data_bytes * 8
        for bit_pos in range(data_width_bits):
            if flipped_bits & (1 << bit_pos):
                bitflips.append(BitFlipLocation(bank, row, base_col + bit_pos))

        return bitflips

    def __del__(self):
        self.client.close()
