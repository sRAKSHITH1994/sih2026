"""Portable firmware checks using g++; invokes pytest for full Python/C++ parity."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    subprocess.run([sys.executable,str(ROOT/'scripts/build_native.py')],check=True)
    subprocess.run([sys.executable,'-m','pytest','backend/tests/test_native_parity.py','-q'],cwd=ROOT,check=True)
