from typing import List, Dict

from rowhammer_tester.gateware.payload_executor import Encoder, OpCode
from rowhammer_tester.scripts.litedram_settings import TimingSettings, LiteDramSettings
from rowhammer_tester.scripts.utils import get_generated_file
from utrr.dram.dram_address import DramAddress
from utrr.dram.dram_row_mapping import DramRowMapping
from utrr.dsl.command import (
    Command,
    PreCommand,
    RefCommand,
    ActCommand,
    LoopCommand,
    NopCommand,
)
from utrr.dsl.compile_utils import create_prologue, create_epilogue
from utrr.dsl.parse import parse_commands
from utrr.dsl.resolve import resolve_commands
from utrr.dsl.unroll_program import unroll_program

MAX_LOOP_COUNT = 4000  # or whatever the hardware limit is


def compile_code(
    code: str,
    addresses_lookup: Dict[str, List[DramAddress]],
    dram_row_mapping: DramRowMapping,
) -> List[Encoder.Instruction]:
    ast_code = parse_commands(code=code)

    resolved_program = resolve_commands(ast_code, addresses_lookup)
    unrolled_program = unroll_program(resolved_program)

    # Get LiteDRAM settings and encoder
    json_file = get_generated_file("litedram_settings.json")
    settings = LiteDramSettings.from_json_file(json_file)
    timing = settings.timing
    encoder = Encoder(
        bankbits=settings.geom.bankbits,
        nranks=settings.phy.nranks,
    )

    # Compile the unrolled program into DDR instructions
    prologue = create_prologue(encoder=encoder, timing=timing)
    main_program = compile_program(
        commands=unrolled_program,
        encoder=encoder,
        timing=timing,
        dram_row_mapping=dram_row_mapping,
    )
    epilogue = create_epilogue(encoder=encoder)

    return prologue + main_program + epilogue


def compile_program(
    commands: List[Command],
    encoder: Encoder,
    timing: TimingSettings,
    dram_row_mapping: DramRowMapping,
) -> List[Encoder.Instruction]:
    """
    Compiles a resolved program into the target low-level language.

    Args:
        commands: A list of resolved DSL commands.
        encoder: An encoder instance for generating instructions.
        timing: Timing parameters for the instructions.
        dram_row_mapping: Internal DRAM row mapping

    Returns:
        A list of low-level instructions.
    """
    compiled = []

    def compile_commands(
        cmds: List[Command], row_mapping: DramRowMapping, loop_stack=None
    ):
        if loop_stack is None:
            loop_stack = []
        for cmd in cmds:
            if isinstance(cmd, PreCommand):
                # PRE
                compiled.append(
                    encoder.Instruction(
                        OpCode.PRE,
                        timeslice=timing.tRP,
                        address=encoder.address(col=1 << 10, rank=0),
                    )
                )
            elif isinstance(cmd, RefCommand):
                # REF
                compiled.append(encoder.Instruction(OpCode.REF, timeslice=1))
                compiled.append(
                    encoder.Instruction(OpCode.NOOP, timeslice=timing.tRFC - 1)
                )
            elif isinstance(cmd, NopCommand):
                if cmd.count <= 0:
                    raise ValueError(
                        f"NOP command requires a count > 0, got {cmd.count}"
                    )
                compiled.append(encoder.Instruction(OpCode.NOOP, timeslice=cmd.count))

            elif isinstance(cmd, ActCommand):
                # ACT
                bank = cmd.bank
                row = cmd.row
                logical_address_row = row_mapping.physical_to_logical(row)
                compiled.append(
                    encoder.Instruction(
                        OpCode.ACT,
                        timeslice=timing.tRAS,
                        address=encoder.address(
                            bank=bank, row=logical_address_row, rank=0
                        ),
                    )
                )
            elif isinstance(cmd, LoopCommand):
                # We handle the entire cmd.count by chunking it into blocks <= MAX_LOOP_COUNT.
                times_left = cmd.count
                while times_left > 0:
                    chunk = min(times_left, MAX_LOOP_COUNT)

                    # 1) Compile the body instructions for this chunk
                    loop_start_index = len(compiled)
                    compile_commands(
                        cmd.body, row_mapping, loop_stack + [loop_start_index]
                    )
                    loop_size = len(compiled) - loop_start_index

                    # 2) If chunk > 1, append a LOOP instruction
                    #    "count = chunk - 1" means: total chunk runs = chunk
                    if chunk > 1:
                        compiled.append(
                            encoder.Instruction(
                                op_code=OpCode.LOOP, jump=loop_size, count=chunk - 1
                            )
                        )
                    times_left -= chunk

    compile_commands(cmds=commands, row_mapping=dram_row_mapping)
    return compiled
