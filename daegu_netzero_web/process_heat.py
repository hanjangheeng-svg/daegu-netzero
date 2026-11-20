"""Thermodynamically bounded preliminary heat integration & electrification.
All figures are conditional engineering examples, never Daegu factory measurements.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math
import pandas as pd

REQUIRED = ('name','kind','supply_c','target_c','capacity_kw_k')

@dataclass(frozen=True)
class EngineeringInputs:
    delta_t_min_c: float = 10.0
    recovery_realization: float = .70
    boiler_efficiency: float = .85
    source_c: float = 35.0
    heat_pump_supply_c: float = 95.0
    heat_pump_carnot_fraction: float = .46
    heat_pump_heat_fraction: float = .35
    max_hp_supply_c: float = 110.0
    hp_approach_c: float = 5.0
    annual_hours: float = 6000.0
    gas_kg_co2_kwh: float = .202
    grid_kg_co2_kwh: float = .40

EXAMPLE_STREAMS = pd.DataFrame([
    {'name':'염색 배출수','kind':'hot','supply_c':90.0,'target_c':35.0,'capacity_kw_k':5.5},
    {'name':'건조 배기','kind':'hot','supply_c':160.0,'target_c':65.0,'capacity_kw_k':2.5},
    {'name':'급수 예열','kind':'cold','supply_c':20.0,'target_c':80.0,'capacity_kw_k':4.0},
    {'name':'염색 용수','kind':'cold','supply_c':25.0,'target_c':95.0,'capacity_kw_k':3.0},
    {'name':'공정 가열','kind':'cold','supply_c':75.0,'target_c':135.0,'capacity_kw_k':2.2},
])

def validate_streams(frame: pd.DataFrame) -> pd.DataFrame:
    missing=set(REQUIRED)-set(frame.columns)
    if missing: raise ValueError('필수 열 누락: '+', '.join(sorted(missing)))
    d=frame.loc[:,REQUIRED].copy()
    if d.empty: raise ValueError('최소 1개의 열흐름이 필요합니다.')
    d['name']=d['name'].astype(str).str.strip()
    d['kind']=d['kind'].astype(str).str.lower().str.strip()
    if d['name'].eq('').any() or d['name'].duplicated().any(): raise ValueError('열흐름 이름은 비어 있거나 중복되면 안 됩니다.')
    if not d['kind'].isin(['hot','cold']).all(): raise ValueError('kind는 hot 또는 cold로 입력하세요.')
    for col in ['supply_c','target_c','capacity_kw_k']:
        d[col]=pd.to_numeric(d[col],errors='coerce')
        if not d[col].map(math.isfinite).all(): raise ValueError(col+'에 유효한 숫자를 입력하세요.')
    if (d['capacity_kw_k']<=0).any(): raise ValueError('열용량유량은 0보다 커야 합니다.')
    hot=d.kind=='hot';cold=~hot
    if not (d.loc[hot,'supply_c']>d.loc[hot,'target_c']).all(): raise ValueError('hot 흐름은 공급온도가 목표온도보다 높아야 합니다.')
    if not (d.loc[cold,'supply_c']<d.loc[cold,'target_c']).all(): raise ValueError('cold 흐름은 목표온도가 공급온도보다 높아야 합니다.')
    if not hot.any() or not cold.any(): raise ValueError('최소 1개의 hot 흐름과 1개의 cold 흐름이 필요합니다.')
    return d

def pinch_targets(streams: pd.DataFrame, delta_t_min_c: float=10.0) -> dict:
    """Minimum utilities from shifted-temperature heat cascade, no exchanger-network guarantee."""
    d=validate_streams(streams)
    if not 0 <= delta_t_min_c <= 100: raise ValueError('최소 접근온도 범위를 확인하세요.')
    shift=delta_t_min_c/2
    intervals=[]
    for r in d.itertuples(index=False):
        lo=min(r.supply_c,r.target_c)+( -shift if r.kind=='hot' else shift)
        hi=max(r.supply_c,r.target_c)+( -shift if r.kind=='hot' else shift)
        intervals.append((r.kind,lo,hi,r.capacity_kw_k,r.name))
    levels=sorted({x for _,lo,hi,_,_ in intervals for x in (lo,hi)},reverse=True)
    rows=[]; cumulative=0.;min_cascade=0.
    for high,low in zip(levels[:-1],levels[1:]):
        middle=(high+low)/2
        net_cp=sum(cp*(1 if k=='hot' else -1) for k,lo,hi,cp,_ in intervals if lo < middle < hi)
        net_heat=net_cp*(high-low)
        cumulative+=net_heat;min_cascade=min(min_cascade,cumulative)
        rows.append({'upper_shifted_c':high,'lower_shifted_c':low,'net_capacity_kw_k':net_cp,'net_heat_kw':net_heat,'unadjusted_cascade_kw':cumulative})
    cold_kw=sum(r.capacity_kw_k*(r.target_c-r.supply_c) for r in d.itertuples(index=False) if r.kind=='cold')
    hot_kw=sum(r.capacity_kw_k*(r.supply_c-r.target_c) for r in d.itertuples(index=False) if r.kind=='hot')
    q_h_min=max(0.,-min_cascade)
    recovery=max(0.,min(cold_kw,hot_kw,cold_kw-q_h_min))
    q_c_min=max(0.,hot_kw-recovery)
    adjusted=[r['unadjusted_cascade_kw']+q_h_min for r in rows]
    pinch_candidates=[rows[i]['lower_shifted_c'] for i,v in enumerate(adjusted) if abs(v)<1e-7]
    return {'heating_demand_kw':cold_kw,'hot_available_kw':hot_kw,'heating_utility_min_kw':q_h_min,
            'cooling_utility_min_kw':q_c_min,'max_recoverable_kw':recovery,
            'pinch_shifted_c':pinch_candidates[0] if pinch_candidates else None,
            'intervals':pd.DataFrame(rows)}

def heat_pump_cop(settings:EngineeringInputs) -> float:
    evap=settings.source_c-settings.hp_approach_c+273.15
    cond=settings.heat_pump_supply_c+settings.hp_approach_c+273.15
    if evap<=0 or cond<=evap: raise ValueError('열원·공급온도를 확인하세요.')
    if not 0 < settings.heat_pump_carnot_fraction <= 1: raise ValueError('카르노 효율비는 (0,1] 범위입니다.')
    cop=settings.heat_pump_carnot_fraction*cond/(cond-evap)
    if cop<=1: raise ValueError('조건에 따른 COP가 1 이하입니다. 전기화 제안을 중단합니다.')
    return cop

def evaluate(streams:pd.DataFrame, s:EngineeringInputs) -> dict:
    if not 0<=s.recovery_realization<=1 or not 0<=s.heat_pump_heat_fraction<=1: raise ValueError('도입 비율은 0~1입니다.')
    if not 0<s.boiler_efficiency<=1 or s.annual_hours<=0: raise ValueError('보일러 효율과 운전시간을 확인하세요.')
    if s.gas_kg_co2_kwh<0 or s.grid_kg_co2_kwh<0:raise ValueError('배출계수는 음수가 될 수 없습니다.')
    pinch=pinch_targets(streams,s.delta_t_min_c)
    base=pinch['heating_demand_kw']; recover=pinch['max_recoverable_kw']*s.recovery_realization
    remaining=max(0.,base-recover)
    # Conservative temperature-screening bound: only cold streams whose final target
    # is at or below the heat-pump supply temperature can be assigned HP duty.
    # Subtract all recovered heat from that eligible pool first to avoid claiming
    # unverified recovery allocation between high-/low-temperature sinks.
    d=validate_streams(streams)
    low_temp_cold_kw=sum(r.capacity_kw_k*(r.target_c-r.supply_c) for r in d.itertuples(index=False)
                         if r.kind=='cold' and r.target_c<=s.heat_pump_supply_c)
    eligible_base=low_temp_cold_kw*s.heat_pump_heat_fraction
    eligible=max(0.,low_temp_cold_kw-recover)*s.heat_pump_heat_fraction
    if s.heat_pump_supply_c>s.max_hp_supply_c and eligible>0:
        raise ValueError('설정된 히트펌프 최대 공급온도를 초과했습니다. 전기화 비율을 줄이거나 공급온도를 낮추세요.')
    cop=heat_pump_cop(s) if eligible>0 else None
    scenarios=[]
    for name,recovery_kw,hp_heat_kw in [
       ('기존 보일러',0.,0.),('폐열회수',recover,0.),
       ('히트펌프 전환',0.,eligible_base),('폐열회수 + 히트펌프',recover,eligible)]:
        residual=max(0.,base-recovery_kw)
        hp_heat=min(residual,hp_heat_kw)
        boiler_heat=residual-hp_heat
        gas_kwh=boiler_heat/s.boiler_efficiency*s.annual_hours
        hp_kwh=hp_heat/cop*s.annual_hours if cop else 0.
        emission_t=(gas_kwh*s.gas_kg_co2_kwh+hp_kwh*s.grid_kg_co2_kwh)/1000
        scenarios.append({'대안':name,'열회수_kW':recovery_kw,'히트펌프_열공급_kW':hp_heat,'보일러_열공급_kW':boiler_heat,
            '가스투입_MWh_년':gas_kwh/1000,'추가전력_MWh_년':hp_kwh/1000,'배출_tCO2_년':emission_t})
    table=pd.DataFrame(scenarios)
    baseline=table.iloc[0]['배출_tCO2_년']
    table['순감축_tCO2_년']=baseline-table['배출_tCO2_년']
    table['감축률_%']=100*table['순감축_tCO2_년']/baseline if baseline>0 else 0
    # Only process heat; not other plant loads, equipment manufacture, leakage, or grid system dispatch.
    return {'pinch':pinch,'options':table,'cop':cop,'recovery_actual_kw':recover,'baseline_t':baseline,
            'hp_eligible_after_recovery_kw':max(0.,low_temp_cold_kw-recover)}

def grid_sensitivity(streams:pd.DataFrame,s:EngineeringInputs,factors=(.1,.2,.35,.45,.6)) -> pd.DataFrame:
    from dataclasses import replace
    rows=[]
    for factor in factors:
        sub=evaluate(streams,replace(s,grid_kg_co2_kwh=factor))
        r=sub['options'].iloc[-1]
        rows.append({'전력배출계수_kg_kWh':factor,'연간순감축_tCO2':r['순감축_tCO2_년'],'감축률_%':r['감축률_%'],
                     '전기화순감축_양수':r['순감축_tCO2_년']>0})
    return pd.DataFrame(rows)

# AI must be evaluated only with actual observed equipment data. No synthetic "accuracy" claims.
def evaluate_observed_model(data:pd.DataFrame) -> dict:
    """Time-ordered holdout, leakage-safe baseline, require measured heat rather than synthetic labels."""
    needed={'flow_kg_h','inlet_c','outlet_c','cp_kj_kgk','measured_heat_kw'}
    if not needed.issubset(data.columns):raise ValueError('실측 AI 검증 입력에 필요한 열: '+', '.join(sorted(needed)))
    d=data.copy()
    features=['flow_kg_h','inlet_c','outlet_c','cp_kj_kgk']
    for col in features+['measured_heat_kw']:
        d[col]=pd.to_numeric(d[col],errors='coerce')
    d=d.dropna(subset=features+['measured_heat_kw'])
    if len(d)<60:raise ValueError('실측 시계열 데이터가 최소 60행 필요합니다. 현재 '+str(len(d))+'행')
    if (d['flow_kg_h']<0).any() or (d['cp_kj_kgk']<=0).any():raise ValueError('유량 및 비열을 확인하세요.')
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error
    split=int(len(d)*.8)
    xtr=d.iloc[:split][features];xte=d.iloc[split:][features]
    ytr=d.iloc[:split]['measured_heat_kw'];yte=d.iloc[split:]['measured_heat_kw']
    model=RandomForestRegressor(n_estimators=100,max_depth=8,min_samples_leaf=2,random_state=42,n_jobs=1)
    model.fit(xtr,ytr)
    pred=model.predict(xte)
    # physics baseline for sensible heating/cooling, absolute duty
    physics=(xte['flow_kg_h']*xte['cp_kj_kgk']*(xte['outlet_c']-xte['inlet_c']).abs()/3600).to_numpy()
    return {'n_train':len(xtr),'n_test':len(xte),'ai_mae_kw':float(mean_absolute_error(yte,pred)),
            'physics_mae_kw':float(mean_absolute_error(yte,physics)),
            'table':pd.DataFrame({'실측_kW':yte.to_numpy(),'AI예측_kW':pred,'열수지기준_kW':physics})}
