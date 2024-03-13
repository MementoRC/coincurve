import os
import os.path
import platform
import shutil
import subprocess
import tarfile
from io import BytesIO
import sys
from sys import path as PATH
from os.path import join

from setuptools import Distribution as _Distribution, setup, find_packages, __version__ as setuptools_version
from setuptools.extension import Extension

# Define the package root directory and add it to the system path
COINCURVE_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
PATH.append(COINCURVE_ROOT_DIR)

# Add setuptools local package path
PATH.insert(0, join(COINCURVE_ROOT_DIR, 'setup_tools'))

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from setup_tools.support import absolute, detect_dll, has_system_lib  # noqa: E402

BUILDING_FOR_WINDOWS = detect_dll(COINCURVE_ROOT_DIR)

MAKE = 'gmake' if platform.system() in ['FreeBSD', 'OpenBSD'] else 'make'

# IMPORTANT: keep in sync with .github/workflows/build.yml
#
# Version of libsecp256k1 to download if none exists in the `libsecp256k1` directory
UPSTREAM_REF = os.getenv('COINCURVE_UPSTREAM_TAG') or '1ad5185cd42c0636104129fcc9f6a4bf9c67cc40'

LIB_TARBALL_URL = f'https://github.com/bitcoin-core/secp256k1/archive/{UPSTREAM_REF}.tar.gz'

# We require setuptools >= 3.3
if [int(i) for i in setuptools_version.split('.', 2)[:2]] < [3, 3]:
    raise SystemExit(
        f'Your setuptools version ({setuptools_version}) is too old to correctly install this package. Please upgrade '
        f'to a newer version (>= 3.3).'
    )


def download_library(command):
    if command.dry_run:
        return
    libdir = absolute('libsecp256k1')
    if os.path.exists(os.path.join(libdir, 'autogen.sh')):
        # Library already downloaded
        return
    if not os.path.exists(libdir):
        import logging

        command.announce('downloading libsecp256k1 source code', level=logging.INFO)
        try:
            import requests
            try:
                r = requests.get(LIB_TARBALL_URL, stream=True, timeout=10)
                status_code = r.status_code
                if status_code == 200:
                    content = BytesIO(r.raw.read())
                    content.seek(0)
                    with tarfile.open(fileobj=content) as tf:
                        dirname = tf.getnames()[0].partition('/')[0]
                        tf.extractall()  # noqa: S202
                    shutil.move(dirname, libdir)
                else:
                    raise SystemExit('Unable to download secp256k1 library: HTTP-Status: %d', status_code)
            except requests.exceptions.RequestException as e:
                raise SystemExit('Unable to download secp256k1 library: %s', str(e))
        except ImportError as e:
            raise SystemExit('Unable to download secp256k1 library: %s', str(e))


package_data = {'coincurve': ['py.typed']}


def main():
    from setup_tools.commands import BdistWheel, EggInfo, Sdist, Develop
    from setup_tools.build_clib import BuildClib
    from setup_tools.build_ext import BuildCFFIForSharedLib, BuildExt

    if has_system_lib():

        class Distribution(_Distribution):
            def has_c_libraries(self):
                return not has_system_lib()

        extension = Extension(
            name='coincurve._libsecp256k1',
            sources=[os.path.join('coincurve', '_libsecp256k1.c')],
            # ABI?: py_limited_api=True,
        )

        extension.extra_compile_args = [
            subprocess.run(['pkg-config', '--cflags-only-I', 'libsecp256k1']).strip().decode('utf-8')  # noqa S603
        ]
        extension.extra_link_args = [
            subprocess.run(['pkg-config', '--libs-only-L', 'libsecp256k1']).strip().decode('utf-8'),  # noqa S603
            subprocess.run(['pkg-config', '--libs-only-l', 'libsecp256k1']).strip().decode('utf-8'),  # noqa S603
        ]

        if os.name == 'nt' or sys.platform == 'win32':
            # Apparently, the linker on Windows interprets -lxxx as xxx.lib, not libxxx.lib
            for i, v in enumerate(extension.__dict__.get('extra_link_args')):
                extension.__dict__['extra_link_args'][i] = v.replace('-L', '/LIBPATH:')

                if v.startswith('-l'):
                    v = v.replace('-l', 'lib')
                    extension.__dict__['extra_link_args'][i] = f'{v}.lib'

        setup_kwargs = dict(
            ext_modules=[extension],
            cmdclass={
                'build_clib': BuildClib,
                'build_ext': BuildCFFIForSharedLib,
                'develop': Develop,
                'egg_info': EggInfo,
                'sdist': Sdist,
                'bdist_wheel': BdistWheel,
            },
        )

    else:
        if BUILDING_FOR_WINDOWS:

            class Distribution(_Distribution):
                def is_pure(self):
                    return False

            package_data['coincurve'].append('libsecp256k1.dll')
            setup_kwargs = {}

        else:

            class Distribution(_Distribution):
                def has_c_libraries(self):
                    return not has_system_lib()

            setup_kwargs = dict(
                ext_package='coincurve',
                cffi_modules=['_cffi_build/build.py:ffi'],
                cmdclass={
                    'build_clib': BuildClib,
                    'build_ext': BuildExt,
                    'develop': Develop,
                    'egg_info': EggInfo,
                    'sdist': Sdist,
                    'bdist_wheel': BdistWheel,
                },
            )

    setup(
        name='coincurve',
        version='19.0.1',

        description='Cross-platform Python CFFI bindings for libsecp256k1',
        long_description=open('README.md', 'r').read(),
        long_description_content_type='text/markdown',
        author_email='Ofek Lev <oss@ofek.dev>',
        license='MIT OR Apache-2.0',

        python_requires='>=3.8',
        setup_requires=['cffi>=1.3.0'],
        install_requires=['asn1crypto', 'cffi>=1.3.0'],

        packages=find_packages(
            exclude=[
                'setup_tools',
                'tests',
            ]
        ),
        package_dir={'coincurve': 'coincurve'},
        package_data=package_data,

        distclass=Distribution,
        zip_safe=False,

        project_urls={
            'Documentation': 'https://ofek.dev/coincurve/',
            'Issues': 'https://github.com/ofek/coincurve/issues',
            'Source': 'https://github.com/ofek/coincurve',
        },
        keywords=[
            'secp256k1',
            'crypto',
            'elliptic curves',
            'bitcoin',
            'ethereum',
            'cryptocurrency',
        ],
        classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: MIT License',
            'License :: OSI Approved :: Apache Software License',
            'Natural Language :: English',
            'Operating System :: OS Independent',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.8',
            'Programming Language :: Python :: 3.9',
            'Programming Language :: Python :: 3.10',
            'Programming Language :: Python :: 3.11',
            'Programming Language :: Python :: 3.12',
            'Programming Language :: Python :: Implementation :: CPython',
            'Programming Language :: Python :: Implementation :: PyPy',
            'Topic :: Software Development :: Libraries',
            'Topic :: Security :: Cryptography',
        ],
        **setup_kwargs
    )


if __name__ == '__main__':
    main()
