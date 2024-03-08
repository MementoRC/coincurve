import os
import sys

if __name__ == '__main__' and os.name == 'nt':
    import dlltracer

    with dlltracer.Trace(out=sys.stdout):
        import coincurve._libsecp256k1  # noqa: F401
