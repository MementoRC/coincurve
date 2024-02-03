import os
import platform
import shutil
import sys

MAKE = 'gmake' if platform.system() in ['FreeBSD', 'OpenBSD'] else 'make'
PKGCONFIG = shutil.which('pkg-config')

PACKAGE_SETUP_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(PACKAGE_SETUP_DIR)
