"""Local-first API for Daegu NetZero: calculations reuse the tested v1.5 engine."""
from __future__ import annotations
import io, json, os, sys, zipfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from factory_engine import Plant, recommend, sensitivity, audit
from evidence_features import company_comparison, economics, range_evaluation
from process_extraction import extract_rules, heat_balance, cap_recovery_fuel_mwh
from official_energy import load_official

app=FastAPI(title='Daegu NetZero API',version='1.9.1-local')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173','http://127.0.0.1:5173','http://localhost:8504'],allow_methods=['GET','POST'],allow_headers=['*'])

class PlantInput(BaseModel):
    gas_m3:float=Field(120000,ge=0,le=1e11)
    electricity_mwh:float=Field(550,ge=0,le=1e10)
    target_pct:float=Field(10,ge=0,le=100)
    extra_electricity_cap_mwh:float=Field(110,ge=0,le=1e10)
    gas_kwh_m3:float=Field(10.5,gt=1,le=100)
    gas_ef_kg_kwh:float=Field(.202,ge=0,le=10)
    grid_ef_kg_kwh:float=Field(.4,ge=0,le=10)
    heat_share:float=Field(.7,ge=0,le=1)
    efficiency_max:float=Field(.12,ge=0,le=1)
    recovery_max:float=Field(.18,ge=0,le=1)
    electrifiable_max:float=Field(.3,ge=0,le=1)
    boiler_efficiency:float=Field(.85,gt=0,le=1)
    cop:float=Field(2.8,gt=1,le=30)
    recovery_cap_fuel_mwh:Optional[float]=Field(None,ge=0)
    gas_price:float=Field(650,ge=0)
    electricity_price:float=Field(140,ge=0)
    investment_low:float=Field(30,ge=0)
    investment_mid:float=Field(70,ge=0)
    investment_high:float=Field(150,ge=0)

class ExtractInput(BaseModel):
    text:str=Field(max_length=4500)
    method:str='rules'

class HeatInput(BaseModel):
    values:dict
    approach_c:float=Field(10,gt=0,lt=100)
    recovery_fraction:float=Field(.7,ge=0,le=1)
    boiler_efficiency:float=Field(.85,gt=0,le=1)
    gas_m3:float=Field(120000,ge=0)
    gas_kwh_m3:float=Field(10.5,gt=1)
    heat_share:float=Field(.7,ge=0,le=1)

def analyze(data:PlantInput):
    settings=data.model_dump()
    for key in ('target_pct','gas_price','electricity_price','investment_low','investment_mid','investment_high'):
        settings.pop(key)
    p=Plant(**settings)
    opt=recommend(p,data.target_pct)
    c=opt['chosen']; baseline=opt['baseline']
    stress=sensitivity(p,c,data.target_pct)
    low=max(0,data.efficiency_max*100*.6); recovery_low=max(0,data.recovery_max*100*.6)
    ranges=range_evaluation(p,c,data.target_pct,{
        'efficiency_max':[low,data.efficiency_max*100,min(100,data.efficiency_max*130)],
        'recovery_max':[recovery_low,data.recovery_max*100,min(100,data.recovery_max*130)],
        'electrifiable_max':[data.electrifiable_max*60,data.electrifiable_max*100,min(100,data.electrifiable_max*130)]
    })
    caps=sorted([data.investment_low,data.investment_mid,data.investment_high])
    cost=economics(p,c,data.gas_price,data.electricity_price,tuple(caps))
    try: region=company_comparison(p)
    except Exception as exc: region={'warning':str(exc)}
    return {
        'inputs':data.model_dump(),
        'feasible':opt['feasible'],'candidate_count':opt['candidate_count'],
        'target_tco2':opt['target_tco2'],'gap_tco2':opt['gap_tco2'],
        'baseline':baseline,'chosen':c,'stress':stress.to_dict('records'),
        'ranges':ranges.to_dict('records'),'scenario_method':('공정 승인 시 회수연료 상한 × 0.6/1.0/1.2 및 다른 기술 잠재율 가정' if p.recovery_cap_fuel_mwh is not None else '기술 잠재율 최소·기준·최대 가정'), 'economics':{
            'annual_net_krw':cost['annual_net_krw'],'gas_saved_m3':cost['gas_saved_m3'],
            'table':json.loads(cost['table'].to_json(orient='records',force_ascii=False))},
        'region':region,'audit':audit(p,c),
        'alternatives':opt['table'].sort_values(['목표 충족','연간 순감축(tCO₂)'],ascending=[False,False]).head(8).to_dict('records'),
        'disclaimer':'기업 입력/가상값과 가정 기술계수로 산출한 조건부 계산. 대구 전체 감축량 또는 실제 설비 성능이 아닙니다.'
    }

@app.post('/api/analyze')
def analyze_route(data:PlantInput):
    try:return analyze(data)
    except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc))

@app.post('/api/extract')
def extract_route(data:ExtractInput):
    try:
        if data.method!='rules':raise ValueError('로컬 규칙 추출만 지원합니다.')
        vals=extract_rules(data.text)
        return {'values':vals,'source':data.method,'confirmed':False}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/heat')
def heat_route(data:HeatInput):
    try:
        r=heat_balance(data.values,data.approach_c,data.recovery_fraction)
        fuel=data.gas_m3*data.gas_kwh_m3/1000
        r['recovery_cap_fuel_mwh']=cap_recovery_fuel_mwh(r['annual_recovered_heat_mwh'],data.boiler_efficiency,fuel,data.heat_share)
        r['confirmed_input_only']=True
        return r
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.get('/api/health')
def health_route():
    return {'status':'ok','mode':'local-rules'}

@app.get('/api/region')
def region_route():
    e,g=load_official()
    return {'electricity':e[['year','category','mwh']].to_dict('records'),'gas':g[['year','category','thousand_m3']].to_dict('records'),
            'source':'대구 북구 탄소중립 기본계획 표 3-38·3-40 (원출처 KOSIS 재수록)',
            'caveat':'대구 전체 용도별 통계이며 개별 기업 또는 동종업종 평균이 아닙니다. 원 KOSIS 대조 미완료.'}

class ReportInput(BaseModel):
    analysis:PlantInput
    process:Optional[dict]=None
@app.post('/api/report')
def report_route(data:ReportInput):
    result=analyze(data.analysis)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('01_진단결과.json',json.dumps(result,ensure_ascii=False,indent=2))
        z.writestr('02_확인한_공정조건.json',json.dumps(data.process or {},ensure_ascii=False,indent=2))
        z.writestr('03_검토안내.txt','본 결과는 입력한 연료·전력 사용량과 가정한 기술 잠재량의 조건부 산정입니다.\n실제 사업장 적용 전 계측, 투자비 견적, 설비제약 및 공공데이터의 원자료 확인이 필요합니다.\n공정정보는 이 서버에 별도 저장하지 않지만 웹서버·호스팅의 로그 정책은 별도입니다.\n')
    stream.seek(0)
    return StreamingResponse(stream,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="daegu_netzero_report.zip"'})

FRONT=ROOT/'frontend'/'dist'
@app.get('/')
def index():
    f=FRONT/'index.html'
    if not f.exists(): return {'message':'React UI is not built. Run npm install && npm run build in frontend directory.'}
    return FileResponse(f)
from fastapi.staticfiles import StaticFiles
if (FRONT/'assets').exists():app.mount('/assets',StaticFiles(directory=str(FRONT/'assets')),name='assets')
