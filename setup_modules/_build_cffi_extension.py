import logging
import os
import sys

from _support import absolute_from_setup_dir, build_flags, execute_command_with_temp_log
from setuptools.command import build_ext


class _BuildExtensionFromCFFI(build_ext.build_ext):
    static_lib = None

    def update_link_args(self, libraries, libraries_dirs, extra_link_args):
        raise NotImplementedError('update_link_args')

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

        # PKG_CONFIG_PATH is updated by build_clib if built locally
        ext.include_dirs.extend(build_flags('libsecp256k1', 'I'))
        ext.library_dirs.extend(build_flags('libsecp256k1', 'L'))

        libraries = build_flags('libsecp256k1', 'l')
        logging.info(f'  Libraries:{libraries}')

        # We do not set ext.libraries, this would add the default link instruction
        # Instead, we use extra_link_args to customize the link command
        self.update_link_args(libraries, ext.library_dirs, ext.extra_link_args)

        super().build_extension(ext)


class _BuildCFFI(_BuildExtensionFromCFFI):
    def build_extension(self, ext):
        logging.info(f'Cmdline CFFI build:' f'\n     C-file target: {ext.sources[0]}')

        build_script = absolute_from_setup_dir(os.path.join('_cffi_build', 'build.py'))

        build_dir = os.path.join(self.build_temp, 'cffi_build')
        os.makedirs(build_dir, exist_ok=True)
        for i, c_file in enumerate(ext.sources):
            # Extract filename from path
            c_file = os.path.join(build_dir, os.path.basename(c_file))
            cmd = [sys.executable, build_script, c_file, '1' if self.static_lib else '0']
            execute_command_with_temp_log(cmd)

            # Update the location of the C-file (built in the temp dir) for it compilation
            # in the next step of the Extension build
            ext.sources[i] = c_file

        super().build_extension(ext)
        logging.info('   CFFI C-file build: Done')


class BuildCFFIForSharedLib(_BuildCFFI):
    static_lib = False

    def update_link_args(self, libraries, libraries_dirs, extra_link_args):
        if self.compiler.__class__.__name__ == 'UnixCCompiler':
            extra_link_args.extend([f'-l{lib}' for lib in libraries])
            if sys.platform == 'darwin':
                # It seems that the syntax may be: -Wl,-rpath,@loader_path/lib
                extra_link_args.extend(
                    [
                        # f'-Wl,-rpath,{self.build_lib}/lib',
                        '-Wl,-rpath,@loader_path/lib',
                    ]
                )
            else:
                extra_link_args.extend(
                    [
                        '-Wl,-rpath,$ORIGIN/lib',
                        '-Wl,-rpath,$ORIGIN/lib64',
                    ]
                )
        elif self.compiler.__class__.__name__ == 'MSVCCompiler':
            # This section is not used yet since we still cross-compile on Windows
            # TODO: write the windows native build here when finalized
            raise NotImplementedError(f'Unsupported compiler: {self.compiler.__class__.__name__}')
        else:
            raise NotImplementedError(f'Unsupported compiler: {self.compiler.__class__.__name__}')


class BuildCFFIForStaticLib(_BuildCFFI):
    static_lib = True

    def update_link_args(self, libraries, libraries_dirs, extra_link_args):
        if self.compiler.__class__.__name__ == 'UnixCCompiler':
            # It is possible that the library was compiled without fPIC option
            for lib in libraries:
                # On MacOS the mix static/dynamic option is different
                # It requires a -force_load <full_lib_path> option for each library
                if sys.platform == 'darwin':
                    for lib_dir in libraries_dirs:
                        if os.path.exists(os.path.join(lib_dir, f'lib{lib}.a')):
                            extra_link_args.extend(['-Wl,-force_load', os.path.join(lib_dir, f'lib{lib}.a')])
                            break
                else:
                    extra_link_args.extend(['-Wl,-Bstatic', f'-l{lib}', '-Wl,-Bdynamic'])

        elif self.compiler.__class__.__name__ == 'MSVCCompiler':
            # This section is not used yet since we still cross-compile on Windows
            # TODO: write the windows native build here when finalized
            raise NotImplementedError(f'Unsupported compiler: {self.compiler.__class__.__name__}')
        else:
            raise NotImplementedError(f'Unsupported compiler: {self.compiler.__class__.__name__}')
