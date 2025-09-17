import json
from pathlib import Path
from typing import Dict

from utrr.pipeline.pipeline_context import PipelineContext
from utrr.pipeline.stage.stage import Stage
from utrr.dram.dram_controller import DramController


class ExportPipeContext(Stage):
    """
    A stage that exports only the `data` field from the PipelineContext to a JSON Lines file.
    This class provides a "singleton per filepath" behavior, meaning that any attempt to create
    another instance with the same filepath returns the original instance.

    Example:
        e1 = ExportPipeContext(Path("/tmp/file1.jsonl"))
        e2 = ExportPipeContext(Path("/tmp/file1.jsonl"))
        assert e1 is e2  # Same instance for the same filepath

        e3 = ExportPipeContext(Path("/tmp/file2.jsonl"))
        assert e3 is not e1  # Different filepath yields a new instance
    """

    _instances: Dict[Path, "ExportPipeContext"] = {}

    def __new__(cls, filepath: Path):
        # Check if an instance already exists for this filepath
        if filepath in cls._instances:
            return cls._instances[filepath]

        # If not, create a new instance and store it in the dictionary
        instance = super().__new__(cls)
        cls._instances[filepath] = instance
        return instance

    def __init__(self, filepath: Path):
        # The initialization should still run, but remember that
        # for the same filepath, __new__ returns the same instance.
        # So if called multiple times with the same path, __init__ should
        # either do nothing or be idempotent.
        if not hasattr(self, "_initialized"):
            self.filepath = filepath
            self._initialized = True

    def __repr__(self):
        # Include class name, memory address, and filepath in the representation
        return f"<{self.__class__.__name__} at {hex(id(self))}, filepath={self.filepath!r}>"

    def setup(self, controller: DramController):
        # Ensure the file exists by touching it.
        self.filepath.touch(exist_ok=True)

    def execute(
        self, controller: DramController, pipe_ctxt: PipelineContext
    ) -> PipelineContext:
        # Only dump the data field
        record = {"data": pipe_ctxt.data}
        with self.filepath.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return pipe_ctxt
