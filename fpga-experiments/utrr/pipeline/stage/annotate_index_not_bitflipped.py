import logging
from typing import List, Dict

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController
from utrr.dram.dram_address import DramAddress

logger = logging.getLogger(__name__)


class AnnotateIndexNotBitflipped(Stage):
    def __init__(
        self,
        addresses: Dict[DramAddress, List[int]],
    ):
        self.addresses = addresses

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        indices_not_bitflipped = []
        for address in pipe_ctxt.addresses_bitflipped:
            indices_not_bitflipped.extend(self.addresses[address])

        indices_not_bitflipped = sorted(indices_not_bitflipped)

        return pipe_ctxt.add_data("indices_not_bitflipped", indices_not_bitflipped)
