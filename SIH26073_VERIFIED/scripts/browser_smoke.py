"""Exercise the unchanged production dist against a running local backend.
Optional dependency: playwright + Chromium. Use a disposable SIH_DB_PATH.
"""
import argparse,json,subprocess,sys,os,tempfile,time,atexit,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');parser.add_argument('--start-server',action='store_true');args=parser.parse_args()
    if args.start_server:
        temp=tempfile.TemporaryDirectory(prefix='sih_browser_');atexit.register(temp.cleanup)
        env={**os.environ,'SIH_DB_PATH':str(Path(temp.name)/'browser.db'),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(ROOT/'backend'),'--host','127.0.0.1','--port','8765'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def stop():process.terminate();process.wait(timeout=10)
        atexit.register(stop)
        for _ in range(200):
            try:
                urllib.request.urlopen(args.url+'/api/v1/health',timeout=1);break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('Disposable backend did not start')
    out=ROOT/'docs/verification';out.mkdir(parents=True,exist_ok=True);errors=[];result={}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100})
        page.on('pageerror',lambda e:errors.append(str(e)))
        response=page.goto(args.url);assert response.status==200
        result['served_original_html']=response.body()==(ROOT/'frontend/dist/index.html').read_bytes()
        page.get_by_role('button',name='Station Simulator',exact=True).click()
        page.get_by_role('button',name='Reset + one step',exact=True).click()
        page.wait_for_function("document.body.innerText.includes('SAMPLE 1')")
        page.screenshot(path=str(out/'frozen_simulator.png'),full_page=True)
        r=page.request.post(args.url+'/api/v1/simulation/step',data={'scenario':'electrical','steps':60,'reset':True})
        assert r.status==200,r.text();result['simulator_class']=r.json()['target']['packet']['local_brain']['fault_type']
        page.get_by_role('button',name='Hardware Integration',exact=True).click()
        page.wait_for_function("document.body.innerText.includes('SIMULATED')")
        page.screenshot(path=str(out/'frozen_hardware.png'),full_page=True)
        page.get_by_role('button',name='Live Intelligence',exact=True).click()
        page.wait_for_function("document.body.innerText.includes('GLOBAL BRAIN DECISION')")
        page.screenshot(path=str(out/'frozen_live.png'),full_page=True)
        page.get_by_role('button',name='Evaluation Criteria',exact=True).click()
        with page.expect_response(lambda r:'/api/v1/evaluation/run' in r.url,timeout=180000) as response:
            page.get_by_role('button',name='Run injected benchmark',exact=True).click()
        r=response.value;assert r.status==200,r.text();body=r.json()
        result['evaluation_compatible']=all(k in body for k in ['binary_metrics','latency','criteria','confusion','samples','warning','scenarios'])
        result['evaluation_samples']=body['samples'];result['native_rules_used']=body['native_rules_used']
        page.screenshot(path=str(out/'frozen_evaluation.png'),full_page=True)
        result['console_page_errors']=errors;assert not errors,errors
        result['pages_tested']=['Live Intelligence','Evaluation Criteria','Hardware Integration','Station Simulator']
        browser.close()
    (out/'browser_results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
