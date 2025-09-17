import time

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class WaitUntilElapsed(Stage):
    def __init__(self, wait_time: int, units: str = "seconds"):
        self.wait_time = wait_time
        self.units = units.lower()

    def setup(self, controller: DramController):
        pass

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        scheduled_time = self._convert_to_seconds(self.wait_time, self.units)

        elapsed_time_ms = time.time() - pipe_ctxt.pipe_start_time
        remaining_time_ms = scheduled_time - elapsed_time_ms

        if remaining_time_ms > 0:
            time.sleep(remaining_time_ms)
        else:
            delay = -remaining_time_ms
            raise RuntimeError(
                f"Timing requirement missed for stage scheduled at {scheduled_time:.2f} seconds. "
                f"Executed late by {delay:.2f} seconds."
            )

        return pipe_ctxt

    @staticmethod
    def _convert_to_seconds(time_value: float, units: str) -> float:
        unit_multipliers = {
            "seconds": 1,
            "milliseconds": 1 / 1000,
            "minutes": 60,
            "hours": 3600,
        }

        if units not in unit_multipliers:
            raise ValueError(f"Unsupported time unit: {units}")

        return time_value * unit_multipliers[units]

    def __repr__(self):
        return f"WaitUntilElapsed(wait_time={self.wait_time}, units='{self.units}')"
