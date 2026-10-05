"""Live synthetic HTTP smoke. Requires built frontend and seeded local DB."""
import httpx
import os
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
password = os.environ['DEMO_PASSWORD']
processes = [
    subprocess.Popen([str(root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')), '-m', 'uvicorn', 'campus_assistant.api.main:app', '--port', '8000'], cwd=root, env=dict(os.environ, PYTHONPATH=str(root / 'src')), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    subprocess.Popen(['node', 'build'], cwd=root / 'frontend', env=dict(os.environ, HOST='127.0.0.1', PORT='5173', ORIGIN='http://127.0.0.1:5173'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
]
try:
    for url in ['http://127.0.0.1:8000/health', 'http://127.0.0.1:5173/']:
        for _ in range(50):
            try:
                if httpx.get(url, trust_env=False).status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Service did not start')
    with httpx.Client(base_url='http://127.0.0.1:5173', follow_redirects=True, trust_env=False, headers={'accept': 'text/html', 'origin': 'http://127.0.0.1:5173'}) as web:
        assert web.post('/?/login', data={'username':'dosen','password':password}).status_code == 200
        token = web.cookies.get('campus_session')
        assert token
        cid = 'SMOKE-' + str(time.time_ns())
        assert web.post('/academic?/save',data={'op':'class','id':cid,'name':'Synthetic HTTP smoke class'}).status_code == 200
        assert web.post('/academic?/save',data={'op':'student','class_id':cid,'id':cid+'-S','name':'Synthetic HTTP student'}).status_code == 200
        academic = web.get('/academic',params={'class':cid})
        assert 'Synthetic HTTP student' in academic.text
        with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':f'Bearer {token}'},trust_env=False) as api:
            d = api.get(f'/classes/{cid}/academic').json()
            data = {'op':'scores','class_id':cid,'revision':d['revision'],**{f"score_{cid}-S_ASM-0{i}":str(70+i) for i in range(1,4)}}
            assert web.post('/academic?/save',data=data).status_code == 200
            assert api.get(f'/classes/{cid}/academic').json()['scores'][cid+'-S']['ASM-01'] == 71
            text=f'student_id,assessment_id,value\n{cid}-S,ASM-02,85\n'
            preview=web.post('/academic?/save',data={'op':'preview','class_id':cid},files={'file':('scores.csv',text,'text/csv')})
            assert preview.status_code == 200 and 'Preview valid' in preview.text
            assert api.get(f'/classes/{cid}/academic').json()['scores'][cid+'-S']['ASM-02'] == 72
        report = web.get('/reports',params={'class':cid})
        assert report.status_code == 200 and 'CPL-01' in report.text
        export = web.get('/reports/export',params={'class':cid})
        assert export.status_code == 200 and 'course_only' in export.text
        body={'class_id':cid,'baseline_hours_month':50,'new_work_hours_month':12,'review_hours_month':6,'correction_hours_month':2,'value_per_hour':100000,'monthly_operating_cost':1500000,'initial_cost':12000000,'horizon_months':12}
        assert '20.00%' in web.post('/reports?/scenario',data=body).text
        assert web.post('/?/logout',data={'submit':'1'}).status_code == 200
        assert not web.cookies.get('campus_session')
    print('HTTP admin smoke passed: class → student → scores → CSV preview → report/export → ROI scenario → logout')
finally:
    for process in processes:
        process.terminate()
        process.wait(timeout=5)
