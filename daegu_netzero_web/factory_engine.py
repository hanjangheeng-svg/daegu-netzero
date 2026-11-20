"""Company-level screening, entirely separate from Daegu public regional statistics.

A factory baseline is either illustrative demo data or user-supplied meter/billing data.
The potential shares and conversion coefficients are *unverified user assumptions*.
Sequential fuel savings and incremental grid emissions ensure no double counting.
"""
from dataclasses import dataclass, asdict
from itertools import product
import math
import pandas as pd

@dataclass(frozen=True)
class Plant:
    gas_m3: float = 120000.
    electricity_mwh: float = 550.
    gas_kwh_m3: float = 10.5
    gas_ef_kg_kwh: float = .202
    grid_ef_kg_kwh: float = .4
    heat_share: float = .7
    efficiency_max: float = .12
    recovery_max: float = .18
    electrifiable_max: float = .3
    boiler_efficiency: float = .85
    cop: float = 2.8
    extra_electricity_cap_mwh: float = 110.
    recovery_cap_fuel_mwh: float | None = None

TECHS = ('효율 개선', '폐열회수', '저온열 전기화')

def validate(p: Plant):
    for k in ('gas_m3','electricity_mwh','gas_ef_kg_kwh','grid_ef_kg_kwh','extra_electricity_cap_mwh'):
        v=getattr(p,k)
        if not math.isfinite(v) or v < 0: raise ValueError(f'{k}은 0 이상의 유한한 수여야 합니다.')
    if p.recovery_cap_fuel_mwh is not None and (not math.isfinite(p.recovery_cap_fuel_mwh) or p.recovery_cap_fuel_mwh<0):
        raise ValueError('회수가능 연료 환산 상한은 0 이상의 유한한 수여야 합니다.')
    for k in ('gas_kwh_m3','cop'):
        v=getattr(p,k)
        if not math.isfinite(v) or v<=1: raise ValueError(f'{k}는 1보다 커야 합니다.')
    for k in ('heat_share','efficiency_max','recovery_max','electrifiable_max','boiler_efficiency'):
        v=getattr(p,k)
        if not math.isfinite(v) or not 0<=v<=1 or (k=='boiler_efficiency' and v==0):
            raise ValueError(f'{k}은 올바른 0~1 범위여야 합니다.')

def simulate(p: Plant, eff=0., rec=0., hp=0.):
    validate(p)
    if any(not math.isfinite(x) or x<0 or x>1 for x in (eff,rec,hp)):
        raise ValueError('도입 단계는 0~1 사이여야 합니다.')
    fuel=p.gas_m3*p.gas_kwh_m3/1000 # MWh of gas fuel input
    pool=fuel*p.heat_share
    eff_fuel=pool*p.efficiency_max*eff
    rec_fuel=(pool-eff_fuel)*p.recovery_max*rec if p.recovery_cap_fuel_mwh is None else min(pool-eff_fuel,p.recovery_cap_fuel_mwh*rec)
    hp_fuel=(pool-eff_fuel-rec_fuel)*p.electrifiable_max*hp
    new_elec=hp_fuel*p.boiler_efficiency/p.cop
    gas_saved=eff_fuel+rec_fuel+hp_fuel
    original_gas_co2=fuel*p.gas_ef_kg_kwh
    original_elec_co2=p.electricity_mwh*p.grid_ef_kg_kwh
    gross=gas_saved*p.gas_ef_kg_kwh
    extra=new_elec*p.grid_ef_kg_kwh
    net=gross-extra
    after_gas=original_gas_co2-gross
    after_elec=original_elec_co2+extra
    return {
        'fuel_mwh':fuel,'baseline_tco2':original_gas_co2+original_elec_co2,
        'baseline_gas_tco2':original_gas_co2,'baseline_electricity_tco2':original_elec_co2,
        'eff_fuel_mwh':eff_fuel,'recovery_fuel_mwh':rec_fuel,'hp_fuel_mwh':hp_fuel,
        'saved_fuel_mwh':gas_saved,'extra_electricity_mwh':new_elec,
        'gross_gas_reduction_tco2':gross,'additional_grid_tco2':extra,
        'net_reduction_tco2':net,'after_tco2':after_gas+after_elec,
        'after_gas_tco2':after_gas,'after_electricity_tco2':after_elec,
        'eff':eff,'rec':rec,'hp':hp,
        'within_grid_limit':new_elec<=p.extra_electricity_cap_mwh+1e-7,
    }

def recommend(p: Plant, target_pct: float, levels=(0.,.25,.5,.75,1.)):
    if not 0<=target_pct<=100: raise ValueError('감축목표가 범위를 벗어났습니다.')
    baseline=simulate(p)
    target=baseline['baseline_tco2']*target_pct/100
    available=[]
    for lv in product(levels,repeat=3):
        r=simulate(p,*lv)
        if r['within_grid_limit']:
            r['n_tech']=sum(x>0 for x in lv)
            r['effort']=sum(lv)
            available.append(r)
    if not available:raise ValueError('허용되는 기술 조합이 없습니다.')
    meets=[r for r in available if r['net_reduction_tco2']>=target-1e-9]
    if meets:
        best=min(meets,key=lambda r:(r['n_tech'],r['effort'],r['extra_electricity_mwh'],r['net_reduction_tco2']))
    else:
        best=max(available,key=lambda r:(r['net_reduction_tco2'],-r['n_tech'],-r['effort']))
    table=pd.DataFrame([{
        '효율 개선 도입':round(r['eff']*100),
        '폐열회수 도입':round(r['rec']*100),
        '전기화 도입':round(r['hp']*100),
        '연간 순감축(tCO₂)':r['net_reduction_tco2'],
        '추가 전력(MWh)':r['extra_electricity_mwh'],
        '기술 수':r['n_tech'],
        '목표 충족':r['net_reduction_tco2']>=target-1e-9,
    } for r in available])
    return {'chosen':best,'target_tco2':target,'baseline':baseline,'feasible':bool(meets),
        'gap_tco2':max(target-best['net_reduction_tco2'],0.),'table':table,'candidate_count':len(available)}

def sensitivity(p:Plant, chosen:dict, target_pct:float=0.):
    rows=[]
    cases=[('기본 입력',p,1.),('전력 배출계수 +30%',Plant(**{**asdict(p),'grid_ef_kg_kwh':p.grid_ef_kg_kwh*1.3}),1.),
           ('COP 20% 저하',Plant(**{**asdict(p),'cop':max(1.1,p.cop*.8)}),1.),
           ('실제 기술 적용률 70%',p,.7)]
    for name,variant,factor in cases:
        v=simulate(variant,chosen['eff']*factor,chosen['rec']*factor,chosen['hp']*factor)
        target=simulate(variant)['baseline_tco2']*target_pct/100
        rows.append({'조건':name,'순감축(tCO₂/년)':v['net_reduction_tco2'],
                     '추가 전력(MWh/년)':v['extra_electricity_mwh'],
                     '감축률(%)':v['net_reduction_tco2']/simulate(variant)['baseline_tco2']*100 if simulate(variant)['baseline_tco2'] else 0.,
                     '목표 충족':v['net_reduction_tco2']>=target-1e-7,
                     '목표 대비 부족(tCO₂/년)':max(0.,target-v['net_reduction_tco2']),
                     '전력 증설 상한 만족':v['within_grid_limit'],
                     '해석':('순감축 절대량 불변·기준배출 증가로 목표 판정 변화 가능' if name=='전력 배출계수 +30%' and chosen['hp']==0 else
                           '히트펌프 미선택으로 해당 COP 가정 비활성' if name=='COP 20% 저하' and chosen['hp']==0 else
                           '기술 도입 차질 위험' if name=='실제 기술 적용률 70%' else '선택 조합의 감도 계산')})
    return pd.DataFrame(rows)

def required_for_target(p:Plant,target_pct:float):
    base=simulate(p)
    target=base['baseline_tco2']*target_pct/100
    return {'target_tco2':target,'equivalent_fuel_mwh':target/p.gas_ef_kg_kwh if p.gas_ef_kg_kwh>0 else None,
            'annual_heat_kw_at_6000h':target/p.gas_ef_kg_kwh*1000/6000 if p.gas_ef_kg_kwh>0 else None}

def audit(p:Plant,r:dict):
    return {
        'mass_energy_balance_ok':abs(r['saved_fuel_mwh']-(r['eff_fuel_mwh']+r['recovery_fuel_mwh']+r['hp_fuel_mwh']))<1e-7,
        'carbon_balance_ok':abs(r['baseline_tco2']-r['after_tco2']-r['net_reduction_tco2'])<1e-7,
        'heat_service_conversion_ok': abs(r['extra_electricity_mwh']-r['hp_fuel_mwh']*p.boiler_efficiency/p.cop)<1e-7,
        'non_negative_emissions':r['after_gas_tco2']>=-1e-8 and r['after_electricity_tco2']>=-1e-8,
    }
