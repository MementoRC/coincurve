import logging
import os
import pathlib
import platform
import shutil

from _config import MAKE
from _support import (
    absolute_from_setup_dir,
    download_library,
    execute_command_with_temp_log,
    has_system_lib,
)
from setuptools.command import build_clib


class BuildClibWithCmake(build_clib.build_clib):
    def __init__(self, dist):
        super().__init__(dist)
        self.pkgconfig_dir = None

    def get_source_files(self):
        # Ensure library has been downloaded (sdist might have been skipped)
        if not has_system_lib():
            download_library(self)

        # This seems to create issues in MANIFEST.in
        return [f for _, _, fs in os.walk(absolute_from_setup_dir('libsecp256k1')) for f in fs]

    def run(self):
        if has_system_lib():
            logging.info('Using system library')
            return

        logging.info('SECP256K1 C library build (CMake):')

        cwd = pathlib.Path().cwd()
        build_temp = os.path.abspath(self.build_temp)
        os.makedirs(build_temp, exist_ok=True)

        lib_src = os.path.join(cwd, 'libsecp256k1')

        install_dir = str(build_temp).replace('temp', 'lib')
        install_dir = os.path.join(install_dir, 'coincurve')

        if not os.path.exists(lib_src):
            # library needs to be downloaded
            self.get_source_files()

        cmake_args = [
            '-DCMAKE_BUILD_TYPE=Release',
            f'-DCMAKE_INSTALL_PREFIX={install_dir}',
            '-DBUILD_SHARED_LIBS=ON',
            '-DSECP256K1_BUILD_BENCHMARKS=OFF',
            '-DSECP256K1_BUILD_TESTS=ON',
            '-DSECP256K1_ENABLE_MODULE_ECDH=ON',
            '-DSECP256K1_ENABLE_MODULE_RECOVERY=ON',
            '-DSECP256K1_ENABLE_MODULE_SCHNORRSIG=ON',
            '-DSECP256K1_ENABLE_MODULE_EXTRAKEYS=ON',
        ]

        if (x_host := os.environ.get('COINCURVE_CROSS_HOST')) is not None:
            logging.info(f'Cross-compiling for {x_host}:{os.name}')
            if platform.system() == 'Darwin' or platform.machine() == 'arm64':
                # Let's try to not cross-compile on MacOS
                cmake_args.append('-DCMAKE_OSX_ARCHITECTURES=arm64')
            else:
                # Note, only 2 toolchain files are provided (2/1/24)
                cmake_args.append(f'-DCMAKE_TOOLCHAIN_FILE=../cmake/{x_host}.toolchain.cmake')

        elif os.name == 'nt':
            # For windows, select the correct toolchain file
            cmake_args.append('-G "Visual Studio 16 2019" -A x64')

        logging.info('    cmake config')
        execute_command_with_temp_log(['cmake', '-S', lib_src, '-B', build_temp, *cmake_args])

        try:
            os.chdir(build_temp)
            logging.info('    cmake build')
            execute_command_with_temp_log(['cmake', '--build', '.'])

            logging.info('    cmake install')
            execute_command_with_temp_log(['cmake', '--install', '.'], debug=True)
        finally:
            os.chdir(cwd)

        self.pkgconfig_dir = [
            os.path.join(install_dir, 'lib', 'pkgconfig'),
            os.path.join(install_dir, 'lib64', 'pkgconfig'),
        ]
        os.environ['PKG_CONFIG_PATH'] = f'{":".join(self.pkgconfig_dir)}:{os.environ.get("PKG_CONFIG_PATH", "")}'

        logging.info('build_clib: Done')


class BuildClib(build_clib.build_clib):
    def __init__(self, dist):
        super().__init__(dist)
        self.pkgconfig_dir = None

    def get_source_files(self):
        # Ensure library has been downloaded (sdist might have been skipped)
        if not has_system_lib():
            download_library(self)

        # This seems to create issues in MANIFEST.in
        return [f for _, _, fs in os.walk(absolute_from_setup_dir('libsecp256k1')) for f in fs]

    def run(self):
        if has_system_lib():
            logging.info('Using system library')
            return

        logging.info('SECP256K1 C library build (make):')

        cwd = pathlib.Path().cwd()
        build_temp = os.path.abspath(self.build_temp)
        os.makedirs(build_temp, exist_ok=True)

        lib_src = os.path.join(cwd, 'libsecp256k1')

        install_dir = str(build_temp).replace('temp', 'lib')
        install_dir = os.path.join(install_dir, 'coincurve')

        if not os.path.exists(lib_src):
            # library needs to be downloaded
            self.get_source_files()

        autoreconf = 'autoreconf -if --warnings=all'
        bash = shutil.which('bash')

        logging.info('    autoreconf')
        execute_command_with_temp_log([bash, '-c', autoreconf], cwd=lib_src)

        # Keep downloaded source dir pristine (hopefully)
        try:
            os.chdir(build_temp)
            cmd = [
                absolute_from_setup_dir('libsecp256k1/configure'),
                '--prefix',
                install_dir.replace('\\', '/'),
                '--disable-static',
                '--disable-dependency-tracking',
                '--with-pic',
                '--enable-module-extrakeys',
                '--enable-module-recovery',
                '--enable-module-schnorrsig',
                '--enable-experimental',
                '--enable-module-ecdh',
                '--enable-benchmark=no',
                '--enable-tests=no',
                '--enable-exhaustive-tests=no',
            ]

            if 'COINCURVE_CROSS_HOST' in os.environ:
                cmd.append(f"--host={os.environ['COINCURVE_CROSS_HOST']}")

            logging.info('    configure')
            execute_command_with_temp_log([bash, '-c', ' '.join(cmd)])

            logging.info('    make')
            execute_command_with_temp_log([MAKE])

            logging.info('    make check')
            execute_command_with_temp_log([MAKE, 'check'])

            logging.info('    make install')
            execute_command_with_temp_log([MAKE, 'install'])
        finally:
            os.chdir(cwd)

        self.pkgconfig_dir = os.path.join(install_dir, 'lib', 'pkgconfig')

        logging.info('build_clib: Done')
