```
                               __   _ __      ___________   _      __
                              / /  (_) /____ /  _/ ___/ /  (_)__  / /__
                             / /__/ / __/ -_)/ // /__/ /__/ / _ \/  '_/
                            /____/_/\__/\__/___/\___/____/_/_//_/_/\_\

                                Copyright 2017-2022 / EnjoyDigital

                            Small footprint and configurable Inter-Chip
                             communication cores powered by Migen & LiteX
```

[![](https://github.com/enjoy-digital/liteiclink/workflows/ci/badge.svg)](https://github.com/enjoy-digital/liteiclink/actions) ![License](https://img.shields.io/badge/License-BSD%202--Clause-orange.svg)


[> Intro
--------
LiteICLink provides small footprint and configurable inter chip communication
cores.

LiteICLink is part of LiteX libraries whose aims are to lower entry level of
complex FPGA cores by providing simple, elegant and efficient implementations
of components used in today's SoC such as Ethernet, SATA, PCIe, SDRAM Controller...

Using Migen to describe the HDL allows the core to be highly and easily configurable.

LiteICLink can be used as LiteX library or can be integrated with your standard
design flow by generating the verilog rtl that you will use as a standard core.

[> Features
-----------
SerWB:
  - Wishbone over 3 LVDS I/Os (high speed) or 3 Single-Ended I/Os (low speed).
  - Artix7, Kintex7, Kintex Ultrascale high-speed PHYs.
  - Vendor agnostic low-speed PHY.
  - 8B/10B, integrated gearbox.
  - Up to 1.25Gbps linerate / 32 bits @ 31.25Mhz user interface.
  - Automatic sampling window adjustement at startup.
  - Encapsulated Etherbone protocol with buffered writes.

SerDes:
  - Artix7 GTP support.
  - Kintex7 GTX support.
  - Ultrascale GTH support.
  - Ultrascale+ GTY support.
  - Lattice ECP5 support.

[> FPGA Proven
---------------
LiteICLink is already used in commercial and open-source designs:
- Software Defined Radio boards for CPRI/JESD204B: http://enjoy-digital.fr/
- USB3 Pipe: https://github.com/enjoy-digital/usb3_pipe
- ARTIQ: https://m-labs.hk/artiq/
- and others commercial designs...

[> Possible improvements
------------------------
- add support for Altera SerDes.
- add support for Lattice Crosslink NX SerDes.
- add more documentation
- ... See below Support and consulting :)

If you want to support these features, please contact us at florent [AT]
enjoy-digital.fr.

[> Getting started
------------------
1. Install Python 3.6+ and FPGA vendor's development tools.
2. Install LiteX and the cores by following the LiteX's wiki [installation guide](https://github.com/enjoy-digital/litex/wiki/Installation).
3. You can find examples of integration of the core with LiteX in LiteX-Boards and in the examples directory.

[> Tests
--------
Unit tests are available in ./test/.
To run all the unit tests:
```sh
$ ./setup.py test
```

Tests can also be run individually:
```sh
$ python3 -m unittest test.test_name
```

[> License
----------
LiteICLink is released under the very permissive two-clause BSD license. Under the
terms of this license, you are authorized to use LiteICLink for closed-source
proprietary designs.
Even though we do not require you to do so, those things are awesome, so please
do them if possible:
 - tell us that you are using LiteICLink
 - cite LiteICLink in publications related to research it has helped
 - send us feedback and suggestions for improvements
 - send us bug reports when something goes wrong
 - send us the modifications and improvements you have done to LiteICLink.

[> Support and consulting
-------------------------
We love open-source hardware and like sharing our designs with others.

LiteICLink is developed and maintained by EnjoyDigital.

If you would like to know more about LiteICLink or if you are already a happy user
and would like to extend it for your needs, EnjoyDigital can provide standard
commercial support as well as consulting services.

So feel free to contact us, we'd love to work with you! (and eventually shorten
the list of the possible improvements :)

[> Contact
----------
E-mail: florent [AT] enjoy-digital.fr
