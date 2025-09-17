import logging
from typing import List

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController
from utrr.dram.dram_address import DramAddress

logger = logging.getLogger(__name__)


class BitflipCheckDramAddress(Stage):
    def __init__(
        self,
        addresses: List[DramAddress],
        pattern_32bit: int,
        ignore_addresses: List[DramAddress] = None,
    ):
        self.addresses = addresses
        self.pattern_32bit = pattern_32bit

        if ignore_addresses:
            self.ignore_addresses = ignore_addresses
        else:
            self.ignore_addresses = []

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        addresses_bitflipped = controller.dma_memtest_addresses_flipped(
            addresses=self.addresses, pattern_32bit=self.pattern_32bit
        )
        addresses_bitflipped = set(addresses_bitflipped) - set(self.ignore_addresses)

        address_dict_bitflipped = [
            address.to_dict() for address in addresses_bitflipped
        ]

        return pipe_ctxt.replace_addresses_bitflipped(
            new_addresses=addresses_bitflipped
        ).add_data("addresses_dict_bitflipped", address_dict_bitflipped)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"addresses={self.addresses}, pattern_32bit={hex(self.pattern_32bit)})"
        )
