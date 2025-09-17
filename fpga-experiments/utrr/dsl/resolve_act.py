import ast
import operator
from typing import Any, Dict, List

from utrr.dram.dram_address import DramAddress

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.USub: operator.neg,
}


class ExpressionResolver(ast.NodeVisitor):
    def __init__(
        self, addresses_dict: Dict[str, List[DramAddress]], loop_vars: Dict[str, int]
    ):
        """
        :param addresses_dict: e.g. {"A": [DramAddress(...), ...], "B": [...]}
        :param loop_vars: e.g. {"i": 0}
        """
        self.addresses = addresses_dict
        self.loop_vars = loop_vars

    def evaluate(self, expression: str) -> Any:
        tree = ast.parse(expression, mode="eval")
        return self.visit(tree.body)

    # -------------------------
    # Core Visit Methods
    # -------------------------

    def visit_Name(self, node: ast.Name):
        """
        Called when we see a bare name, e.g. `A` or `i`.
        We need to distinguish between address-lists (like "A")
        and loop-variables (like "i").
        """
        name_str = node.id
        if name_str in self.loop_vars:
            return self.loop_vars[name_str]
        elif name_str in self.addresses:
            # Return the entire list of DramAddresses for that name
            return self.addresses[name_str]
        else:
            raise ValueError(f"Unknown name: {name_str}")

    def visit_Constant(self, node: ast.Constant):
        """Python 3.8+ uses Constant instead of Num."""
        # If it's just a number (int, float), return it.
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def visit_BinOp(self, node: ast.BinOp):
        left_val = self.visit(node.left)
        right_val = self.visit(node.right)

        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")

        return SAFE_OPERATORS[op_type](left_val, right_val)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        operand_val = self.visit(node.operand)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")

        return SAFE_OPERATORS[op_type](operand_val)

    def visit_Subscript(self, node: ast.Subscript):
        """
        Handles something like A[i+1].
        - node.value is the "A"
        - node.slice is the "i+1"
        """
        base_obj = self.visit(node.value)  # e.g. addresses["A"]
        if not isinstance(base_obj, list):
            raise ValueError("Subscript is only supported on address lists for now.")

        # Evaluate the slice
        # In Python >= 3.9, slice can be ast.Constant, ast.Slice, etc.
        # We assume it's something like A[i+1] (simple index).
        if isinstance(node.slice, ast.Slice):
            raise ValueError("Slicing (e.g. A[1:3]) not supported.")
        index_val = self.visit(node.slice)
        if not isinstance(index_val, int):
            raise ValueError("Array index must evaluate to an integer.")

        # Bounds check
        if index_val < 0 or index_val >= len(base_obj):
            raise IndexError(f"Index {index_val} out of range.")

        return base_obj[index_val]  # returns a DramAddress

    def visit_Attribute(self, node: ast.Attribute):
        """
        Handles something like (A[i+1]).row
        - node.value is A[i+1] (which hopefully is a DramAddress)
        - node.attr is 'row' or 'bank'
        """
        obj = self.visit(node.value)
        if not isinstance(obj, DramAddress):
            raise ValueError(
                f"Cannot get attribute '{node.attr}' on non-DramAddress: {obj}"
            )

        attr = node.attr
        if not hasattr(obj, attr):
            raise ValueError(f"DramAddress has no attribute '{attr}'")

        return getattr(obj, attr)

    # For Python < 3.8, you might also define visit_Num, etc.
    # but the gist is the same.


def main():
    addresses = {
        "A": [DramAddress(bank=2, row=100), DramAddress(bank=3, row=150)],
        "B": [DramAddress(bank=5, row=200), DramAddress(bank=6, row=250)],
    }
    loop_vars = {"i": 0}

    resolver = ExpressionResolver(addresses, loop_vars)

    expr = "A[i+1].row - 1"
    val = resolver.evaluate(expr)
    print(val)  # 149


if __name__ == "__main__":
    main()
