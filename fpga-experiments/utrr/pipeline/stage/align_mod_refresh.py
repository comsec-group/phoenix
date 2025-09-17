from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class AlignModRefresh(Stage):
    def __init__(self, modulus: int, mod_value: int):
        self.modulus = modulus
        self.mod_value = mod_value

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        controller.align_mod_refresh(modulus=self.modulus, mod_value=self.mod_value)
        return pipe_ctxt

    def __repr__(self):
        return f"{self.__class__.__name__}(modulus={self.modulus}, mod_value={self.mod_value})"
