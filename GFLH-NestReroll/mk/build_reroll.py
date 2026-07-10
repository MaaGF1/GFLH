# build_reroll.py
import os
import sys
import subprocess
import shutil

def build():
    
    mk_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(mk_dir)   
    dist_dir = os.path.join(root_dir, 'dist')
    build_dir = os.path.join(root_dir, 'build')      

    
    spec_file = os.path.join(mk_dir, 'Nestreroll.spec')
    if not os.path.exists(spec_file):
        print("ERROR: Nestreroll.spec not found in mk directory!")
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
        os.path.join(mk_dir, 'NestReroll.spec') 
    ]
    
    subprocess.run(pyinstaller_cmd, cwd=root_dir, check=True)
    print("Build finished. Executable is in ./dist/RerollTool/")

if __name__ == "__main__":
    build()