from typing import Iterable

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.platform_litex.litex.litex_dram_controller import LitexDramController


class BitflipExistCheck(Stage):
    def __init__(
        self,
        bank: int,
        rows: Iterable[int],
        pattern_32bit: int,
        shuffle_order_across_runs: bool = False,
    ):
        self.bank = bank
        self.rows = list(rows)
        self.pattern_32bit = pattern_32bit
        self.shuffle_order_across_runs = shuffle_order_across_runs

    def setup(self, controller: LitexDramController):
        pass

    def execute(
        self, controller: LitexDramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        bitflips = controller.dma_memtest_rows_flipped(
            bank=self.bank, rows=self.rows, pattern_32bit=self.pattern_32bit
        )
        bitflips_sorted = dict(sorted(bitflips.items()))
        return pipe_ctxt.with_updated_bitflips(bitflips_sorted)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"bank={self.bank}, "
            f"rows={sorted(self.rows)}, "
            f"address={hex(id(self))}"
            f")"
        )
