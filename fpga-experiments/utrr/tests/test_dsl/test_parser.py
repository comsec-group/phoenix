import pytest
from pyparsing import ParseException

from utrr.dsl.command import (
    PreCommand,
    ActCommand,
    RefCommand,
    ForCommand,
    LoopCommand,
    NopCommand,
)
from utrr.dsl.parse import parse_commands


def test_parse_code_with_local_vars():
    code = """
some_var = 5
some_offset = 10

for i in range(2, some_var + 3):
    act(bank=addresses[i].bank, row=addresses[i].row + some_offset - 1)
    nop(cycles=3)

    for k in range(i * some_offset, (i + 1) * some_offset):
        act(bank=addresses[k].bank, row=addresses[k].row + i + some_var)
        pre()
    """

    result = parse_commands(code=code)
    print(result)

    # ---------------------------------------------------------
    # 0) Verify that we have one top-level command after parsing:
    #    The parser might skip or ignore top-level assignments
    #    if you haven't implemented compile-time var support yet.
    #    We'll assume that those assignments do not appear as commands in `result`.
    # ---------------------------------------------------------
    assert (
        len(result) == 1
    ), f"Expected exactly one top-level command (the 'for i' loop), got {len(result)}"
    for_cmd_i = result[0]
    assert isinstance(
        for_cmd_i, ForCommand
    ), "Expected a ForCommand object for `i` loop"

    # ---------------------------------------------------------
    # 1) Check outer loop: for i in range(2, some_var + 3)
    # ---------------------------------------------------------
    assert for_cmd_i.var_name == "i", "Loop variable should be `i`"
    assert for_cmd_i.start == 2, "Start of `i` loop should be 2"
    # The end should be a string, because `some_var + 3` is not a literal
    assert (
        for_cmd_i.end == "some_var + 3"
    ), "End of `i` loop should be `some_var + 3` as a string expression"

    body_i = for_cmd_i.body
    # We expect the body of the `i` loop to have exactly 3 commands:
    #   1) ActCommand (bank=..., row=...)
    #   2) NopCommand(cycles=3)
    #   3) Another ForCommand for `k`
    assert (
        len(body_i) == 3
    ), f"Expected 3 commands in the `i` loop body, got {len(body_i)}"

    # (1) ActCommand
    act_cmd_1 = body_i[0]
    assert isinstance(act_cmd_1, ActCommand), "First command should be ActCommand"
    # bank = addresses[i].bank
    assert act_cmd_1.bank == "addresses[i].bank"
    # row = addresses[i].row + some_offset - 1
    assert act_cmd_1.row == "addresses[i].row + some_offset - 1"

    # (2) NopCommand
    nop_cmd = body_i[1]
    assert isinstance(nop_cmd, NopCommand), "Second command should be NopCommand"
    assert nop_cmd.count == 3, "Expected nop(cycles=3)"

    # (3) Inner ForCommand for `k`
    for_cmd_k = body_i[2]
    assert isinstance(
        for_cmd_k, ForCommand
    ), "Third command should be a ForCommand for `k`"

    # ---------------------------------------------------------
    # 2) Check inner loop: for k in range(i * some_offset, (i + 1) * some_offset):
    # ---------------------------------------------------------
    assert for_cmd_k.var_name == "k", "Loop variable should be `k`"
    assert for_cmd_k.start == "i * some_offset", "start should be `i * some_offset`"
    assert (
        for_cmd_k.end == "(i + 1) * some_offset"
    ), "end should be `(i + 1) * some_offset`"

    body_k = for_cmd_k.body
    # We expect the body of the `k` loop to be [ActCommand, PreCommand]
    assert (
        len(body_k) == 2
    ), f"Expected 2 commands in the `k` loop body, got {len(body_k)}"

    # (1) ActCommand
    act_cmd_2 = body_k[0]
    assert isinstance(
        act_cmd_2, ActCommand
    ), "First command in `k` loop should be ActCommand"
    # bank = addresses[k].bank
    assert act_cmd_2.bank == "addresses[k].bank"
    # row = addresses[k].row + i + some_var
    assert act_cmd_2.row == "addresses[k].row + i + some_var"

    # (2) PreCommand
    pre_cmd_2 = body_k[1]
    assert isinstance(
        pre_cmd_2, PreCommand
    ), "Second command in `k` loop should be PreCommand"


def test_parse_nested_loop():
    code = """
for i in range(10):
    for k in range(i * 59, (i+1) * 59):
        act(bank=addresses[k].bank, row=addresses[k].row - 1)
        pre()
    """
    result = parse_commands(code=code)
    print(result)

    # We expect exactly one top-level command: a ForCommand for `i` in range(0, 10)
    assert len(result) == 1, "Expected exactly one top-level command"
    for_cmd_i = result[0]
    assert isinstance(for_cmd_i, ForCommand), "Expected a ForCommand object for `i`"

    # Check loop variable, start, end for `i`
    assert for_cmd_i.var_name == "i", "Loop variable should be `i`"
    assert for_cmd_i.start == 0, "Start of `i` loop should be 0"
    assert for_cmd_i.end == 10, "End of `i` loop should be 10"

    # The body of the `i` loop should contain exactly one ForCommand (the `k` loop)
    body_i = for_cmd_i.body
    assert len(body_i) == 1, "Expected exactly one command in the `i` loop body"
    for_cmd_k = body_i[0]
    assert isinstance(for_cmd_k, ForCommand), "Expected a ForCommand object for `k`"

    # Check loop variable, start, end for `k`
    assert for_cmd_k.var_name == "k", "Loop variable should be `k`"
    assert for_cmd_k.start == "i * 59", "Start of `k` loop should be `i * 59`"
    assert for_cmd_k.end == "(i + 1) * 59", "End of `k` loop should be `(i + 1) * 59`"

    # The body of the `k` loop should contain [ACT, PRE]
    body_k = for_cmd_k.body
    assert len(body_k) == 2, "Expected exactly two commands in the `k` loop body"

    # 1) ACT
    act_cmd = body_k[0]
    assert isinstance(act_cmd, ActCommand), "First command in `k` loop should be ACT"
    assert act_cmd.bank == "addresses[k].bank"
    assert act_cmd.row == "addresses[k].row - 1"

    # 2) PRE
    pre_cmd = body_k[1]
    assert isinstance(pre_cmd, PreCommand), "Second command in `k` loop should be PRE"


def test_parse_for_loop_with_variable():
    code = """
for i in range(0, 2):
    pre()
    act(bank=addresses[i].bank, row=addresses[i].row + 1)
    ref()
"""
    result = parse_commands(code=code)
    print(result)

    # There should be exactly one top-level command: a ForCommand
    assert len(result) == 1, "Expected exactly one top-level command"
    for_cmd = result[0]
    assert isinstance(for_cmd, ForCommand), "Expected a ForCommand object"

    # Check loop variable, start, end
    assert for_cmd.var_name == "i", "Loop variable should be 'i'"
    assert for_cmd.start == 0, "Start should be 0"
    assert for_cmd.end == 2, "End should be 2"

    # Body should be [PRE, ACT, REF]
    body = for_cmd.body
    assert len(body) == 3, "Expected exactly three commands in the FOR body"

    # 1) PRE
    assert isinstance(body[0], PreCommand), "First command should be PRE"
    # 2) ACT $i+1
    act_cmd = body[1]
    assert isinstance(act_cmd, ActCommand), "Second command should be ACT"
    assert act_cmd.bank == "addresses[i].bank"
    assert act_cmd.row == "addresses[i].row + 1"
    # # 3) REF
    assert isinstance(body[2], RefCommand), "Third command should be REF"


def test_parse_nested_loop_and_for():
    """
    Verifies the DSL parser correctly parses a nested structure:
    LOOP ... FOR ... (without unrolling).
    Again, we only verify the parser output structure.
    """
    code = """
for _ in range(2):
    for i in range(0, 2):
        pre()
        act(bank=addresses[i].bank, row=addresses[i]+1)
        ref()
"""
    try:
        parsed = parse_commands(code=code)
        # We expect exactly one top-level command: LoopCommand(count=2, body=[ForCommand(...)])
        assert len(parsed) == 1, "Expected a single top-level LOOP command"
        outer_loop_cmd = parsed[0]
        assert isinstance(
            outer_loop_cmd, LoopCommand
        ), "The top-level command should be LoopCommand"
        assert outer_loop_cmd.count == 2, "Loop count should be 2"

        # Inside its body, we expect exactly one ForCommand
        loop_body = outer_loop_cmd.body
        assert (
            len(loop_body) == 1
        ), "Expected the LOOP to contain exactly one command (the FOR)"
        inner_for = loop_body[0]
        assert isinstance(
            inner_for, ForCommand
        ), "Inside the LOOP, we should have a ForCommand"

        # Check the FOR details
        assert inner_for.var_name == "i"
        assert inner_for.start == 0
        assert inner_for.end == 2

        # The FOR body should be [PRE, ACT, REF]
        for_body = inner_for.body
        assert len(for_body) == 3, "Expected three commands in the FOR body"
        assert isinstance(for_body[0], PreCommand)
        assert isinstance(for_body[1], ActCommand)
        assert isinstance(for_body[2], RefCommand)
    except ParseException as pe:
        pytest.fail(f"Parsing failed: {pe}")


def test_parse_for_loop_with_dummy_variable():
    """
    Verifies the DSL parser correctly handles an '@' dummy-address reference
    within a FOR loop. This test still only covers parsing, not resolution.
    """
    code = """
for i in range(5, 7):
    act(bank=decoys[i].bank, row=decoys[i].row + 2)
"""

    try:
        parsed = parse_commands(code=code)
        # We should have exactly one top-level command (FOR)
        assert len(parsed) == 1, "Expected exactly one top-level command"
        for_cmd = parsed[0]
        assert isinstance(for_cmd, ForCommand), "Expected a ForCommand"

        # Check loop variable, start, end
        assert for_cmd.var_name == "i", "Loop variable should be 'i'"
        assert for_cmd.start == 5, "Start should be 5"
        assert for_cmd.end == 7, "End should be 7"

        # Body should have a single command: ACT @j+2
        body = for_cmd.body
        assert len(body) == 1, "Expected exactly one command in the FOR body"
        act_cmd = body[0]
        assert isinstance(act_cmd, ActCommand), "Command should be ACT"

        assert act_cmd.bank == "decoys[i].bank"
        assert act_cmd.row == "decoys[i].row + 2"
    except ParseException as pe:
        pytest.fail(f"Parsing failed: {pe}")


def test_parse_nop_command():
    """
    Ensures the DSL parser correctly parses a NOP command with an integer argument.
    """
    code = """
nop(cycles=5)
"""

    try:
        parsed = parse_commands(code=code)
        # There should be exactly one top-level command: a NopCommand
        assert len(parsed) == 1, "Expected exactly one top-level command"
        nop_cmd = parsed[0]
        assert isinstance(nop_cmd, NopCommand), "Expected a NopCommand object"
        assert nop_cmd.count == 5, "NOP count should be 5"

    except ParseException as pe:
        pytest.fail(f"Parsing failed: {pe}")
