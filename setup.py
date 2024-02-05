import os.path
from os.path import join, dirname, abspath
from sys import path as PATH

from setuptools import Distribution as _Distribution, setup
from setuptools.extension import Extension

COINCURVE_ROOT = dirname(abspath(__file__))
PATH.append(COINCURVE_ROOT)

# Add setup_modules to the path to import the custom commands
PATH.insert(0, join(COINCURVE_ROOT, 'setup_modules'))
from _build_c_library import BuildClibWithCmake, BuildClib  # noqa
from _build_cffi_extension import BuildCFFIForSharedLib  # noqa
from _custom_commands import Develop, BdistWheel  # noqa
from _support import detect_dll, has_system_lib  # noqa

# IMPORTANT: keep in sync with .github/workflows/build.yml
#
# Version of libsecp256k1 to download if none exists in the `libsecp256k1` directory
UPSTREAM_REF = os.getenv('COINCURVE_UPSTREAM_TAG') or '1ad5185cd42c0636104129fcc9f6a4bf9c67cc40'
UPSTREAM_HSH = os.getenv('COINCURVE_UPSTREAM_HSH') or 'ba34be4319f505c5766aa80b99cfa696cbb2993bfecf7d7eb8696106c493cb8c'

LIB_TARBALL_URL = f'https://github.com/bitcoin-core/secp256k1/archive/{UPSTREAM_REF}.tar.gz'
LIB_TARBALL_HASH = f'{UPSTREAM_HSH}'
TAR_NAME = f'secp256k1-{UPSTREAM_REF}'
LIB_NAME = 'libsecp256k1'

BUILDING_FOR_WINDOWS = detect_dll()


def main():
    extension = Extension(
        name=f'coincurve._{LIB_NAME}',
        # This is necessary to define the Extension. The build process creates these files.
        # Their name is not critical, but it must be unique.
        sources=[f'_{LIB_NAME}.c'],
        py_limited_api=False,
    )

    globals_ = {}
    with open(join(COINCURVE_ROOT, 'src', 'coincurve', '_version.py')) as fp:
        exec(fp.read(), globals_)  # noqa S102
        __version__ = globals_['__version__']

    if has_system_lib():

        class Distribution(_Distribution):
            def has_c_libraries(self):
                return not has_system_lib()

        setup_kwargs = dict(
            setup_requires=['cffi>=1.3.0', 'requests'],
            ext_modules=[extension],
            cmdclass={
                'build_clib': BuildClib,
                'build_ext': BuildCFFIForSharedLib,
                'develop': Develop,
                'bdist_wheel': BdistWheel,
            },
        )

    else:
        if BUILDING_FOR_WINDOWS:

            class Distribution(_Distribution):
                def is_pure(self):
                    return False

            setup_kwargs = {}

        else:

            class Distribution(_Distribution):
                def has_c_libraries(self):
                    return not has_system_lib()

            setup_kwargs = dict(
                setup_requires=['cffi>=1.3.0', 'requests'],
                ext_modules=[extension],
                cmdclass={
                    'build_clib': BuildClibWithCmake,
                    'build_ext': BuildCFFIForSharedLib,
                    # 'develop': Develop,
                    'bdist_wheel': BdistWheel,
                },
            )

    setup(
        version=__version__,

        package_dir={'coincurve': 'src/coincurve'},

        distclass=Distribution,
        zip_safe=False,
        **setup_kwargs
    )


if __name__ == '__main__':
    main()
