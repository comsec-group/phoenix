import ast
from typing import List

from utrr.dsl.command import (
    NopCommand,
    ActCommand,
    PreCommand,
    RefCommand,
    LoopCommand,
    ForCommand,
    Command,
)


class CommandParsingError(Exception):
    """Custom exception for command parsing errors."""

    pass


def parse_command(node):
    """Parses single commands like nop, act, pre, ref."""
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        func = node.value.func
        # Safely handle the function name in various AST forms:
        if isinstance(func, ast.Name):
            func_name = func.id
        else:
            return None

        if func_name == "nop":
            args = {kw.arg: kw.value.n for kw in node.value.keywords}
            return NopCommand(count=args.get("cycles", 0))
        elif func_name == "act":
            args = {kw.arg: ast.unparse(kw.value) for kw in node.value.keywords}
            return ActCommand(bank=args.get("bank", ""), row=args.get("row", ""))
        elif func_name == "pre":
            return PreCommand()
        elif func_name == "ref":
            return RefCommand()
    return None


def parse_range_arg(arg):
    """
    Convert a range() argument into either a plain integer (if constant)
    or a string representing the expression (if non-constant).
    """
    # Python 3.8+ style
    if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
        return arg.value
    # Python 3.7 and older might use ast.Num instead of ast.Constant
    elif isinstance(arg, ast.Num):
        return arg.n
    else:
        # For something like (i*59), ast.unparse(...) yields "i * 59".
        return ast.unparse(arg)


def parse_body(body):
    """Recursively parse a block (list of statements) into DSL commands."""
    commands = []
    for stmt in body:
        if isinstance(stmt, ast.For):
            # We're expecting stmt.iter to be something like range(...)
            if (
                isinstance(stmt.iter, ast.Call)
                and isinstance(stmt.iter.func, ast.Name)
                and stmt.iter.func.id == "range"
            ):
                loop_range_args = stmt.iter.args

                # The loop variable
                loop_var = stmt.target.id if isinstance(stmt.target, ast.Name) else None

                if len(loop_range_args) == 1:
                    # range(N)
                    start = 0
                    end = parse_range_arg(loop_range_args[0])
                elif len(loop_range_args) == 2:
                    # range(start, end)
                    start = parse_range_arg(loop_range_args[0])
                    end = parse_range_arg(loop_range_args[1])
                else:
                    raise ValueError(
                        f"Unsupported range format: range(...) has {len(loop_range_args)} args"
                    )

                parsed_body = parse_body(stmt.body)

                # If the loop variable is "_" we treat it like a LoopCommand
                if loop_var == "_":
                    # If start or end are not integers, you have to decide how to handle that
                    # For example, if they are symbolic expressions, you might handle them differently
                    if not (isinstance(start, int) and isinstance(end, int)):
                        raise ValueError(
                            "LoopCommand with '_' only supports numeric range."
                        )
                    commands.append(LoopCommand(count=end - start, body=parsed_body))
                else:
                    # Build a ForCommand with possibly symbolic start/end
                    commands.append(
                        ForCommand(
                            var_name=loop_var, start=start, end=end, body=parsed_body
                        )
                    )
            else:
                raise ValueError(
                    f"For loop is not a range(...): {ast.unparse(stmt.iter)}"
                )
        else:
            cmd = parse_command(stmt)
            if cmd:
                commands.append(cmd)

    return commands


def parse_commands(code: str) -> List[Command]:
    try:
        tree = ast.parse(code)
        return parse_body(tree.body)
    except SyntaxError as e:
        raise CommandParsingError(f"Syntax error while parsing: {e}") from e


if __name__ == "__main__":
    code = """
for k in range(128):
    for i in range(10):
        nop(cycles=60)

        for _ in range(60):
            act(bank=addresses[i].bank, row=addresses[i].row + 1)
            pre()

    ref()

    for i in range(10, 20):
        nop(cycles=60)

        for _ in range(60):
            act(bank=addresses[i].bank, row=addresses[i].row + 1)
            pre()
    """
    parsed_commands = parse_commands(code)
    for cmd in parsed_commands:
        print(cmd)
