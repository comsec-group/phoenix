from dataclasses import dataclass
from typing import List, Union

from utrr.dram.dram_address import DramAddress


@dataclass
class Command:
    pass


@dataclass
class PreCommand(Command):
    pass


@dataclass
class RefCommand(Command):
    pass


@dataclass
class ActCommand(Command):
    bank: Union[str, int]
    row: Union[str, int]


@dataclass
class LoopCommand(Command):
    count: int
    body: List[Command]


@dataclass
class ForCommand(Command):
    var_name: str
    # Allow either an integer (e.g. 0, 100) or a string (e.g. "i * 59")
    start: Union[int, str]
    end: Union[int, str]
    body: List[Command]


@dataclass
class NopCommand(Command):
    count: int
