# build_f2p.py
import os
import subprocess
import sys
import shutil

def build():
    
    mk_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(mk_dir)   
    dist_dir = os.path.join(root_dir, 'dist')
    build_dir = os.path.join(root_dir, 'build')      

    
    spec_file = os.path.join(mk_dir, 'f2p.spec')
    if not os.path.exists(spec_file):
        print("ERROR: f2p.spec not found in mk directory!")
        sys.exit(1)
    
    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)

    pyinstaller_cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--workpath', build_dir,
        '--distpath', dist_dir,
        '--noconfirm',
        os.path.join(mk_dir, 'f2p.spec') 
    ]
    
    subprocess.run(pyinstaller_cmd, cwd=root_dir, check=True)
    print("Build finished. Executable is in ./dist/GFLH-F2P/")

if __name__ == "__main__":
    build()