import logging
import os
import os.path
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
from io import BytesIO

from setuptools import Distribution as _Distribution, setup, find_packages, __version__ as setuptools_version
from setuptools._distutils import log
from setuptools._distutils.errors import DistutilsError
from setuptools.command.build_clib import build_clib as _build_clib
from setuptools.command.build_ext import build_ext as _build_ext
from setuptools.command.develop import develop as _develop
from setuptools.command.dist_info import dist_info as _dist_info
from setuptools.command.egg_info import egg_info as _egg_info
from setuptools.command.sdist import sdist as _sdist
from setuptools.extension import Extension

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:
    _bdist_wheel = None

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from setup_support import absolute, detect_dll, has_system_lib, build_flags

BUILDING_FOR_WINDOWS = detect_dll()

MAKE = 'gmake' if platform.system() in ['FreeBSD', 'OpenBSD'] else 'make'

# IMPORTANT: keep in sync with .github/workflows/build.yml
#
# Version of libsecp256k1 to download if none exists in the `libsecp256k1` directory
UPSTREAM_REF = os.getenv('COINCURVE_UPSTREAM_TAG') or '1ad5185cd42c0636104129fcc9f6a4bf9c67cc40'

LIB_TARBALL_URL = f'https://github.com/bitcoin-core/secp256k1/archive/{UPSTREAM_REF}.tar.gz'

LIB_NAME = 'libsecp256k1'
PKG_NAME = 'coincurve'

# Helpers for compilation instructions
# Cross-compile for Windows/ARM64, Linux/ARM64, Darwin/ARM64, Windows/x86 (GitHub)
X_HOST = os.getenv('COINCURVE_CROSS_HOST')

SYSTEM = platform.system()  # supported: Windows, Linux, Darwin
MACHINE = platform.machine()  # supported: AMD64, x86_64

SECP256K1_BUILD = os.getenv('COINCURVE_SECP256K1_BUILD') or 'STATIC'

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
        command.announce('downloading libsecp256k1 source code', level=log.INFO)
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


class egg_info(_egg_info):
    def run(self):
        # Ensure library has been downloaded (sdist might have been skipped)
        if not has_system_lib():
            download_library(self)

        _egg_info.run(self)


class dist_info(_dist_info):
    def run(self):
        # Ensure library has been downloaded (sdist might have been skipped)
        if not has_system_lib():
            download_library(self)

        _dist_info.run(self)


class sdist(_sdist):
    def run(self):
        if not has_system_lib():
            download_library(self)
        _sdist.run(self)


if _bdist_wheel:

    class bdist_wheel(_bdist_wheel):
        def run(self):
            if not has_system_lib():
                download_library(self)
            _bdist_wheel.run(self)


else:
    bdist_wheel = None


class BuildClibWithCMake(_build_clib):
    title = 'SECP256K1 C library build'

    def __init__(self, dist):
        super().__init__(dist)
        self.pkgconfig_dir = None

        self._cwd = None
        self._lib_src = None
        self._install_dir = None
        self._install_lib_dir = None

    def get_source_files(self):
        # Ensure library has been downloaded (sdist might have been skipped)
        if not has_system_lib():
            download_library(self)

        # This seems to create issues in MANIFEST.in
        return [f for _, _, fs in os.walk(absolute(LIB_NAME)) for f in fs]

    def run(self):
        if has_system_lib():
            logging.info('Using system library')
            return

        logging.info(self.title)
        self.bc_set_dirs_download()
        self.bc_prepare_build(self._install_lib_dir, self.build_temp, self._lib_src)

        try:
            os.chdir(self.build_temp)
            subprocess.check_call(self.bc_build_command())  # noqa S603
        finally:
            os.chdir(self._cwd)

        # Register lib installation path
        self.bc_update_pkg_config_path()

    def bc_set_dirs_download(self):
        self._cwd = pathlib.Path().cwd()
        os.makedirs(self.build_temp, exist_ok=True)
        self._install_dir = str(self.build_temp).replace('temp', 'lib')

        if SECP256K1_BUILD == 'SHARED':
            # Install shared library in the package directory
            self._install_lib_dir = os.path.join(self._install_dir, PKG_NAME)
        else:
            # Install static library in its own directory for retrieval by build_ext
            self._install_lib_dir = os.path.join(
                self._install_dir.replace('lib', 'x_lib'), LIB_NAME
            )

        self._lib_src = os.path.join(self._cwd, LIB_NAME)
        if not os.path.exists(self._lib_src):
            self.get_source_files()

    def bc_update_pkg_config_path(self):
        self.pkgconfig_dir = [
            os.path.join(self._install_lib_dir, 'lib', 'pkgconfig'),
            os.path.join(self._install_lib_dir, 'lib64', 'pkgconfig'),
        ]
        os.environ['PKG_CONFIG_PATH'] = (
            f'{str(os.pathsep).join(self.pkgconfig_dir)}'
            f'{os.pathsep}'
            f'{os.getenv("PKG_CONFIG_PATH", "")}'
        ).replace('\\', '/')

        # Verify installation
        subprocess.check_call(['pkg-config', '--exists', LIB_NAME])  # noqa S603

    @staticmethod
    def _generator(msvc):
        if '2017' in str(msvc):
            return 'Visual Studio 15 2017'
        if '2019' in str(msvc):
            return 'Visual Studio 16 2019'
        if '2022' in str(msvc):
            return 'Visual Studio 17 2022'

    @staticmethod
    def bc_prepare_build(install_lib_dir, build_temp, lib_src):
        cmake_args = [
            '-DCMAKE_BUILD_TYPE=Release',
            f'-DCMAKE_INSTALL_PREFIX={install_lib_dir}',
            f'-DCMAKE_C_FLAGS={"-fPIC" if SECP256K1_BUILD != "SHARED" and SYSTEM != "Windows" else ""}',
            f'-DSECP256K1_DISABLE_SHARED={"OFF" if SECP256K1_BUILD == "SHARED" else "ON"}',
            '-DSECP256K1_BUILD_BENCHMARK=OFF',
            '-DSECP256K1_BUILD_TESTS=OFF',
            '-DSECP256K1_ENABLE_MODULE_ECDH=ON',
            '-DSECP256K1_ENABLE_MODULE_RECOVERY=ON',
            '-DSECP256K1_ENABLE_MODULE_SCHNORRSIG=ON',
            '-DSECP256K1_ENABLE_MODULE_EXTRAKEYS=ON',
        ]

        # Windows (more complex)
        if SYSTEM == 'Windows':
            vswhere = shutil.which('vswhere')
            cmd = [vswhere, '-latest', '-find', 'MSBuild\\**\\Bin\\MSBuild.exe']
            msvc = subprocess.check_output(cmd).strip().decode('utf-8')  # noqa S603

            # For windows x86/x64, select the correct architecture
            arch = 'x64' if MACHINE == 'AMD64' else 'Win32'  # Native

            if X_HOST is not None:
                logging.info(f'Cross-compiling on {SYSTEM}:{MACHINE} for {X_HOST}')
                if X_HOST in ['arm64', 'ARM64', 'x86']:
                    arch = 'Win32' if X_HOST in ['x86'] else 'arm64'
                else:
                    raise NotImplementedError(f'Unsupported architecture: {X_HOST}')

            # Place the DLL directly in the package directory
            cmake_args.append('-DCMAKE_INSTALL_BINDIR=.')
            cmake_args.extend(['-G', BuildClibWithCMake._generator(msvc), f'-A{arch}'])

        elif SYSTEM == 'Darwin':
            if X_HOST is None:
                cmake_args.append(
                    f'-DCMAKE_OSX_ARCHITECTURES={MACHINE}'  # Native
                )
            else:
                logging.info(f'Cross-compiling on {SYSTEM}:{MACHINE} for {X_HOST}')
                if X_HOST in ['armv7', 'armv7s', 'arm64', 'arm64e']:
                    cmake_args.append(
                        f'-DCMAKE_OSX_ARCHITECTURES={X_HOST}'
                    )
        else:
            if X_HOST is not None:
                if X_HOST not in [
                    'arm-linux-gnueabihf',
                    'x86_64-w64-mingw32',
                ]:
                    raise NotImplementedError(f'Unsupported architecture: {X_HOST}')

                logging.info(f'Cross-compiling on {SYSTEM}:{MACHINE} for {X_HOST}')
                cmake_args.append(
                    f'-DCMAKE_TOOLCHAIN_FILE=../cmake/{X_HOST}.toolchain.cmake'
                )

        logging.info('    Configure CMake')
        subprocess.check_call(['cmake', '-S', lib_src, '-B', build_temp, *cmake_args])  # noqa S603

    @staticmethod
    def bc_build_command():
        logging.info('    Install with CMake')
        return ['cmake', '--build', '.', '--target', 'install', '--config', 'Release', '--clean-first']


class SharedLinker(object):
    @staticmethod
    def update_link_args(compiler, libraries, libraries_dirs, extra_link_args):
        if compiler.__class__.__name__ == 'UnixCCompiler':
            extra_link_args.extend([f'-l{lib}' for lib in libraries])
            if sys.platform == 'darwin':
                extra_link_args.extend([
                    '-Wl,-rpath,@loader_path/lib',
                ])
            else:
                extra_link_args.extend([
                    '-Wl,-rpath,$ORIGIN/lib',
                    '-Wl,-rpath,$ORIGIN/lib64',
                ])
        elif compiler.__class__.__name__ == 'MSVCCompiler':
            for ld in libraries_dirs:
                ld = ld.replace('/', '\\')
                for lib in libraries:
                    lib_file = os.path.join(ld, f'lib{lib}.lib')
                    lib_path = [f'/LIBPATH:{ld}', f'lib{lib}.lib']
                    if os.path.exists(lib_file):
                        extra_link_args.extend(lib_path)
        else:
            raise NotImplementedError(f'Unsupported compiler: {compiler.__class__.__name__}')


class StaticLinker(object):
    @staticmethod
    def update_link_args(compiler, libraries, libraries_dirs, extra_link_args):
        if compiler.__class__.__name__ == 'UnixCCompiler':
            # It is possible that the library was compiled without fPIC option
            for lib in libraries:
                # On MacOS the mix static/dynamic option is different
                # It requires a -force_load <full_lib_path> option for each library
                if sys.platform == 'darwin':
                    for lib_dir in libraries_dirs:
                        if os.path.exists(os.path.join(lib_dir, f'lib{lib}.a')):
                            extra_link_args.extend(
                                ['-Wl,-force_load', os.path.join(lib_dir, f'lib{lib}.a')]
                            )
                            break
                else:
                    extra_link_args.extend(['-Wl,-Bstatic', f'-l{lib}', '-Wl,-Bdynamic'])

        elif compiler.__class__.__name__ == 'MSVCCompiler':
            for ld in libraries_dirs:
                ld = ld.replace('/', '\\')
                for lib in libraries:
                    lib_file = os.path.join(ld, f'lib{lib}.lib')
                    if os.path.exists(lib_file):
                        extra_link_args.append(lib_file)
        else:
            raise NotImplementedError(f'Unsupported compiler: {compiler.__class__.__name__}')


class BuildExtensionFromCFFI(_build_ext):
    static_lib = True if SECP256K1_BUILD == 'STATIC' else False

    def update_link_args(self, libraries, libraries_dirs, extra_link_args):
        if self.static_lib:
            StaticLinker.update_link_args(self.compiler, libraries, libraries_dirs, extra_link_args)
        else:
            SharedLinker.update_link_args(self.compiler, libraries, libraries_dirs, extra_link_args)

    def build_extension(self, ext):
        # Construct C-file from CFFI
        build_script = os.path.join('_cffi_build', 'build_shared.py')
        for i, c_file in enumerate(ext.sources):
            os.makedirs(self.build_temp, exist_ok=True)
            c_file = os.path.join(self.build_temp, os.path.basename(c_file))
            # This puts c-file a temp location (and not in the coincurve src directory)
            ext.sources[i] = c_file
            cmd = [sys.executable, build_script, c_file, '1' if self.static_lib else '0']
            subprocess.check_call(cmd)  # noqa S603

        # Enforce API interface
        ext.py_limited_api = False

        # Location of locally built library
        lib = 'libsecp256k1' if self.static_lib else 'coincurve'
        c_lib_pkg = os.path.join(self.build_lib.replace('lib', 'x_lib'), lib, 'lib', 'pkgconfig')
        if not os.path.isfile(os.path.join(c_lib_pkg, f'{LIB_NAME}.pc')) and not has_system_lib():
            raise RuntimeError(
                f'Library not found in {c_lib_pkg}, nor as a system lib({has_system_lib()}). '
                'Please check that the library was properly built.'
            )

        # PKG_CONFIG_PATH is updated by build_clib if built locally,
        # however, it would not work for a step-by-step build, thus we specify the lib path
        ext.extra_compile_args.extend([f'-I{build_flags(LIB_NAME, "I", c_lib_pkg)[0]}'])
        ext.library_dirs.extend(build_flags(LIB_NAME, 'L', c_lib_pkg))

        libraries = build_flags(LIB_NAME, 'l', c_lib_pkg)
        logging.info(f'  Libraries:{libraries}')

        # We do not set ext.libraries, this would add the default link instruction
        # Instead, we use extra_link_args to customize the link command
        self.update_link_args(libraries, ext.library_dirs, ext.extra_link_args)

        super().build_extension(ext)


class develop(_develop):
    def run(self):
        if not has_system_lib():
            raise DistutilsError(
                "This library is not usable in 'develop' mode when using the "
                'bundled libsecp256k1. See README for details.'
            )
        _develop.run(self)


def main():
    package_data = {'coincurve': ['py.typed']}

    extension = Extension(
        name='coincurve._libsecp256k1',
        sources=['_c_file_for_extension.c'],
        py_limited_api=False,
        extra_compile_args=['/d2FH4-'] if SYSTEM == 'Windows' else [],
    )

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
            ext_modules=[extension],
            cmdclass={
                'build_clib': BuildClibWithCMake,
                'build_ext': BuildExtensionFromCFFI,
                'develop': develop,
                'egg_info': egg_info,
                'sdist': sdist,
                'bdist_wheel': bdist_wheel,
            },
        )

    setup(
        name='coincurve',
        version='19.0.0',

        description='Cross-platform Python CFFI bindings for libsecp256k1',
        long_description=open('README.md', 'r').read(),
        long_description_content_type='text/markdown',
        author_email='Ofek Lev <oss@ofek.dev>',
        license='MIT OR Apache-2.0',

        python_requires='>=3.8',
        install_requires=['asn1crypto', 'cffi>=1.3.0'],

        packages=find_packages(exclude=('_cffi_build', '_cffi_build.*', LIB_NAME, 'tests')),
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
