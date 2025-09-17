from typing import List, Optional, Dict, Union

from utrr.dram.dram_address import DramAddress
from utrr.dsl.command import (
    Command,
    PreCommand,
    RefCommand,
    ActCommand,
    LoopCommand,
    ForCommand,
    NopCommand,
)
from utrr.dsl.resolve_act import ExpressionResolver


def resolve_act(
    act_cmd: ActCommand,
    addresses_lookup: Dict[str, List[DramAddress]],
    loop_vars: Optional[Dict[str, int]] = None,
) -> DramAddress:
    resolver = ExpressionResolver(addresses_lookup, loop_vars)

    bank_val = resolver.evaluate(act_cmd.bank)
    row_val = resolver.evaluate(act_cmd.row)

    return DramAddress(bank=bank_val, row=row_val)


def resolve_commands(
    commands: List[Command],
    addresses_lookup: Dict[str, List[DramAddress]],
    loop_vars: Optional[Dict[str, int]] = None,
) -> List[Command]:
    """
    Resolves all commands in the parsed DSL, including unrolling ForCommands.

    - PreCommand, RefCommand, NopCommand remain as-is.
    - ActCommand expressions get resolved into DramAddresses.
    - LoopCommand body is recursively resolved (but we do NOT unroll that).
    - ForCommand is unrolled from start..end, each iteration resolving the body.

    Now also supports expression-based start/end (e.g., "i * 59").
    """
    if loop_vars is None:
        loop_vars = {}

    resolved = []

    for cmd in commands:
        if (
            isinstance(cmd, PreCommand)
            or isinstance(cmd, RefCommand)
            or isinstance(cmd, NopCommand)
        ):
            # These commands don't have expressions to resolve
            resolved.append(cmd)

        elif isinstance(cmd, ActCommand):
            address = resolve_act(
                act_cmd=cmd, addresses_lookup=addresses_lookup, loop_vars=loop_vars
            )
            resolved.append(ActCommand(bank=address.bank, row=address.row))

        elif isinstance(cmd, LoopCommand):
            # Recursively resolve the body, but do not unroll
            resolved_body = resolve_commands(cmd.body, addresses_lookup, loop_vars)
            resolved.append(LoopCommand(count=cmd.count, body=resolved_body))

        elif isinstance(cmd, ForCommand):
            # Evaluate possible expressions for start and end
            start_val = evaluate_expression_or_int(
                cmd.start, addresses_lookup, loop_vars
            )
            end_val = evaluate_expression_or_int(cmd.end, addresses_lookup, loop_vars)

            # UNROLL the for-loop from start_val to end_val
            for i in range(start_val, end_val):
                nested_loop_vars = dict(loop_vars)
                nested_loop_vars[cmd.var_name] = i

                resolved_body = resolve_commands(
                    cmd.body, addresses_lookup, nested_loop_vars
                )

                resolved.extend(resolved_body)
        else:
            raise TypeError(f"Unknown command type: {type(cmd).__name__}")

    return resolved


def evaluate_expression_or_int(
    value: Union[int, str],
    addresses_lookup: Dict[str, List[DramAddress]],
    loop_vars: Dict[str, int],
) -> int:
    """
    Helper function that:
      - If 'value' is already an int, returns it directly.
      - If 'value' is a string, evaluates it as an expression using ExpressionResolver.
      - Ensures the result is an integer (raises TypeError otherwise).
    """
    if isinstance(value, int):
        return value
    elif isinstance(value, str):
        resolver = ExpressionResolver(addresses_lookup, loop_vars)
        result = resolver.evaluate(value)
        if not isinstance(result, int):
            raise TypeError(
                f"ForCommand range expression must evaluate to an int, got '{result}' "
                f"(type={type(result)}) for expression '{value}'"
            )
        return result
    else:
        raise TypeError(
            f"ForCommand range start/end must be int or str, got {value} (type={type(value)})"
        )
