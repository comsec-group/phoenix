
import cocotb
import types
from cocotb.result import TestFailure
from cocotb.triggers import RisingEdge, Timer, Event
from cocotblib.Phase import Infrastructure, PHASE_WAIT_TASKS_END
from cocotblib.Scorboard import ScorboardInOrder

from cocotblib.misc import Bundle, BoolRandomizer


class Stream:
    def __init__(self, dut, name):
        self.valid   = dut.__getattr__(name + "_valid")
        self.ready   = dut.__getattr__(name + "_ready")
        self.payload = Bundle(dut,name + "_payload")
        # Event
        self.event_ready = Event()
        self.event_valid = Event()

    def startMonitoringReady(self, clk):
        self.clk  = clk
        self.fork_ready = cocotb.fork(self.monitor_ready())

    def startMonitoringValid(self, clk):
        self.clk  = clk
        self.fork_valid = cocotb.fork(self.monitor_valid())

    def stopMonitoring(self):
        self.fork_ready.kill()
        self.fork_valid.kill()

    @cocotb.coroutine
    def monitor_ready(self):
        while True:
            yield RisingEdge(self.clk)
            if int(self.ready) == 1:
                self.event_ready.set( self.payload )

    @cocotb.coroutine
    def monitor_valid(self):
        while True:
            yield RisingEdge(self.clk)
            if int(self.valid) == 1:
                self.event_valid.set( self.payload )


class Transaction(object):
    def __init__(self):
        object.__setattr__(self,"_nameToElement",{})

    def __setattr__(self, key, value):
        # print("set " + key)
        if key[0] != '_':
            self._nameToElement[key] = value
        object.__setattr__(self,key,value)

    def equalRef(self,ref):
        # if(len(self._nameToElement) != len(ref._nameToElement)):
        #     return False
        for name in self._nameToElement:
            refValue = getattr(ref,name)
            if refValue != None and self._nameToElement[name] != getattr(ref,name):
                return False
        return True

    def assertEqualRef(self,ref):
        if not self.equalRef(ref):
            raise TestFailure("\nFAIL transaction not equal\ntransaction =>\n%s\nref =>\n%s\n\n" % (self,ref))


    def __str__(self):
        buffer = ""
        biggerName = 0
        for n in self._nameToElement:
            if len(n) > biggerName:
                biggerName = len(n)
        for name in self._nameToElement:
            e = self._nameToElement[name]
            buffer += "%s %s: 0x%x\n" % (name," "*(biggerName-len(name)), 0 if e == None else e)
        return buffer

# Transaction = type('Transaction', (object,), {})

class StreamDriverMaster:
    def __init__(self,stream,transactor,clk,reset):
        self.stream = stream
        self.clk = clk
        self.reset = reset
        self.transactor = transactor

        cocotb.fork(self.stim())

    @cocotb.coroutine
    def stim(self):
        stream = self.stream
        stream.valid <= 0
        while True:
            yield RisingEdge(self.clk)
            if int(stream.valid) == 1 and int(stream.ready) == 1:
                stream.valid <= 0
                for i in range(nextDelay):
                    yield RisingEdge(self.clk)

            if self.transactor != None and (int(stream.valid) == 0 or int(stream.ready) == 1):
                if isinstance(self.transactor,types.GeneratorType):
                    trans = next(self.transactor)
                else:
                    trans = self.transactor()
                if trans != None:
                    if hasattr(trans,"nextDelay"):
                        nextDelay = trans.nextDelay
                    else:
                        nextDelay = 0
                    stream.valid <= 1

                    for name in stream.payload.nameToElement:
                        if hasattr(trans,name) == False:
                            raise Exception("Missing element in bundle :" + name)
                        e = stream.payload.nameToElement[name] <= getattr(trans,name)



class StreamDriverSlave:
    def __init__(self,stream,clk,reset):
        self.stream = stream
        self.clk = clk
        self.reset = reset
        self.randomizer = BoolRandomizer()
        cocotb.fork(self.stim())

    @cocotb.coroutine
    def stim(self):
        stream = self.stream
        stream.ready <= 1
        while True:
            yield RisingEdge(self.clk)
            stream.ready <= self.randomizer.get()


def TransactionFromBundle(bundle):
    trans = Transaction()
    for name in bundle.nameToElement:
        setattr(trans,name, int(bundle.nameToElement[name]))
    return trans


class StreamMonitor:
    def __init__(self,stream,callback,clk,reset):
        self.stream = stream
        self.callback = callback
        self.clk = clk
        self.reset = reset
        cocotb.fork(self.stim())

    @cocotb.coroutine
    def stim(self):
        stream = self.stream
        while True:
            yield RisingEdge(self.clk)
            if int(stream.valid) == 1 and int(stream.ready) == 1:
                trans = TransactionFromBundle(stream.payload)
                yield Timer(1)
                self.callback(trans)




class StreamFifoTester(Infrastructure):
    def __init__(self,name,parent,pushStream,popStream,transactionGenerator,dutCounterTarget,clk,reset):
        Infrastructure.__init__(self,name,parent)
        self.pushStream = pushStream
        self.popStream = popStream
        self.clk = clk
        self.reset = reset
        self.dutCounter = 0
        self.closeIt = False
        self.transactionGenerator = transactionGenerator
        self.dutCounterTarget = dutCounterTarget
        self.pushRandomizer = BoolRandomizer()
        self.scoreboard = ScorboardInOrder("scoreboard", self)

    def createInfrastructure(self):
        StreamDriverMaster(self.pushStream, self.genPush, self.clk, self.reset)
        StreamDriverSlave(self.popStream, self.clk, self.reset)
        StreamMonitor(self.popStream, self.onUut, self.clk, self.reset)
        StreamMonitor(self.pushStream, self.onRef, self.clk, self.reset)

    def startPhase(self, phase):
        Infrastructure.startPhase(self, phase)
        if phase == PHASE_WAIT_TASKS_END:
            self.closeIt = True

    def genPush(self):
        if not self.closeIt and self.pushRandomizer.get():
            return self.transactionGenerator()

    def onUut(self, uut):
        self.dutCounter += 1
        self.scoreboard.uutPush(uut)

    def onRef(self, uut):
        self.scoreboard.refPush(uut)

    def canPhaseProgress(self, phase):
        return self.dutCounter > self.dutCounterTarget


