from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


import random


class IssueRandomRefresh(Stage):
    def __init__(self, random_refresh_range: range):
        self.random_refresh_range = random_refresh_range

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        target_ref_count_increment = random.choice(self.random_refresh_range)
        current_ref_count = controller.read_refresh_count()
        target_ref_count = current_ref_count + target_ref_count_increment
        controller.align_refresh(target_ref_count=target_ref_count)
        return pipe_ctxt

    def __repr__(self):
        return f"{self.__class__.__name__}(random_refresh_range={self.random_refresh_range})"
