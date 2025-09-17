from typing import List

from utrr.dsl.command import Command, LoopCommand


def unroll_program(commands: List[Command]) -> List[Command]:
    """
    Unrolls the inner loops while leaving the outermost loops intact.

    Args:
        commands: A list of commands to process.

    Returns:
        A program with inner loops unrolled.
    """
    result = []
    for cmd in commands:
        if isinstance(cmd, LoopCommand):
            # Leave the outermost loop rolled, but unroll all inner loops in its body
            unrolled_body = fully_expand_loops(unroll_inner_loops(cmd.body))
            result.append(LoopCommand(count=cmd.count, body=unrolled_body))
        else:
            result.append(cmd)
    return result


def fully_expand_loops(commands: List[Command]) -> List[Command]:
    """
    Expands all loops into their fully unrolled bodies.

    Args:
        commands: A list of commands to process.

    Returns:
        A fully unrolled list of commands.
    """
    expanded = []
    for cmd in commands:
        if isinstance(cmd, LoopCommand):
            for _ in range(cmd.count):
                expanded.extend(fully_expand_loops(cmd.body))
        else:
            expanded.append(cmd)
    return expanded


def unroll_inner_loops(commands: List[Command]) -> List[Command]:
    """
    Unrolls all inner loops in the given command list, leaving only the outermost loops rolled.

    Args:
        commands: A list of commands to process.

    Returns:
        A list of commands with inner loops unrolled.
    """
    unrolled = []
    for cmd in commands:
        if isinstance(cmd, LoopCommand):
            # Unroll all inner loops within this loop
            unrolled_body = unroll_inner_loops(cmd.body)
            unrolled.append(LoopCommand(count=cmd.count, body=unrolled_body))
        elif isinstance(cmd, Command):
            unrolled.append(cmd)
    return unrolled
