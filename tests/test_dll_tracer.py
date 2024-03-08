import os
import sys
from ctypes import CDLL

if __name__ == '__main__' and os.name == 'nt':
    import dlltracer

    with dlltracer.Trace(out=sys.stdout):
        path = os.getenv('CONDA_PREFIX')

        CDLL(os.path.join(path, 'Library', 'bin', 'libsecp256k1-2.dll'))
        import coincurve._libsecp256k1  # noqa: F401
