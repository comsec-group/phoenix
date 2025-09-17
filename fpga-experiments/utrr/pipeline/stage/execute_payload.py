from typing import List

from rowhammer_tester.gateware.payload_executor import Encoder
from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class ExecutePayload(Stage):
    def __init__(
        self,
        payload: List[Encoder.Instruction],
        verbose: bool = False,
    ):
        self.payload = payload
        self.verbose = verbose

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        if self.payload:
            controller.execute_payload(payload=self.payload, verbose=self.verbose)
        return pipe_ctxt

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"len(payload)={len(self.payload)}, "
            # f"payload={payload_to_string(self.payload)}, "
            ")"
        )
