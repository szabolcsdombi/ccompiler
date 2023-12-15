import os
import subprocess
import sys


def get_env():
    program_files = os.environ['ProgramFiles(x86)']

    path = subprocess.check_output([
        os.path.join(program_files, 'Microsoft Visual Studio', 'Installer', 'vswhere.exe'),
        '-latest',
        '-prerelease',
        '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
        '-property', 'installationPath',
        '-products', '*',
    ], encoding='mbcs', errors='strict').strip()

    vcvarsall = os.path.join(path, 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')

    lines = subprocess.check_output(
        args=f'cmd /u /c "{vcvarsall}" x86_amd64 && set',
        stderr=subprocess.DEVNULL,
    ).decode('utf-16le', errors='replace')

    env = {
        key.lower(): value
        for key, _, value in
        (line.partition('=') for line in lines.splitlines())
        if key and value
    }

    return env


def find_exe(env, exe):
    paths = env['path'].split(os.pathsep)
    for p in paths:
        fn = os.path.join(os.path.abspath(p), exe)
        if os.path.isfile(fn):
            return os.path.normpath(fn)


class Compiler:
    def __init__(self, python=False):
        self.env = get_env()
        self.cc = find_exe(self.env, 'cl.exe')
        self.linker = find_exe(self.env, 'link.exe')
        self.lib = find_exe(self.env, 'lib.exe')
        self.rc = find_exe(self.env, 'rc.exe')

        self.temp = 'build'
        self.sources = []
        self.include_dirs = []
        self.library_dirs = []
        self.libraries = []
        self.macros = []
        self.exports = []

        self.compiler_preargs=[]
        self.compiler_postargs=[]

        self.linker_preargs=[]
        self.linker_postargs=[]

        self.compile_options = ['/nologo', '/Ox', '/W3', '/GL', '/DNDEBUG', '/MD']
        self.linker_options = ['/nologo', '/INCREMENTAL:NO', '/LTCG']

        self.error = lambda: exit(1)

        for path in self.env.get('include', '').split(os.pathsep):
            self.include_dirs.append(os.path.normpath(path))

        for path in self.env.get('lib', '').split(os.pathsep):
            self.library_dirs.append(os.path.normpath(path))

        if python:
            version = sys.version_info
            home = os.path.normpath(os.path.abspath(os.path.dirname(sys.executable)))
            self.include_dirs.append(os.path.join(home, 'include'))
            self.library_dirs.append(os.path.join(home, 'libs'))
            self.libraries.append(f'python{version.major}{version.minor}')

    def compile(self, output):
        if not os.path.isdir(self.temp):
            os.makedirs(self.temp)

        compile_options = []
        compile_options.extend(self.compiler_preargs)
        compile_options.append('/c')
        compile_options.extend(self.compile_options)

        for path in self.include_dirs:
            compile_options.append(f'-I{path}')

        for name, value in self.macros:
            compile_options.append(f'-D{name}' if value is None else f'-D{name}={value}')

        objects = []

        for i, src in enumerate(self.sources):
            obj = os.path.join(self.temp, f'{i}.res' if src.endswith('.rc') else f'{i}.obj')
            objects.append(obj)

            if src.endswith('.rc'):
                if subprocess.call([self.rc, f'/fo{obj}', src]):
                    return self.error()
                continue

            compile_args = [self.cc]
            compile_args.extend(compile_options)
            if src.endswith('.cpp'):
                compile_args.append('/EHsc')
            compile_args.append(f'/Tc{src}' if src.endswith('.c') else f'/Tp{src}')
            compile_args.append(f'/Fo{obj}')
            compile_args.extend(self.compiler_postargs)

            if subprocess.call(compile_args):
                return self.error()

        linker_args = [self.linker]
        linker_args.extend(self.linker_preargs)
        linker_args.extend(self.linker_options)

        for path in self.library_dirs:
            linker_args.append(f'/LIBPATH:{path}')

        for lib in self.libraries:
            linker_args.append(f'{lib}.lib')

        linker_args.extend(objects)

        for symbol in self.exports:
            linker_args.append(f'/EXPORT:{symbol}')

        linker_args.append(f'/OUT:{output}')
        linker_args.extend(self.linker_postargs)

        if subprocess.call(linker_args):
            return self.error()
