import logging
import os
import os.path
import pathlib
import platform
import shutil
import sys

from setuptools import Distribution as _Distribution, setup, find_packages
from setuptools.command import build_clib, build_ext, develop, dist_info, egg_info, sdist
from setuptools.extension import Extension

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:
    _bdist_wheel = None

PACKAGE_SETUP_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(PACKAGE_SETUP_DIR)
from setup_support import absolute_from_setup_dir, build_flags, detect_dll, download_library, has_system_lib, \
    execute_command_with_temp_log  # noqa: E402

BUILDING_FOR_WINDOWS = detect_dll()

MAKE = 'gmake' if platform.system() in ['FreeBSD', 'OpenBSD'] else 'make'
PKGCONFIG = shutil.which('pkg-config')

# IMPORTANT: keep in sync with .github/workflows/build.yml
#
# Version of libsecp256k1 to download if none exists in the `libsecp256k1` directory
UPSTREAM_REF = os.getenv('COINCURVE_UPSTREAM_TAG') or '1ad5185cd42c0636104129fcc9f6a4bf9c67cc40'
UPSTREAM_HSH = os.getenv('COINCURVE_UPSTREAM_HSH') or 'ba34be4319f505c5766aa80b99cfa696cbb2993bfecf7d7eb8696106c493cb8c'

LIB_TARBALL_URL = f'https://github.com/bitcoin-core/secp256k1/archive/{UPSTREAM_REF}.tar.gz'
LIB_TARBALL_HASH = f'{UPSTREAM_HSH}'

TAR_NAME = f'secp256k1-{UPSTREAM_REF}'
LIB_NAME = 'libsecp256k1'
PKG_NAME = 'coincurve'

_SECP256K1_BUILD_TYPE = 'SHARED'


class EggInfo(egg_info.egg_info):
    def run(self):
        # Ensure library has been downloaded (sdist might have been skipped)
        if not has_system_lib():
            download_library(self)

        super().run()


class DistInfo(dist_info.dist_info):
    def run(self):
        # Ensure library has been downloaded (sdist might have been skipped)
        if not has_system_lib():
            download_library(self)

        super().run()


class Sdist(sdist.sdist):
    def run(self):
        if not has_system_lib():
            download_library(self)
        super().run()


class Develop(develop.develop):
    def run(self):
        if not has_system_lib():
            raise RuntimeError(
                'This library is not usable in "develop" mode when using the '
                f'bundled {LIB_NAME}. See README for details.'
            )
        super().run()


if _bdist_wheel:
    class BdistWheel(_bdist_wheel):
        def run(self):
            if not has_system_lib():
                download_library(self)
            super().run()


class _BuildClib(build_clib.build_clib):
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
        return [f for _, _, fs in os.walk(absolute_from_setup_dir(LIB_NAME)) for f in fs]

    def run(self):
        if has_system_lib():
            logging.info('Using system library')
            return

        logging.info(self.title)
        self.bc_set_dirs_download()
        self.bc_prepare_build(self._install_lib_dir, self.build_temp, self._lib_src)

        try:
            os.chdir(self.build_temp)
            self.bc_build_in_temp(self._install_lib_dir, self._lib_src)
            execute_command_with_temp_log(self.bc_build_command(), debug=True)
        finally:
            os.chdir(self._cwd)

        # Register lib installation path
        self.bc_update_pkg_config_path()

    def bc_set_dirs_download(self):
        self._cwd = pathlib.Path().cwd()
        os.makedirs(self.build_temp, exist_ok=True)
        self._install_dir = str(self.build_temp).replace('temp', 'lib')
        self._install_lib_dir = os.path.join(self._install_dir, PKG_NAME)
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
            f'{os.environ.get("PKG_CONFIG_PATH", "")}'
        ).replace('\\', '/')

        # Verify installation
        execute_command_with_temp_log([PKGCONFIG, '--exists', LIB_NAME])

    @staticmethod
    def bc_prepare_build(install_lib_dir, build_temp, lib_src):
        raise NotImplementedError('This method should be implemented in a Mixin class')

    @staticmethod
    def bc_build_in_temp(install_lib_dir, lib_src):
        pass

    @staticmethod
    def bc_build_command():
        raise NotImplementedError('This method should be implemented in a Mixin class')


class BuildClibWithCMake(_BuildClib):
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
            f'-DCMAKE_C_FLAGS={"-fPIC" if _SECP256K1_BUILD_TYPE == "SHARED" and os.name != "nt" else "ON"}',
            f'-DSECP256K1_DISABLE_SHARED={"OFF" if _SECP256K1_BUILD_TYPE == "SHARED" else "ON"}',
            '-DSECP256K1_BUILD_BENCHMARK=OFF',
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
                cmake_args.append(
                    '-DCMAKE_OSX_ARCHITECTURES=arm64'
                )
            else:
                # Note, only 2 toolchain files are provided (2/1/24)
                cmake_args.append(
                    f'-DCMAKE_TOOLCHAIN_FILE=../cmake/{x_host}.toolchain.cmake'
                )

        elif os.name == 'nt':
            vswhere = shutil.which('vswhere')
            msvc = execute_command_with_temp_log(
                [vswhere, '-latest', '-find', 'MSBuild\\**\\Bin\\MSBuild.exe'],
                capture_output=True,
            )
            logging.info(f'Using MSVC: {msvc}')

            # For windows, select the correct toolchain file
            cmake_args.extend(['-G', BuildClibWithCMake._generator(msvc), '-Ax64'])

        logging.info('    Configure CMake')
        execute_command_with_temp_log(['cmake', '-S', lib_src, '-B', build_temp, *cmake_args])

    @staticmethod
    def bc_build_command():
        logging.info('    Install with CMake')
        return ['cmake', '--build', '.', '--target', 'install', '--config', 'Release', '--clean-first']


class BuildClibWithMake(_BuildClib):
    @staticmethod
    def bc_prepare_build(install_lib_dir, build_temp, lib_src):
        autoreconf = 'autoreconf -if --warnings=all'
        bash = shutil.which('bash')

        logging.info('    autoreconf')
        execute_command_with_temp_log([bash, '-c', autoreconf], cwd=lib_src)

    @staticmethod
    def bc_build_in_temp(install_lib_dir, lib_src):
        bash = shutil.which('bash')
        cmd = [
            os.path.join(lib_src, 'configure'),
            '--prefix',
            absolute_from_setup_dir(install_lib_dir.replace('\\', '/')),
            f'{"--enable-shared" if _SECP256K1_BUILD_TYPE == "SHARED" else "--enable-static"}',
            '--disable-dependency-tracking',
            '--with-pic',
            '--enable-module-extrakeys',
            '--enable-module-recovery',
            '--enable-module-schnorrsig',
            '--enable-experimental',
            '--enable-module-ecdh',
            '--enable-tests=no',
            '--enable-exhaustive-tests=no',
        ]

        if 'COINCURVE_CROSS_HOST' in os.environ:
            cmd.append(f"--host={os.environ['COINCURVE_CROSS_HOST']}")

        logging.info('    configure')
        execute_command_with_temp_log([bash, '-c', ' '.join(cmd)])

        logging.info('    make')
        execute_command_with_temp_log([MAKE])

        logging.info('    Clean')
        execute_command_with_temp_log([MAKE, 'clean'])

    @staticmethod
    def bc_build_command():
        logging.info('    Install with Make')
        return [MAKE, 'install']


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
            vswhere = shutil.which('vswhere')
            dumpbin = execute_command_with_temp_log(
                [vswhere, '-latest', '-find', '**\\bin\\dumpbin.exe'],
                capture_output=True,
            )
            dumpbin = dumpbin.decode('utf-8', errors='ignore').strip()
            logging.info(f'Using dumpin: {dumpbin}')

            for ld in libraries_dirs:
                ld = ld.replace('/', '\\')
                for lib in libraries:
                    lib_file = os.path.join(ld, f'lib{lib}.lib')
                    if os.path.exists(lib_file):
                        logging.info(f'    LIB: {lib_file}:{os.path.isfile(lib_file)}')
                        export = execute_command_with_temp_log(
                            [dumpbin, '-exports', lib_file],
                            capture_output=True,
                        )
                        logging.info(f'exports: {export}')
                        extra_link_args.append(lib_file)
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
            vswhere = shutil.which('vswhere')
            dumpbin = execute_command_with_temp_log(
                [vswhere, '-latest', '-find', '**\\bin\\dumpbin.exe'],
                capture_output=True,
            )
            dumpbin = dumpbin.decode('utf-8', errors='ignore').strip()
            logging.info(f'Using dumpin: {dumpbin}')

            for ld in libraries_dirs:
                ld = ld.replace('/', '\\')
                for lib in libraries:
                    lib_file = os.path.join(ld, f'lib{lib}.lib')
                    if os.path.exists(lib_file):
                        logging.info(f'    LIB: {lib_file}:{os.path.isfile(lib_file)}')
                        export = execute_command_with_temp_log(
                            [dumpbin, '-exports', lib_file],
                            capture_output=True,
                        )
                        logging.info(f'exports: {export}')
                        extra_link_args.append(lib_file)
        else:
            raise NotImplementedError(f'Unsupported compiler: {compiler.__class__.__name__}')


class _BuildExtensionFromCFFI(build_ext.build_ext):
    static_lib = True if _SECP256K1_BUILD_TYPE == 'STATIC' else False

    def update_link_args(self, libraries, libraries_dirs, extra_link_args):
        if self.static_lib:
            StaticLinker.update_link_args(self.compiler, libraries, libraries_dirs, extra_link_args)
        else:
            SharedLinker.update_link_args(self.compiler, libraries, libraries_dirs, extra_link_args)

    def build_extension(self, ext):
        logging.info(
            f'Extension build:'
            f'\n         OS:{os.name}'
            f'\n   Platform:{sys.platform}'
            f'\n   Compiler:{self.compiler.__class__.__name__}'
            f'\n     Static:{self.static_lib}'
        )

        # Enforce API interface
        ext.py_limited_api = False

        # Location of locally built library
        c_lib_pkg = os.path.join(self.build_lib, 'coincurve', 'lib', 'pkgconfig')

        # PKG_CONFIG_PATH is updated by build_clib if built locally
        # Do not override the CFFI C-file secp256k1.h with the one from the source distribution
        # ext.include_dirs.extend(build_flags(LIB_NAME, 'I', c_lib_pkg))
        ext.include_dirs.extend(build_flags(LIB_NAME, 'I', c_lib_pkg))
        ext.library_dirs.extend(build_flags(LIB_NAME, 'L', c_lib_pkg))

        libraries = build_flags(LIB_NAME, 'l', c_lib_pkg)
        logging.info(f'  Libraries:{libraries}')

        # We do not set ext.libraries, this would add the default link instruction
        # Instead, we use extra_link_args to customize the link command
        self.update_link_args(libraries, ext.library_dirs, ext.extra_link_args)

        super().build_extension(ext)


class _BuildCFFI(_BuildExtensionFromCFFI):
    def build_extension(self, ext):
        logging.info(
            f'Cmdline CFFI build:'
            f'\n     Source: {absolute_from_setup_dir(ext.sources[0])}'
        )

        build_script = os.path.join('_cffi_build', 'build.py')
        for c_file in ext.sources:
            logging.info(f'     Static: {self.static_lib}')
            # cmd = [sys.executable, build_script, c_file, '1' if self.static_lib else '0']
            # It seems that when compiling the C file generated by CFFI,
            # the compiler needs to use dllexport to prepare linking with the DLL
            cmd = [sys.executable, build_script, c_file, '1']
            logging.info(f'        CMD: {cmd}')
            execute_command_with_temp_log(cmd, debug=True)

        super().build_extension(ext)


class BuildCFFIExtension(_BuildCFFI):
    pass


package_data = {PKG_NAME: ['py.typed']}

extension = Extension(
    name=f'{PKG_NAME}._{LIB_NAME}',
    sources=[os.path.join(PKG_NAME, f'_{LIB_NAME}.c')],
    py_limited_api=False,
)

if has_system_lib():

    class Distribution(_Distribution):
        def has_c_libraries(self):
            return not has_system_lib()


    # TODO: This has not been tested yet. has_system_lib() does not find conda install lib yet
    setup_kwargs = dict(
        setup_requires=['cffi>=1.3.0', 'requests'],
        ext_modules=[extension],
        cmdclass={
            'build_clib': BuildClibWithMake,
            'build_ext': BuildCFFIExtension,
            'develop': Develop,
            'egg_info': EggInfo,
            'sdist': Sdist,
            'bdist_wheel': BdistWheel if _bdist_wheel else None,
        },
    )

else:
    if BUILDING_FOR_WINDOWS:

        class Distribution(_Distribution):
            def is_pure(self):
                return False


        package_data[PKG_NAME].append(f'{LIB_NAME}.dll')
        setup_kwargs = {}

    else:

        class Distribution(_Distribution):
            def has_c_libraries(self):
                return not has_system_lib()


        setup_kwargs = dict(
            setup_requires=['cffi>=1.3.0', 'requests'],
            ext_modules=[extension],
            cmdclass={
                'build_clib': BuildClibWithCMake,
                'build_ext': BuildCFFIExtension,
                'develop': Develop,
                'egg_info': EggInfo,
                'sdist': Sdist,
                'bdist_wheel': BdistWheel if _bdist_wheel else None,
            },
        )


def main():
    setup(
        name=PKG_NAME,
        version='19.0.0',

        packages=find_packages(exclude=('_cffi_build', '_cffi_build.*', LIB_NAME, 'tests')),
        package_data=package_data,

        distclass=Distribution,
        zip_safe=False,
        **setup_kwargs
    )


if __name__ == '__main__':
    main()
