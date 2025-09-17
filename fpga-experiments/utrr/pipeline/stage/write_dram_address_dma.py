from typing import List

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController
from utrr.dram.dram_address import DramAddress


class WriteDramAddressDma(Stage):
    def __init__(
        self,
        rows: List[DramAddress],
        pattern_32bit: int,
    ):
        self.rows = rows
        self.pattern_32bit = pattern_32bit

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        controller.dma_memset_dram_addresses(
            addresses=self.rows, pattern_32bit=self.pattern_32bit
        )

        return pipe_ctxt

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"rows_count={len(self.rows)}, "
            f"rows=[{self.rows}], "
            f"pattern_32bit={hex(self.pattern_32bit)}"
            f")"
        )
