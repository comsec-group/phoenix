from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class SendRefresh(Stage):
    def __init__(self, refresh_count: int, verbose: bool = False):
        self.refresh_count = refresh_count
        self.refresh_payload = None
        self.verbose = verbose

    def setup(self, controller: DramController):
        self.refresh_payload = controller.generate_refresh_payload(
            self.refresh_count, verbose=self.verbose
        )

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        controller.execute_payload(payload=self.refresh_payload, verbose=self.verbose)
        refresh_count = controller.read_refresh_count()
        return pipe_ctxt.add_data("refresh_count", refresh_count)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"refresh_count={self.refresh_count}, "
            f"refresh_payload={'set' if self.refresh_payload else 'not set'}, "
            f"address={hex(id(self))}"
            ")"
        )
