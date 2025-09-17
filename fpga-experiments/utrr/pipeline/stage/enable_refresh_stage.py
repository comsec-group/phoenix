from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class EnableRefresh(Stage):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EnableRefresh, cls).__new__(cls)
        return cls._instance

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        controller.enable_refresh()
        return pipe_ctxt

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(address={hex(id(self))})"
