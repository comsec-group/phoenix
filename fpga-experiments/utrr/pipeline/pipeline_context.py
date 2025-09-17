import time
from dataclasses import dataclass, replace
from typing import Dict, Any, Iterable

from utrr.dram.dram_address import DramAddress


@dataclass(frozen=True)
class PipelineContext:
    data: Dict[str, Any]
    pipe_start_time: float
    addresses_bitflipped: Iterable[DramAddress]

    @staticmethod
    def reset() -> "PipelineContext":
        return PipelineContext(
            data={}, pipe_start_time=time.time(), addresses_bitflipped=[]
        )

    def add_data(self, key: str, value: Any) -> "PipelineContext":
        if key in self.data:
            raise ValueError(
                f"Key '{key}' is already present in the PipelineContext data."
            )
        new_data = {**self.data, key: value}
        return replace(self, data=new_data)

    def replace_addresses_bitflipped(
        self, new_addresses: Iterable["DramAddress"]
    ) -> "PipelineContext":
        return replace(self, addresses_bitflipped=new_addresses)
