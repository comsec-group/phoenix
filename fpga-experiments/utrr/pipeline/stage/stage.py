from abc import ABC, abstractmethod

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.dram.dram_controller import DramController


class Stage(ABC):
    @abstractmethod
    def setup(self, controller: DramController):
        pass

    @abstractmethod
    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        pass
