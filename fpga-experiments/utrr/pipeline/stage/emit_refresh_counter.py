from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class EmitRefreshCounter(Stage):
    def __init__(self, key_name: str, modulus: int = None):
        self.key_name = key_name
        self.modulo = modulus

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        refresh_count = controller.read_refresh_count()
        pipe_ctxt = pipe_ctxt.add_data(self.key_name, refresh_count)

        if self.modulo is not None:
            refresh_mod = refresh_count % self.modulo
            pipe_ctxt = pipe_ctxt.add_data(
                f"{self.key_name}_{self.modulo}", refresh_mod
            )

        return pipe_ctxt

    def __repr__(self):
        return f"{self.__class__.__name__}(key_name={self.key_name!r}, modulo={self.modulo})"
