from pyparsing import ParseException

from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_controller import print_payload_detail, write_payload_detail_to_file
from utrr.dram.dram_row_mapping import DirectDramRowMapping
from utrr.dram.utils import select_random_excluding_addresses
from utrr.dsl.compile import compile_code

code = """
# This is a comment
for i in range(28):
    act(bank=addresses[i].bank, row=addresses[i].row + 1)
    pre()
    act(bank=addresses[i].bank, row=addresses[i].row - 1)
    pre()
    
ref()

for i in range(28, 56):
    act(bank=addresses[i].bank, row=addresses[i].row + 1)
    pre()
    act(bank=addresses[i].bank, row=addresses[i].row - 1)
    pre()
"""

#        1100100
# 00000001100101000000
#     0001100101000010
# Example DRAM addresses
dram_addresses = []
for row in range(101, 10000, 50):
    dram_addresses.append(
        DramAddress(bank=1, row=row),
    )

try:
    row_mapping = DirectDramRowMapping()
    decoys = select_random_excluding_addresses(
        addresses_exclude=dram_addresses,
        count=100,
        min_distance=100,
    )
    addresses_lookup = {
        "addresses": dram_addresses,
        "decoys": decoys,
    }
    compiled_program = compile_code(code, addresses_lookup, row_mapping)
    print("Compiled DDR Program:")
    print_payload_detail(compiled_program)
    write_payload_detail_to_file(payload=compiled_program, file_path="payload.txt")
except ParseException as e:
    print(f"Parsing Error: {e}")
