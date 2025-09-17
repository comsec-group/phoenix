import random

import cocotb
from cocotb.decorators import coroutine
from cocotb.result import TestFailure, ReturnValue
from cocotb.triggers import RisingEdge, Edge

from cocotblib.misc import log2Up, BoolRandomizer, assertEquals, waitClockedCond, randSignal


class Apb3:
    def __init__(self, dut, name, clk = None):
        self.clk = clk
        self.PADDR     = dut.__getattr__(name + "_PADDR")
        self.PSEL      = dut.__getattr__(name + "_PSEL")
        self.PENABLE   = dut.__getattr__(name + "_PENABLE")
        self.PREADY    = dut.__getattr__(name + "_PREADY")
        self.PWRITE    = dut.__getattr__(name + "_PWRITE")
        self.PWDATA    = dut.__getattr__(name + "_PWDATA")
        self.PRDATA    = dut.__getattr__(name + "_PRDATA")

    def idle(self):
        self.PSEL <= 0

    @coroutine
    def delay(self, cycle):
        for i in range(cycle):
            yield RisingEdge(self.clk)

    @coroutine
    def write(self, address, data, sel = 1):
        self.PADDR <= address
        self.PSEL <= sel
        self.PENABLE <= False
        self.PWRITE <= True
        self.PWDATA <= data
        yield RisingEdge(self.clk)
        self.PENABLE <= True
        yield waitClockedCond(self.clk, lambda : self.PREADY == True)
        randSignal(self.PADDR)
        self.PSEL <= 0
        randSignal(self.PENABLE)
        randSignal(self.PWRITE)
        randSignal(self.PWDATA)

    @coroutine
    def writeMasked(self, address, data, mask, sel = 1):
        readThread = self.read(address,sel)
        yield readThread
        yield self.write(address,(readThread.retval & ~mask) | (data & mask),sel)

    @coroutine
    def read(self, address, sel=1):
        self.PADDR <= address
        self.PSEL <= sel
        self.PENABLE <= False
        self.PWRITE <= False
        randSignal(self.PWDATA)
        yield RisingEdge(self.clk)
        self.PENABLE <= True
        yield waitClockedCond(self.clk, lambda: self.PREADY == True)
        randSignal(self.PADDR)
        self.PSEL <= 0
        randSignal(self.PENABLE)
        randSignal(self.PWRITE)
        raise ReturnValue(int(self.PRDATA))


    @coroutine
    def readAssert(self, address, data, sel=1):
        readThread = self.read(address,sel)
        yield readThread
        assertEquals(int(readThread.retval), data," APB readAssert failure")

    @coroutine
    def readAssertMasked(self, address, data, mask, sel=1):
        readThread = self.read(address,sel)
        yield readThread
        assertEquals(int(readThread.retval) & mask, data," APB readAssert failure")

    @coroutine
    def pull(self, address, dataValue, dataMask, sel=1):
        while True:
            readThread = self.read(address, sel)
            yield readThread
            if (int(readThread.retval) & dataMask) == dataValue:
                break