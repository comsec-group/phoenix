###############################################################################
# Tristate
#
class TriState:

    #==========================================================================
    # Constructor
    #==========================================================================
    def __init__(self, dut, name):

        # interface
        self.read        = dut.__getattr__(name + "_read")
        self.write       = dut.__getattr__(name + "_write")
        self.writeEnable = dut.__getattr__(name + "_writeEnable")


class TriStateOutput:

    #==========================================================================
    # Constructor
    #==========================================================================
    def __init__(self, dut, name):

        # interface
        self.write       = dut.__getattr__(name + "_write")
        self.writeEnable = dut.__getattr__(name + "_writeEnable")