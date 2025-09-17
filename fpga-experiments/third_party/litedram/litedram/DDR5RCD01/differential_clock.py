from migen import * 
from random import randint
import logging

class A(Module):
    def __init__(self, input, output):
        self.sync += output.eq(input)

class Driver(Module):
    def __init__(self, clock_domain, signal):
        self.clock_domain = clock_domain
        self.signal = signal
        self.ck_t = Signal()
        self.ck_c = Signal()
        self.comb += self.ck_c.eq(~self.ck_t)

    def drive(self, b=0):
        yield self.signal.eq(b)
    
    def driver_pattern(self):
        base_pattern = [0x0, 0xF, 0x0, 0xF, 0xF]
        test_pattern = base_pattern + [randint(0, 0xF) for _ in range(16)]
        while (yield ResetSignal(self.clock_domain)):
            yield
        for b in test_pattern:
            yield from self.drive(b)
            yield
        
    def drive_clk(self):
        for _ in range(64):
            yield self.ck_t.eq(~(yield self.ck_t))
            yield

    def generators_dict(self):
        return {self.clock_domain: [self.driver_pattern(), self.drive_clk()]}

class TestBed(Module):
    def __init__(self):
        """ Differential clock domain """
        self.submodules.crg = CRG(self, 3)
        self.generators = {}

        self.input = Signal(4)
        self.output = Signal(4)

        driver = Driver("sysx8", self.input)
        self.crg.add_domain("ck_t", (32, 15))
        self.crg.add_domain("ck_c", (32, 31))
        self.submodules += driver

        self.submodules.xA_ck_tc = ClockDomainsRenamer("sysx8")(
            A(
                input=self.input[0],
                output=self.output[0]
            )
        )
        
        self.submodules.xA_ck_t = ClockDomainsRenamer("ck_t")(
            A(
                input=self.input[1],
                output=self.output[1]
           )
        )
        
        self.submodules.xA_ck_c = ClockDomainsRenamer("ck_c")(
            A(
                input=self.input[2],
                output=self.output[2]
            )
        )
        
        self.submodules.xA_sys = A(
            input=self.input[3],
            output=self.output[3]
        )
        self.add_generators(driver.generators_dict())
    
    def add_generators(self, generators):
        for key, value in generators.items():
            if key not in self.generators:
                self.generators[key] = list()
            if not isinstance(value, list):
                value = list(value)
            self.generators[key].extend(value)

    def run_test(self):
        return self.generators

class CRG(Module):
    def __init__(self, tb, reset_cnt):
        """
            clocks = {
                "clk_name" : (clk_period in ticks, clk_shift in ticks)
            }
        """
        self.clocks = clocks ={
            "sys":      (128, 63),
            "sysx2":    (64, 31),
            "sysx4":    (32, 15),
            "sysx8":    (16, 7),
            "sys_rst":  (128, 63+4),
        }

        r = Signal(max=reset_cnt+1)
        self.sync.sys_rst += [
            If( r < reset_cnt, 
                r.eq(r+1),
            )
        ]
        for clk in clocks:
            if clk == "sys_rst":
                continue
            setattr(self.clock_domains, "cd_{}".format(clk), ClockDomain(clk))
            cd = getattr(self, 'cd_{}'.format(clk))
            self.comb += cd.rst.eq(~(r == reset_cnt))

    def add_domain(self, clock_domain, clk_tuple, clk_rst=None):
        cd = getattr(self, f"cd_{clock_domain}", None)
        assert cd is None, f"{clock_domain} already exists"
        setattr(
            self.clock_domains,
            "cd_{}".format(clock_domain),
            ClockDomain(clock_domain)
        )
        cd = getattr(self, 'cd_{}'.format(clock_domain))
        self.clocks[clock_domain] = clk_tuple
        if clk_rst is not None:
            self.comb += cd.rst.eq(clk_rst)



if __name__ == "__main__":
    wave_file_name="main.vcd"
    tb = TestBed()
    finish = [False]
    run_simulation(tb, generators=tb.run_test(), clocks=tb.crg.clocks, vcd_name=wave_file_name)
