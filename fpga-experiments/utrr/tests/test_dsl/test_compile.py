from rowhammer_tester.gateware.payload_executor import Encoder, OpCode
from rowhammer_tester.scripts.litedram_settings import LiteDramSettings
from rowhammer_tester.scripts.utils import get_generated_file
from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_controller import print_payload_detail
from utrr.dram.dram_row_mapping import DirectDramRowMapping
from utrr.dram.utils import select_random_excluding_addresses
from utrr.dsl.command import LoopCommand, PreCommand
from utrr.dsl.compile import compile_program, compile_code

# 1) Setup environment (encoder, timing, mapping)
json_file = get_generated_file("litedram_settings.json")
settings = LiteDramSettings.from_json_file(json_file)
timing = settings.timing
encoder = Encoder(
    bankbits=settings.geom.bankbits,
    nranks=settings.phy.nranks,
)
dram_row_mapping = DirectDramRowMapping()


# --------------------------------------------------
# Actual test
# --------------------------------------------------
def test_loop_splitting_body_emission():
    """
    Tests that a LoopCommand(count=5000) with a hardware limit of 4000
    yields multiple copies of the body (PRE), each followed by a LOOP
    whose 'count' does not exceed 0xf9f (3999).
    We specifically want:
      1) PRE
      2) LOOP count=0xf9f
      3) PRE
      4) LOOP count=0x3e7
    """

    loop_cmd = LoopCommand(count=5000, body=[PreCommand()])

    compiled_instructions = compile_program(
        commands=[loop_cmd],
        encoder=encoder,
        timing=timing,
        dram_row_mapping=dram_row_mapping,
    )

    print()
    print_payload_detail(compiled_instructions)

    # 4) We expect EXACTLY 4 instructions in the final result:
    #    [0] PRE
    #    [1] LOOP with count=0xf9f (3999)
    #    [2] PRE
    #    [3] LOOP with count=0x3e7 (999)
    assert (
        len(compiled_instructions) == 4
    ), f"Expected 4 instructions, got {len(compiled_instructions)}: {compiled_instructions}"

    instr0, instr1, instr2, instr3 = compiled_instructions

    # Check #0: PRE
    assert instr0.op_code == OpCode.PRE, "Instruction #0 should be PRE."
    # timeslice or address checks if needed:
    # assert instr0.timeslice == 0x4
    # assert instr0.address == 0x10000

    # Check #1: LOOP with count=0xf9f (3999)
    assert instr1.op_code == OpCode.LOOP, "Instruction #1 should be LOOP."
    assert (
        instr1.count == 0xF9F
    ), f"LOOP #1 'count' should be 0xf9f (3999), got {instr1.count}"

    # Check #2: PRE again
    assert instr2.op_code == OpCode.PRE, "Instruction #2 should be PRE."

    # Check #3: LOOP with count=0x3e7 (998)
    assert instr3.op_code == OpCode.LOOP, "Instruction #3 should be LOOP."
    assert (
        instr3.count == 0x3E7
    ), f"LOOP #2 'count' should be 0x3e6 (998), got {instr3.count}"

    # If you'd also like to confirm timeslice or jump, do so:
    # assert instr1.jump == (whatever the compiler sets)
    # ...

    print("Test passed with 4 instructions: PRE, LOOP(0xf9f), PRE, LOOP(0x3e6)")


def test_double_sided_hammer_with_ref():
    code = """
for _ in range(20000):
    act(bank=addresses[0].bank, row=addresses[0].row - 1)
    pre()
    act(bank=addresses[0].bank, row=addresses[0].row + 1)
    pre()
    nop(cycles=7)

ref()
nop(cycles=200)

for _ in range(20000):
    act(bank=addresses[0].bank, row=addresses[0].row - 1)
    pre()
    act(bank=addresses[0].bank, row=addresses[0].row + 1)
    pre()
    nop(cycles=7)

    """
    addresses = [DramAddress(bank=0, row=1000)]
    decoys = select_random_excluding_addresses(
        addresses_exclude=addresses,
        count=100,
        min_distance=100,
    )
    addresses_lookup = {
        "addresses": addresses,
        "decoys": decoys,
    }
    payload = compile_code(code, addresses_lookup, dram_row_mapping)

    print_payload_detail(payload)
