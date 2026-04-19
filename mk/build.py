# mk/build.py
import os
import sys
import subprocess
import shutil

def build():
    mk_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(mk_dir)
    dist_dir = os.path.join(root_dir, 'dist')
    build_dir = os.path.join(root_dir, 'build')
    
    if os.path.exists(dist_dir): shutil.rmtree(dist_dir)
    if os.path.exists(build_dir): shutil.rmtree(build_dir)

    pyinstaller_cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--workpath', build_dir,
        '--distpath', dist_dir,
        '--noconfirm',
        os.path.join(mk_dir, 'app.spec')
    ]
    
    subprocess.run(pyinstaller_cmd, cwd=root_dir, check=True)

    sample_src = os.path.join(mk_dir, 'Sample_config.json')
    if os.path.exists(sample_src):
        
        exe_dir = os.path.join(dist_dir, 'GFLH')  
        if not os.path.exists(exe_dir):
            
            exe_dir = dist_dir
        shutil.copy2(sample_src, exe_dir)
        print(f"[INFO] Copied sample config to {exe_dir}")
    else:
        print("[WARN] Sample_config.json not found, skip copy.")

if __name__ == '__main__':
    build()