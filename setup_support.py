import glob
import logging
import os
import subprocess
from contextlib import suppress


def absolute(*paths):
    op = os.path
    return op.realpath(op.abspath(op.join(op.dirname(__file__), *paths)))


def update_pkg_config_path(path='.'):
    """Updates the PKG_CONFIG_PATH environment variable to include the given path."""
    pkg_config_paths = [path, os.getenv('PKG_CONFIG_PATH', '').strip('"')]

    if cpf := os.getenv('CONDA_PREFIX'):
        conda_paths = [os.path.join(cpf, sbd, 'pkgconfig') for sbd in ('lib', 'lib64', os.path.join('Library', 'lib'))]
        pkg_config_paths.extend([p for p in conda_paths if os.path.isdir(p)])

    if lbd := os.getenv('LIB_DIR'):
        pkg_config_paths.append(os.path.join(lbd, 'pkgconfig'))

    # Update environment
    os.environ['PKG_CONFIG_PATH'] = os.pathsep.join(pkg_config_paths)


def build_flags(library, type_, path):
    """Return separated build flags from pkg-config output"""

    update_pkg_config_path(path)

    options = {'I': '--cflags-only-I', 'L': '--libs-only-L', 'l': '--libs-only-l'}
    # flags = subprocess.check_output(['pkg-config', options[type_], library])  # S603
    flags = call_pkg_config([options[type_]], library)
    flags = list(flags.split())

    return [flag.strip(f'-{type_}') for flag in flags]


def _find_lib():
    if 'COINCURVE_IGNORE_SYSTEM_LIB' in os.environ:
        return False

    from cffi import FFI

    from setup import LIB_NAME

    update_pkg_config_path()

    try:
        lib_dir = call_pkg_config(['--libs-only-L'], LIB_NAME)
    except (OSError, subprocess.CalledProcessError):
        if 'LIB_DIR' in os.environ:
            for path in glob.glob(os.path.join(os.environ['LIB_DIR'], f'*{LIB_NAME[3:]}*')):
                with suppress(OSError):
                    FFI().dlopen(path)
                    return True
        # We couldn't locate libsecp256k1, so we'll use the bundled one
        return False

    return verify_system_lib(lib_dir[2:].strip())


_has_system_lib = None


def has_system_lib():
    global _has_system_lib
    if _has_system_lib is None:
        _has_system_lib = _find_lib()
    return _has_system_lib


def detect_dll():
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in os.listdir(os.path.join(here, 'coincurve')):
        if fn.endswith('.dll'):
            return True
    return False


def subprocess_run(cmd, *, debug=False):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa S603
        if debug:
            logging.info(f'Command log:\n{result.stderr}')

        return result.stdout.strip()

    except subprocess.CalledProcessError as e:
        logging.error(f'An error occurred during the command execution: {e}')
        logging.error(f'Command log:\n{e.stderr}')
        raise e


def call_pkg_config(options, library, *, debug=False):
    """Calls pkg-config with the given options and returns the output."""
    import shutil

    from setup import SYSTEM

    if SYSTEM == 'Windows':
        options.append('--dont-define-prefix')

    pkg_config = shutil.which('pkg-config')
    cmd = [pkg_config, *options, library]

    return subprocess_run(cmd, debug=debug)


def has_installed_libsecp256k1():
    """Checks if libsecp256k1 is installed on the system."""
    if os.getenv('COINCURVE_IGNORE_SYSTEM_LIB', '1') == '1':
        return False

    from cffi import FFI

    from setup import LIB_NAME

    update_pkg_config_path()

    try:
        lib_dir = call_pkg_config(['--libs-only-L'], LIB_NAME)
    except (OSError, subprocess.CalledProcessError):
        if 'LIB_DIR' in os.environ:
            for path in glob.glob(os.path.join(os.environ['LIB_DIR'], f'*{LIB_NAME[3:]}*')):
                with suppress(OSError):
                    FFI().dlopen(path)
                    return True
        # We couldn't locate libsecp256k1, so we'll use the bundled one
        return False

    return verify_system_lib(lib_dir[2:].strip())


def verify_system_lib(lib_dir):
    """Verifies that the system library is installed and of the expected type."""
    import ctypes
    from pathlib import Path

    from setup import LIB_NAME, PKG_NAME, SECP256K1_BUILD, SYSTEM

    def load_library(lib):
        try:
            return ctypes.CDLL(lib)
        except OSError:
            return None

    lib_dir = Path(lib_dir).with_name('bin') if SYSTEM == 'Windows' else Path(lib_dir)
    lib_ext = '.dll' if SYSTEM == 'Windows' else '.[sd][oy]*'
    logging.warning(f'dir: {lib_dir}')
    logging.warning(f'patt: *{LIB_NAME[3:]}{lib_ext}')
    l_dyn = list(lib_dir.glob(f'*{LIB_NAME[3:]}*{lib_ext}'))

    # Evaluates the dynamic libraries found,
    logging.warning(f'Found libraries: {l_dyn}')
    dyn_lib = next((lib for lib in l_dyn if load_library(lib) is not None), False)

    found = any((dyn_lib and SECP256K1_BUILD == 'SHARED', not dyn_lib and SECP256K1_BUILD != 'SHARED'))
    if not found:
        logging.warning(
            f'WARNING: {LIB_NAME} is installed, but it is not the expected type. '
            f'Please ensure that the {SECP256K1_BUILD} library is installed.'
        )

    if dyn_lib:
        lib_base = dyn_lib.stem
        # Update coincurve._secp256k1_library_info
        info_file = Path(PKG_NAME, '_secp256k1_library_info.py')
        info_file.write_text(f"SECP256K1_LIBRARY_NAME = '{lib_base}'\nSECP256K1_LIBRARY_TYPE = 'EXTERNAL'\n")

    return found
