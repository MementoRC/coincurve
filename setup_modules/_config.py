import platform
import shutil

MAKE = 'gmake' if platform.system() in ['FreeBSD', 'OpenBSD'] else 'make'
PKGCONFIG = shutil.which('pkg-config')
