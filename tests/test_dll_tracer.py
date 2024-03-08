import os
import sys

from ctypes import CDLL

if __name__ == '__main__' and os.name == 'nt':
    import dlltracer

    with dlltracer.Trace(out=sys.stdout):
        CDLL('libsecp256k1.dll', 0)
        import coincurve._libsecp256k1  # noqa: F401
