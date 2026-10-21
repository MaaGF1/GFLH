# build_sandbox.py
import os
import sys
import subprocess
import shutil


def build():
    mk_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(mk_dir)
    dist_dir = os.path.join(root_dir, 'dist')
    build_dir = os.path.join(root_dir, 'build')

    spec_file = os.path.join(mk_dir, 'sandbox.spec')
    if not os.path.exists(spec_file):
        print("ERROR: sandbox.spec not found in mk directory!")
        return

    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)

    pyinstaller_cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--workpath', build_dir,
        '--distpath', dist_dir,
        '--noconfirm',
        spec_file,
    ]

    subprocess.run(pyinstaller_cmd, cwd=root_dir, check=True)
    print("Build finished. Executable is in ./dist/GFLH-Sandbox/")


if __name__ == "__main__":
    build()
