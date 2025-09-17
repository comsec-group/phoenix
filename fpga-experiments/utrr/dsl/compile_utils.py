from typing import List

from rowhammer_tester.gateware.payload_executor import Encoder, OpCode
from rowhammer_tester.scripts.litedram_settings import TimingSettings


def create_prologue(
    encoder: Encoder, timing: TimingSettings
) -> List[Encoder.Instruction]:
    return [
        encoder.Instruction(OpCode.NOOP, timeslice=timing.tREFI),
        encoder.Instruction(OpCode.NOOP, timeslice=timing.tREFI),
        encoder.Instruction(OpCode.NOOP, timeslice=timing.tREFI),
        encoder.Instruction(
            OpCode.PRE,
            timeslice=timing.tRP,
            address=encoder.address(col=1 << 10, rank=0),
        ),  # precharge all
        encoder.Instruction(OpCode.NOOP, timeslice=1),
        encoder.Instruction(OpCode.NOOP, timeslice=1),
        encoder.Instruction(OpCode.NOOP, timeslice=1),
    ]


def create_epilogue(encoder: Encoder) -> List[Encoder.Instruction]:
    return [encoder.Instruction(OpCode.NOOP, timeslice=0)]
