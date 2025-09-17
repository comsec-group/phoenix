import logging
import random
from typing import Iterable

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController

logger = logging.getLogger(__name__)


class BitflipCheckRow(Stage):
    def __init__(
        self,
        bank: int,
        rows: Iterable[int],
        pattern_32bit: int,
        shuffle_rows_before_check: bool = False,
    ):
        self.bank = bank
        self.rows = list(rows)
        self.pattern_32bit = pattern_32bit
        self.shuffle_rows_before_check = shuffle_rows_before_check

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        if self.shuffle_rows_before_check:
            random.shuffle(self.rows)

        rows_bitflipped = controller.dma_memtest_rows_flipped(
            self.bank, self.rows, self.pattern_32bit
        )
        return pipe_ctxt.add_data("rows_bitflipped", rows_bitflipped)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(bank={self.bank}, "
            f"rows={sorted(self.rows)}, pattern_32bit={hex(self.pattern_32bit)})"
        )
