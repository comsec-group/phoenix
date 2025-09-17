from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class PrechargeAll(Stage):
    def __init__(self):
        self.payload = None

    def setup(self, controller: DramController):
        self.payload = controller.precharge_all_payload()

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        payload = controller.precharge_all_payload()
        controller.execute_payload(payload=payload, verbose=False)
        return pipe_ctxt

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"
