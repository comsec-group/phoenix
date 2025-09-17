import logging
import time
from typing import List

from tqdm import tqdm

from utrr.dram.dram_controller import DramController
from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage

logger = logging.getLogger(__name__)


class Pipeline:
    stages: List[Stage]

    def __init__(self, stages: List[Stage]):
        self.stages = stages

    def run_with_new_ctxt(
        self,
        controller: DramController,
        use_progress_bar: bool = False,
        progress_desc: str = "Running Stages",
    ) -> PipelineContext:
        pipe_ctxt = PipelineContext(
            pipe_start_time=time.time(), data={}, addresses_bitflipped={}
        )
        return self.run(
            controller=controller,
            pipe_ctxt=pipe_ctxt,
            use_progress_bar=use_progress_bar,
            progress_desc=progress_desc,
        )

    def run(
        self,
        controller: DramController,
        pipe_ctxt: PipelineContext,
        use_progress_bar: bool = False,
        progress_desc: str = "Running Stages",
    ) -> PipelineContext:
        self._setup_stages(controller, use_progress_bar)

        stages_iter = (
            tqdm(self.stages, desc=progress_desc, unit="stage")
            if use_progress_bar
            else self.stages
        )

        start_time = time.time()

        stage_results = [{}]

        for stage in stages_iter:
            # Calculate the time relative to pipe_start_time in milliseconds
            relative_execution_time_ms = (
                time.time() - pipe_ctxt.pipe_start_time
            ) * 1000

            execution_start_time = time.time()
            pipe_ctxt = stage.execute(controller, pipe_ctxt)
            execution_duration = (time.time() - execution_start_time) * 1000

            stage_results.append(pipe_ctxt)

            relative_time_str = f"{relative_execution_time_ms:8.2f} ms"
            duration_str = f"{execution_duration:8.2f} ms"
            logger.debug(f"[{relative_time_str} / {duration_str}] executed: {stage}")

        total_duration = (time.time() - start_time) * 1000
        logger.debug(f"Total execution time: {total_duration:.2f} ms.")

        return pipe_ctxt

    def _setup_stages(
        self, controller: DramController, use_progress_bar: bool = False
    ) -> None:
        """Sets up all stages and logs the setup duration."""
        setup_start_time = time.time()

        # Conditionally wrap stages in a tqdm iterator if progress bar is enabled
        stages_iter = (
            tqdm(self.stages, desc="Setting Up Stages", unit="stage")
            if use_progress_bar
            else self.stages
        )

        for stage in stages_iter:
            stage.setup(controller=controller)

        total_setup_duration = (time.time() - setup_start_time) * 1000
        logger.debug(f"Total setup time for all stages: {total_setup_duration:.2f} ms.")
