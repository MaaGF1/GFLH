# build_pick_coin.py
import os
import subprocess
import sys
import shutil

def build():
    
    mk_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(mk_dir)   
    dist_dir = os.path.join(root_dir, 'dist')
    build_dir = os.path.join(root_dir, 'build')      

    
    spec_file = os.path.join(mk_dir, 'pick_coin.spec')
    if not os.path.exists(spec_file):
        print("ERROR: pick_coin.spec not found in mk directory!")
        return
    
    for d in ["dist", "build"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    pyinstaller_cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--workpath', build_dir,
        '--distpath', dist_dir,
        '--noconfirm',
        os.path.join(mk_dir, 'pick_coin.spec') 
    ]
    
    subprocess.run(pyinstaller_cmd, cwd=root_dir, check=True)
    print("Build finished. Executable is in ./dist/PickCoin/")

if __name__ == "__main__":
    build()