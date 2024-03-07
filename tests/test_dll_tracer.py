import os
import sys

import dlltracer

if __name__ == "__main__" and os.name == 'nt':
    with dlltracer.Trace(out=sys.stdout):
        import coincurve._libsecp256k1  # noqa: F401
