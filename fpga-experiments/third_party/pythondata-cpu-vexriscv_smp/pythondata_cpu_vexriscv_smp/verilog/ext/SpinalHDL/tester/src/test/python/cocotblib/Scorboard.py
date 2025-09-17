from queue import Queue

import cocotb
from cocotb.result import TestFailure

from cocotblib.Phase import Infrastructure, PHASE_CHECK_SCORBOARDS


class ScorboardInOrder(Infrastructure):
    def __init__(self,name,parent):
        Infrastructure.__init__(self,name,parent)
        self.refs = Queue()
        self.uuts = Queue()
        self.refsCounter = 0
        self.uutsCounter = 0

    def refPush(self,ref):
        self.refs.put(ref)
        self.refsCounter += 1
        self.update()

    def uutPush(self,uut):
        self.uuts.put(uut)
        self.uutsCounter += 1
        self.update()

    def update(self):
        if (not self.refs.empty()) and (not self.uuts.empty()):
            ref = self.refs.get()
            uut = self.uuts.get()

            self.match(uut,ref)


    def match(self,uut,ref):
        if not uut.equalRef(ref):
            cocotb.log.error("Missmatch detected in " + self.getPath())
            uut.assertEqualRef(ref)

    def startPhase(self, phase):
        Infrastructure.startPhase(self, phase)
        if phase == PHASE_CHECK_SCORBOARDS:
            if (not self.refs.empty()) or (not self.uuts.empty()):
                error = self.getPath() + " has some remaining transaction :\n"
                for e in self.refs.queue:
                    error += "REF:\n" + str(e) + "\n"

                for e in self.uuts.queue:
                    error += "UUT:\n" + str(e) + "\n"

                cocotb.log.error(error)


    def endPhase(self, phase):
        Infrastructure.endPhase(self, phase)
        if phase == PHASE_CHECK_SCORBOARDS:
            if (not self.refs.empty()) or (not self.uuts.empty()):
                raise TestFailure("Scoreboard not empty")


class ScorboardOutOfOrder(Infrastructure):
    def __init__(self,name,parent):
        Infrastructure.__init__(self,name,parent)
        self.refsDic = {}
        self.uutsDic = {}
        self.listeners = []


    def addListener(self,func):
        self.listeners.append(func)

    def refPush(self,ref,oooid):
        if oooid not in self.refsDic:
            self.refsDic[oooid] = Queue()
        self.refsDic[oooid].put(ref)
        self.update(oooid)

    def uutPush(self, uut, oooid):
        if oooid not in self.uutsDic:
            self.uutsDic[oooid] = Queue()
        self.uutsDic[oooid].put(uut)
        self.update(oooid)

    def update(self,oooid):
        if oooid in self.uutsDic and oooid in self.refsDic:
            refs = self.refsDic[oooid]
            uuts = self.uutsDic[oooid]

            ref = refs.get()
            uut = uuts.get()

            self.match(uut,ref)

            #Clean
            if refs.empty():
                self.refsDic.pop(oooid)
            if uuts.empty():
                self.uutsDic.pop(oooid)


    def match(self,uut,ref):
        equal = uut.equalRef(ref)
        for l in self.listeners:
            l(uut,ref,equal)

        if not equal:
            cocotb.log.error("Missmatch detected in " + self.getPath())
            uut.assertEqualRef(ref)

    def startPhase(self, phase):
        Infrastructure.startPhase(self, phase)
        if phase == PHASE_CHECK_SCORBOARDS:
            if len(self.refsDic) != 0 or len(self.uutsDic) != 0:
                error = self.getPath() + " has some remaining transaction :\n"
                for l in self.refsDic.values():
                    for e in l.queue:
                        error += "REF:\n" + str(e) + "\n"

                for l in self.uutsDic.values():
                    for e in l.queue:
                        error += "UUT:\n" + str(e) + "\n"

                cocotb.log.error(error)


    def endPhase(self, phase):
        Infrastructure.endPhase(self, phase)
        if phase == PHASE_CHECK_SCORBOARDS:
            if len(self.refsDic) != 0 or len(self.uutsDic) != 0:
                raise TestFailure("Scoreboard not empty")

