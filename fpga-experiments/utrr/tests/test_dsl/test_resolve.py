from utrr.dram.dram_address import DramAddress
from utrr.dsl.command import (
    ForCommand,
    PreCommand,
    ActCommand,
    RefCommand,
    LoopCommand,
    NopCommand,
)
from utrr.dsl.resolve import resolve_commands


def test_deep_nested_for_loop_with_large_expression_range():
    """
    DSL Equivalent:
      for i in range(10):
          for k in range(i * 59, (i + 1) * 59):
              act(bank=addresses[k].bank, row=addresses[k].row - 1)
              pre()
    """

    # Construct the nested ForCommand structure:
    for_cmd = ForCommand(
        var_name="i",
        start=0,
        end=10,  # i = 0..9
        body=[
            ForCommand(
                var_name="k",
                start="i * 59",
                end="(i + 1) * 59",
                body=[
                    ActCommand(
                        bank="addresses[k].bank",
                        row="addresses[k].row - 1",
                    ),
                    PreCommand(),
                ],
            )
        ],
    )

    # We need enough addresses so k goes up to 59*10-1 = 589
    # Let's construct them programmatically.
    # For variety, store bank = (index // 59), row = (index + 1000).
    addresses = [
        DramAddress(bank=(idx // 59), row=(1000 + idx))
        for idx in range(59 * 10)  # 0..589
    ]
    addresses_lookup = {"addresses": addresses}

    # Resolve/unroll the commands
    resolved = resolve_commands([for_cmd], addresses_lookup=addresses_lookup)

    # 1) Check total number of commands:
    #    - For each i in 0..9, we have 59 iterations of k
    #    - Each iteration yields 2 commands (ACT + PRE)
    #    - Total = 10 * 59 * 2 = 1180
    assert (
        len(resolved) == 10 * 59 * 2
    ), f"Expected {10 * 59 * 2} commands, but got {len(resolved)}"

    # 2) Check a few key expansions:

    # --- (a) First iteration: i=0, k=0 ---
    #     i=0 => k in [0..58]
    #     The first two commands should be Act(bank=?, row=?), PreCommand()
    first_act = resolved[0]
    first_pre = resolved[1]
    assert isinstance(first_act, ActCommand), "First command should be ActCommand"
    assert isinstance(first_pre, PreCommand), "Second command should be PreCommand"

    # For k=0 => addresses[0].bank = 0, addresses[0].row = 1000 => row-1 = 999
    assert first_act.bank == 0, f"Expected bank=0 for k=0, got {first_act.bank}"
    assert first_act.row == 999, f"Expected row=999 for k=0, got {first_act.row}"

    # --- (b) Still i=0, but last k in that block => k=58
    # That iteration yields commands at indices 58*2=116 and 117 in 'resolved'
    # because each k adds 2 commands.
    act_k58 = resolved[58 * 2]  # 116
    pre_k58 = resolved[58 * 2 + 1]  # 117
    assert isinstance(act_k58, ActCommand), "Should be ActCommand"
    assert isinstance(pre_k58, PreCommand), "Should be PreCommand"

    # For k=58 => addresses[58].bank=58//59=0, row=1058 => row-1=1057
    assert act_k58.bank == 0, f"Expected bank=0 for k=58, got {act_k58.bank}"
    assert act_k58.row == 1057, f"Expected row=1057 for k=58, got {act_k58.row}"

    # --- (c) Last iteration: i=9 => k goes from 531..589
    # We'll check the *very last* iteration: k=589 => final 2 commands in the list
    # i=9 block starts after i=0..8 => i=9 is the 10th block of size 59*2=118
    # The i=0 block covers indices 0..(59*2)-1 => 0..117
    # i=1 block => 118..235
    # ...
    # i=9 block => 9 * (59*2) => 9 * 118 = 1062 (start) up to 1062 + 118 - 1 = 1179 (end)
    # The final iteration => index = 1178/1179
    last_act = resolved[-2]
    last_pre = resolved[-1]
    assert isinstance(
        last_act, ActCommand
    ), "Expected second-to-last command to be ActCommand"
    assert isinstance(last_pre, PreCommand), "Expected last command to be PreCommand"

    # For i=9 => k=589 => addresses[589], bank=589//59=9, row=1589 => row-1=1588
    assert last_act.bank == 9, f"Expected bank=9 for k=589, got {last_act.bank}"
    assert last_act.row == 1588, f"Expected row=1588 for k=589, got {last_act.row}"

    # If we get here without errors, the test passes!
    print("Test passed. Resolved commands match the expected partial checks.")


def test_nested_for_loop_with_expression_range():
    """
    DSL equivalent:
    for i in range(0, 2):
        for k in range(i * 2, (i + 1) * 2):
            act(bank=addresses[k].bank, row=addresses[k].row + 10)
            pre()
    """

    # Our DSL representation:
    # Outer ForCommand (var="i", start=0, end=2)
    #   Inner ForCommand (var="k", start="i * 2", end="(i + 1) * 2")
    #     [ ActCommand(bank="addresses[k].bank", row="addresses[k].row + 10"), PreCommand() ]
    for_cmd = ForCommand(
        var_name="i",
        start=0,
        end=2,  # i in [0, 1]
        body=[
            ForCommand(
                var_name="k",
                start="i * 2",
                end="(i + 1) * 2",
                body=[
                    ActCommand(
                        bank="addresses[k].bank",
                        row="addresses[k].row + 10",
                    ),
                    PreCommand(),
                ],
            )
        ],
    )

    # Provide addresses for k = 0..3
    # i = 0 => k = 0,1
    # i = 1 => k = 2,3
    addresses = [
        DramAddress(bank=0, row=0),  # k=0
        DramAddress(bank=0, row=1),  # k=1
        DramAddress(bank=1, row=10),  # k=2
        DramAddress(bank=1, row=11),  # k=3
    ]

    addresses_lookup = {
        "addresses": addresses,
    }

    # When we resolve the commands, all loops expand fully
    resolved = resolve_commands([for_cmd], addresses_lookup=addresses_lookup)

    # Let's build the expected expansion:

    # i=0 => k in [0,1]
    #   ActCommand(bank=addresses[0].bank=0, row=0+10=10), PreCommand()
    #   ActCommand(bank=addresses[1].bank=0, row=1+10=11), PreCommand()
    #
    # i=1 => k in [2,3]
    #   ActCommand(bank=addresses[2].bank=1, row=10+10=20), PreCommand()
    #   ActCommand(bank=addresses[3].bank=1, row=11+10=21), PreCommand()

    expected = [
        # i=0, k=0
        ActCommand(bank=0, row=10),
        PreCommand(),
        # i=0, k=1
        ActCommand(bank=0, row=11),
        PreCommand(),
        # i=1, k=2
        ActCommand(bank=1, row=20),
        PreCommand(),
        # i=1, k=3
        ActCommand(bank=1, row=21),
        PreCommand(),
    ]

    assert resolved == expected, f"\nResolved:\n{resolved}\n\nExpected:\n{expected}"


def test_for_loop_resolve():
    """
    For i=0..2:
      - PreCommand()
      - ActCommand(bank="addresses[i].bank", row="addresses[i].row + 1")
      - RefCommand()
    """

    for_cmd = ForCommand(
        var_name="i",
        start=0,
        end=2,
        body=[
            PreCommand(),
            ActCommand(
                bank="addresses[i].bank",
                row="addresses[i].row + 1",
            ),
            RefCommand(),
        ],
    )

    addresses = [
        DramAddress(bank=0, row=10),  # i=0
        DramAddress(bank=0, row=20),  # i=1
    ]

    addresses_lookup = {
        "addresses": addresses,
    }
    resolved = resolve_commands([for_cmd], addresses_lookup)

    expected = [
        PreCommand(),
        ActCommand(bank=0, row=11),
        RefCommand(),
        PreCommand(),
        ActCommand(bank=0, row=21),
        RefCommand(),
    ]

    assert (
        resolved == expected
    ), f"\nResolved value:\n{resolved}\n\nExpected:\n{expected}"


def test_outer_loop_inner_for_resolved():
    """
    LoopCommand(count=2) wrapping a For i=0..2:
      - PreCommand()
      - ActCommand(bank="addresses[i].bank", row="addresses[i].row - 1")
      - RefCommand()
    """

    loop_cmd = LoopCommand(
        count=2,
        body=[
            ForCommand(
                var_name="i",
                start=0,
                end=2,
                body=[
                    PreCommand(),
                    ActCommand(
                        bank="addresses[i].bank",
                        row="addresses[i].row - 1",
                    ),
                    RefCommand(),
                ],
            )
        ],
    )

    addresses = [
        DramAddress(bank=0, row=10),  # i=0
        DramAddress(bank=0, row=20),  # i=1
    ]

    addresses_lookup = {
        "addresses": addresses,
    }

    resolved = resolve_commands([loop_cmd], addresses_lookup)

    expected = [
        LoopCommand(
            count=2,
            body=[
                PreCommand(),
                ActCommand(bank=0, row=9),
                RefCommand(),
                PreCommand(),
                ActCommand(bank=0, row=19),
                RefCommand(),
            ],
        )
    ]

    assert (
        resolved == expected
    ), f"\nResolved value:\n{resolved}\n\nExpected:\n{expected}"


def test_outer_for_inner_loop():
    """
    For i=0..2:
      - PreCommand()
      - LoopCommand(count=2, body=[ActCommand(bank="addresses[i].bank", row="addresses[i].row + 1"), RefCommand()])
    """

    for_cmd = ForCommand(
        var_name="i",
        start=0,
        end=2,
        body=[
            PreCommand(),
            LoopCommand(
                count=2,
                body=[
                    ActCommand(
                        bank="addresses[i].bank",
                        row="addresses[i].row + 1",
                    ),
                    RefCommand(),
                ],
            ),
        ],
    )

    addresses = [
        DramAddress(bank=0, row=10),  # i=0
        DramAddress(bank=0, row=20),  # i=1
    ]

    addresses_lookup = {
        "addresses": addresses,
    }

    resolved = resolve_commands([for_cmd], addresses_lookup=addresses_lookup)

    expected = [
        PreCommand(),
        LoopCommand(
            count=2,
            body=[
                ActCommand(bank=0, row=11),
                RefCommand(),
            ],
        ),
        PreCommand(),
        LoopCommand(
            count=2,
            body=[
                ActCommand(bank=0, row=21),
                RefCommand(),
            ],
        ),
    ]

    assert (
        resolved == expected
    ), f"\nResolved value:\n{resolved}\n\nExpected:\n{expected}"


def test_for_loop_with_dummy_addresses():
    """
    For i=0..2:
      - PreCommand()
      - LoopCommand(count=2, body=[ActCommand(bank="decoys[i].bank", row="decoys[i].row + 1"), RefCommand()])
    """

    for_cmd = ForCommand(
        var_name="i",
        start=0,
        end=2,
        body=[
            PreCommand(),
            LoopCommand(
                count=2,
                body=[
                    ActCommand(
                        bank="decoys[i].bank",
                        row="decoys[i].row + 1",
                    ),
                    RefCommand(),
                ],
            ),
        ],
    )

    decoys = [
        DramAddress(bank=-1, row=100),  # i=0
        DramAddress(bank=-1, row=200),  # i=1
    ]

    addresses_lookup = {
        "decoys": decoys,
    }

    resolved = resolve_commands([for_cmd], addresses_lookup=addresses_lookup)

    expected = [
        PreCommand(),
        LoopCommand(
            count=2,
            body=[
                ActCommand(bank=-1, row=101),
                RefCommand(),
            ],
        ),
        PreCommand(),
        LoopCommand(
            count=2,
            body=[
                ActCommand(bank=-1, row=201),
                RefCommand(),
            ],
        ),
    ]

    assert (
        resolved == expected
    ), f"\nResolved value:\n{resolved}\n\nExpected:\n{expected}"


def test_for_loop_with_mixed_addresses():
    """
    For i=0..2:
      - PreCommand()
      - ActCommand(bank="addresses[i].bank", row="addresses[i].row + 1")
      - ActCommand(bank="decoys[i].bank", row="decoys[i].row + 2")
      - RefCommand()
      - NopCommand(count=5)
    """

    for_cmd = ForCommand(
        var_name="i",
        start=0,
        end=2,  # i = 0,1
        body=[
            PreCommand(),
            ActCommand(
                bank="addresses[i].bank",
                row="addresses[i].row + 1",
            ),
            ActCommand(
                bank="decoys[i].bank",
                row="decoys[i].row + 2",
            ),
            RefCommand(),
            NopCommand(count=5),
        ],
    )

    real_addresses = [
        DramAddress(bank=0, row=10),  # i=0
        DramAddress(bank=0, row=20),  # i=1
    ]

    decoys = [
        DramAddress(bank=-1, row=100),  # i=0
        DramAddress(bank=-1, row=200),  # i=1
    ]

    addresses_lookup = {
        "addresses": real_addresses,
        "decoys": decoys,
    }

    resolved = resolve_commands([for_cmd], addresses_lookup=addresses_lookup)

    expected_for_i0 = [
        PreCommand(),
        ActCommand(bank=0, row=11),
        ActCommand(bank=-1, row=102),
        RefCommand(),
        NopCommand(count=5),
    ]

    expected_for_i1 = [
        PreCommand(),
        ActCommand(bank=0, row=21),
        ActCommand(bank=-1, row=202),
        RefCommand(),
        NopCommand(count=5),
    ]

    expected = expected_for_i0 + expected_for_i1

    assert (
        resolved == expected
    ), f"\nResolved value:\n{resolved}\n\nExpected:\n{expected}"
