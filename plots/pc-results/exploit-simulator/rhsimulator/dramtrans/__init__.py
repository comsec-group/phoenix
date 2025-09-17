import ctypes
import os
import functools

_lib = None
LIBNAME = "libtrans.so"

class MemLayout():
    channels    = None
    dimms       = None
    ranks       = None
    banks       = None
    
    @classmethod
    def init_layout(cls, ddict, overwrite=False):
        # the memory layout was already initialized
        if not overwrite:
            if cls.channels and cls.dimms and cls.ranks and cls.banks:
                # if the layout is different
                if set([cls.channels, cls.dimms, cls.ranks, cls.banks]) != set(ddict.values()):
                    raise Exception("MemLayout already initialized")
                else:
                    return

        cls.channels    = ddict['channels']
        cls.dimms       = ddict['dimms']
        cls.ranks       = ddict['ranks']
        cls.banks       = ddict['banks']

        init_lib(cls.ranks)
    
    @classmethod
    def assert_layout(cls):
        if not (cls.channels and cls.dimms and cls.ranks and cls.banks):
            raise Exception("Not initialized yet")

@functools.total_ordering
class DRAMAddr(ctypes.Structure):
    _fields_ = [('bank', ctypes.c_uint64),
                ('row', ctypes.c_uint64),
                ('col', ctypes.c_uint64)]
    
    @classmethod
    def from_addr(cls, addr): 
        _assert_lib()
        if isinstance(addr, int):
            return _lib.to_dram(addr) 
        else:
            return NotImplemented


    def __init__(self, bank, row, col=0): 
        self.bank   = bank
        self.row    = row
        self.col    = col
    
    @property
    def numeric_value(s):
        _assert_lib()
        return _lib.linearize(s)

    def to_addr(d):
        _assert_lib()
        return int(_lib.to_addr(d))

    def __str__(s):
        return f"DRAMAddr(b:{s.bank:02d}, r:{s.row:>6d}, c{s.col:>4d})"    

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if isinstance(other, DRAMAddr):
            return self.numeric_value == other.numeric_value
        else:
            return NotImplemented

    def __lt__(self, other):
        if isinstance(other, DRAMAddr):
            return self.numeric_value < other.numeric_value
        else:
            return NotImplemented

    def __hash__(self):
        return self.numeric_value

    def __len__(self):
        return len(self._fields_)


    def same_bank(self, other):
        return  self.bank == other.bank

    
    def __add__(self, other):
        if isinstance(other, DRAMAddr):
            return type(self)(
                self.bank + other.bank,
                self.row + other.row,
                self.col + other.col
            )
        elif isinstance(other, int):
            return type(self)(
                self.bank,
                self.row + other,
                self.col 
            )
        else:
            return NotImplemented

    def __sub__(self, other):
        if isinstance(other, DRAMAddr):
            return type(self)(
                self.bank - other.bank,
                self.row - other.row,
                self.col - other.col
            )
        elif isinstance(other, int):
            return type(self)(
                self.bank,
                self.row + other,
                self.col 
            )
        else:
            return NotImplemented



def _assert_lib():
    global _lib
    if _lib is None:
        raise Exception(f"Library {LIBNAME} not loaded")

def init_lib(ranks):
    global _lib

    if ranks > 2:
        raise Exception(f"Ranks {ranks} > 2")

    path = os.path.dirname(os.path.abspath(__file__))
    _lib = ctypes.cdll.LoadLibrary(os.path.join(path, LIBNAME))


    _lib.to_dram.restype = DRAMAddr 
    _lib.to_dram.argtypes = [ctypes.c_size_t]

    _lib.to_addr.restype = ctypes.c_size_t 
    _lib.to_addr.argtypes = [DRAMAddr]
    
    _lib.linearize.restype = ctypes.c_size_t 
    _lib.linearize.argtypes = [DRAMAddr]
    
    _lib.init_lib.restype = ctypes.c_size_t
    _lib.init_lib.argtypes = [ctypes.c_size_t]

    # TODO the init_lib function at the moment accepts only
    # two configurations 1rk, 2rk. be careful on how you pass this parameter 
    _lib.init_lib(ranks-1)
