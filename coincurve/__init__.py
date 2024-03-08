import ctypes
import os
import warnings

from coincurve.context import GLOBAL_CONTEXT, Context
from coincurve.keys import PrivateKey, PublicKey, PublicKeyXOnly
from coincurve.utils import verify_signature

__all__ = [
    'GLOBAL_CONTEXT',
    'Context',
    'PrivateKey',
    'PublicKey',
    'PublicKeyXOnly',
    'verify_signature',
]

LIBRARY_NAME = 'libsecp256k1-2.dll'


def check_library():
    path_to_library = os.path.join(os.getenv('CONDA_PREFIX'), 'Library', 'bin', LIBRARY_NAME)
    try:
        ctypes.CDLL(path_to_library)
    except Exception:
        warnings.warn(f'The required library {LIBRARY_NAME} is not loaded.')


# Call the function during initialization
check_library()
