"""Build the actual firmware rule core as a host shared library, no ESP32 SDK."""
from pathlib import Path
import os,subprocess,shutil
ROOT=Path(__file__).resolve().parents[1]

def build():
    compiler=shutil.which('g++')
    if not compiler:raise RuntimeError('g++ required. Install a native C++ compiler and add its bin directory to PATH.')
    out=ROOT/'firmware/tests/build';out.mkdir(exist_ok=True)
    target=out/('edge_rules.dll' if os.name=='nt' else 'libedge_rules.so')
    command=[compiler,'-std=c++17','-O2','-shared','-I'+str(ROOT/'firmware/include')]
    if os.name!='nt':command+=['-fPIC']
    command += [str(ROOT/'firmware/tests/native_rules.cpp'),'-o',str(target)]
    subprocess.run(command,check=True)
    return target
if __name__=='__main__':print(build())
