import sys

import dlltracer

with dlltracer.Trace(out=sys.stdout):
    import coincurve._libsecp256k1  # noqa: F401
