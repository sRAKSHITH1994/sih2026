"""sizeof arrays and runEdgeML timing on held-out session features; host, not ESP32."""
from pathlib import Path
import sys,subprocess,json,platform,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge_training'))
from corpus import session,session_seed
from feature_pipeline import extract_sequence
if __name__=='__main__':
    out=ROOT/'firmware/tests/build';out.mkdir(exist_ok=True)
    binary=out/('benchmark.exe' if sys.platform=='win32' else 'benchmark')
    command=['g++','-std=c++17','-O2','-I'+str(ROOT/'firmware/tests/native_stub'),'-I'+str(ROOT/'firmware/include'),
      str(ROOT/'firmware/tests/native_benchmark.cpp'),str(ROOT/'firmware/src/edge_mlp.cpp'),str(ROOT/'firmware/src/feature_engine.cpp'),'-o',str(binary)]
    subprocess.run(command,check=True)
    rows=[]
    for cls in range(10):
        for n in range(3):
            raw,_,_=session(cls,session_seed('test',200,cls,n));rows.extend(extract_sequence(raw)[19:])
    text='\n'.join(' '.join(f'{v:.9g}' for v in row) for row in rows)+'\n'
    result=json.loads(subprocess.run([str(binary)],input=text,capture_output=True,text=True,check=True).stdout)
    result.update(platform=platform.platform(),compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
      build_command=command,model_header_text_bytes=(ROOT/'firmware/include/model_weights.h').stat().st_size,
      model_sha256=hashlib.sha256((ROOT/'edge_training/artifacts/edge_mlp.npz').read_bytes()).hexdigest(),
      scope='Host CPU g++ -O2 runEdgeML including normalization, class masking, softmax and gradient attribution. Excludes feature extraction, ESP32 timing and linker/firmware image overhead.',
      esp32_timing_measured=False)
    (ROOT/'backend/models/native_metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
