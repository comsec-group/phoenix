from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ExperimentResultDir:
    path: Path

    @classmethod
    def create(cls, path: Path) -> "ExperimentResultDir":
        """
        Ensure that the directory at `path` exists and return a new ExperimentResultDir.
        """
        path.mkdir(parents=True, exist_ok=True)
        return cls(path)

    @staticmethod
    def from_base(base_results_dir: Path) -> "ExperimentResultDir":
        """
        Create a new ExperimentResultDir based on the current timestamp under the given base directory.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_dir_path = base_results_dir / timestamp
        return ExperimentResultDir.create(result_dir_path)

    def __repr__(self):
        return f"ExperimentResultDir(path={self.path})"

    def get_log_file_path(self) -> Path:
        return self.path / "experiment_run.log"

    def get_result_export_path(self) -> Path:
        return self.path / "results.jsonl"

    def get_payload_path(self, payload_id: int = 0) -> Path:
        filename = f"payload_{payload_id}.txt"
        return self.path / filename

    def get_pyram_path(self, program_id: int = 0) -> Path:
        filename = f"payload_{program_id}.pyram"
        return self.path / filename

    def get_subdirectory(self, subfolder_name: str) -> "ExperimentResultDir":
        return ExperimentResultDir.create(self.path / subfolder_name)
