import io, zipfile, json
from fastapi.testclient import TestClient
from backend.api import app

client=TestClient(app)
TEXT='폐수 입구온도 70℃, 냉각 목표온도 30℃, 폐수 유량 5m³/h. 급수 입구온도 20℃, 목표온도 55℃, 급수 유량 4m³/h. 연간 4000시간 동시 운전.'

def test_local_extract_only():
    r=client.post('/api/extract',json={'text':TEXT})
    assert r.status_code==200, r.text
    v=r.json()['values']
    assert r.json()['source']=='rules'
    assert v=={'source_in_c':70,'source_out_c':30,'source_flow_m3_h':5,'sink_in_c':20,'sink_target_c':55,'sink_flow_m3_h':4,'annual_hours':4000}
    assert client.post('/api/extract',json={'text':TEXT,'method':'llm'}).status_code==400

def test_full_flow_and_download():
    v=client.post('/api/extract',json={'text':TEXT}).json()['values']
    heat=client.post('/api/heat',json={'values':v}).json()
    assert round(heat['annual_recovered_heat_mwh'],1)==455.8
    b=client.post('/api/analyze',json={}).json()
    assert round(b['chosen']['net_reduction_tco2'],1)==49.6
    new={'recovery_cap_fuel_mwh':heat['recovery_cap_fuel_mwh']}
    a=client.post('/api/analyze',json=new).json()
    assert round(a['chosen']['net_reduction_tco2'],1)==54.2
    resp=client.post('/api/report',json={'analysis':new,'process':{'extracted':v,'heat':heat}})
    assert resp.status_code==200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        assert z.testzip() is None
        r=json.loads(z.read('01_진단결과.json'))
        process=json.loads(z.read('02_확인한_공정조건.json'))
        assert r['chosen']['net_reduction_tco2']==a['chosen']['net_reduction_tco2']
        assert process['heat']['annual_recovered_heat_mwh']==heat['annual_recovered_heat_mwh']
