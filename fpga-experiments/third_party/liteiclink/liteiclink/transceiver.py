# Retro-compatibility 2020-10-14
import sys
from liteiclink import serdes
sys.modules[__name__] = serdes
