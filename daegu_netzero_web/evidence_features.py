"""Interpretive features; city benchmark is NOT peer mean, economics entirely user scenarios."""
from dataclasses import replace
import re
import math
import pandas as pd
from factory_engine import Plant, simulate, recommend
from official_energy import load_official

ENERGY_DIAGNOSTIC_URL = 'https://min24.energy.or.kr/nedms/front/sub/performance.do'
TECH_CASE_URL = 'https://tips.energy.or.kr/overconsector/overconsector_view_01.do?ch_code_num=MF01&code_num=MF'

def region_benchmark(year=2019, gas_kwh_m3=10.5):
    if year not in (2018, 2019): raise ValueError('전력·가스의 공통 연도는 2018~2019입니다.')
    e,g=load_official()
    elec=float(e[(e.year==year)&(e.category=='산업')].mwh.sum())
    gas_m3=float(g[(g.year==year)&(g.category=='산업')].thousand_m3.sum())*1000
    fuel=gas_m3*gas_kwh_m3/1000
    return {'year':year,'electricity_mwh':elec,'gas_m3':gas_m3,'gas_energy_mwh':fuel,
            'gas_energy_share': fuel/(fuel+elec) if fuel+elec else 0}

def company_comparison(p:Plant,year=2019):
    reg=region_benchmark(year,p.gas_kwh_m3)
    fuel=p.gas_m3*p.gas_kwh_m3/1000
    share=fuel/(fuel+p.electricity_mwh) if fuel+p.electricity_mwh else 0
    return {**reg, 'plant_gas_share':share,'difference_pp':(share-reg['gas_energy_share'])*100,
            'orientation':('연료 절감 우선 점검' if share>reg['gas_energy_share']+0.05 else
                          '전력 설비 효율 우선 점검' if share<reg['gas_energy_share']-0.05 else
                          '연료·전력 병행 점검')}

def range_evaluation(p:Plant, chosen:dict, target_pct:float, bounds:dict):
    """Re-evaluate fixed implementation levels under explicitly defined uncertainties.

    With an approved physical heat cap, recovery_max is inactive. Vary the
    *recoverable annual heat cap* instead, reflecting uncertain usable overlap,
    availability and fouling. These are illustrative 60/100/120% multipliers,
    not statistically estimated confidence intervals.
    """
    keys={'efficiency_max':'효율개선 잠재율','recovery_max':'폐열회수 잠재율','electrifiable_max':'전기화 잠재율'}
    for k,label in keys.items():
        v=bounds[k]
        if len(v)!=3 or not 0<=v[0]<=v[1]<=v[2]<=100:
            raise ValueError(f'{label} 최소≤기준≤최대 순서 및 0~100% 필요')
    approved=p.recovery_cap_fuel_mwh is not None
    rows=[]
    for label,i,cap_factor in [('보수',0,.6),('기준',1,1.),('상향',2,1.2)]:
        options={k:bounds[k][i]/100 for k in keys}
        if approved:
            options['recovery_cap_fuel_mwh']=p.recovery_cap_fuel_mwh*cap_factor
        q=replace(p,**options)
        result=simulate(q,chosen['eff'],chosen['rec'],chosen['hp'])
        base=simulate(q)['baseline_tco2'];target=base*target_pct/100
        rows.append({'시나리오':label,'순감축(tCO₂/년)':result['net_reduction_tco2'],
                     '감축률(%)':result['net_reduction_tco2']/base*100 if base else 0.,
                     '목표 충족':result['net_reduction_tco2']>=target-1e-7,
                     '목표 부족(tCO₂/년)':max(0,target-result['net_reduction_tco2']),
                     '추가 전력(MWh/년)':result['extra_electricity_mwh'],
                     '전력 증설 상한 만족':result['within_grid_limit'],
                     '회수열 상한 배율(%)':round(cap_factor*100) if approved else None,
                     '적용 회수연료 상한(MWh/년)':q.recovery_cap_fuel_mwh if approved else None,
                     '시나리오 근거':('승인된 공정열 환산상한의 60/100/120% 및 기타 기술 잠재율 가정; 동일 도입단계 유지. 실제 계측 신뢰구간 아님' if approved else
                                   '미검증 기술 잠재율의 60/100/130% 가정; 동일 도입단계 유지. 실제 계측 신뢰구간 아님')})
    return pd.DataFrame(rows)

def economics(p:Plant, chosen:dict, gas_krw_m3:float, electric_krw_kwh:float,
              investment_million_krw:tuple, nox_g_m3:float|None=None):
    if gas_krw_m3<0 or electric_krw_kwh<0 or not math.isfinite(gas_krw_m3+electric_krw_kwh):
        raise ValueError('요금은 0 이상의 유한한 수여야 합니다.')
    if len(investment_million_krw)!=3 or sorted(investment_million_krw)!=list(investment_million_krw) or min(investment_million_krw)<0:
        raise ValueError('투자비는 최소≤기준≤최대 순으로 입력해야 합니다.')
    saved_gas_m3=chosen['saved_fuel_mwh']*1000/p.gas_kwh_m3
    gas_savings=saved_gas_m3*gas_krw_m3
    elec_cost=chosen['extra_electricity_mwh']*1000*electric_krw_kwh
    annual_net=gas_savings-elec_cost
    rows=[]
    for name,capex in zip(('최소투자','기준투자','최대투자'),investment_million_krw):
        rows.append({'비용 시나리오':name,'투자비(백만원)':capex,
           '연간 순운영비 절감(백만원)':annual_net/1e6,
           '단순 회수기간(년)':round(capex*1e6/annual_net,2) if annual_net>0 else None})
    nox_kg = None if nox_g_m3 is None else saved_gas_m3*nox_g_m3/1000
    return {'table':pd.DataFrame(rows),'gas_saved_m3':saved_gas_m3,'annual_gas_savings_krw':gas_savings,
            'annual_extra_elec_cost_krw':elec_cost,'annual_net_krw':annual_net,'nox_kg':nox_kg}

def parse_process_numbers(text):
    """Extract only unambiguous explicit units; user must confirm before any use."""
    if not isinstance(text,str):raise ValueError('문자열 입력이 필요합니다.')
    ret={}
    patterns={
      '열원 온도(°C)':r'(?:폐수|폐열|열원)\s*(?:온도)?\s*[:은이]?\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|도)',
      '공급 목표온도(°C)':r'(?:공급|목표|가열)\s*(?:온도)?\s*[:은이]?\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|도)',
      '가동시간(h/년)':r'(?:연간\s*)?(?:가동|운전)\s*(?:시간)?\s*[:은이]?\s*(\d+(?:\.\d+)?)\s*(?:시간|h)(?:\s*/\s*년)?',
      '물 유량(m³/h)':r'(?:폐수|물|용수)\s*(?:유량)?\s*[:은이]?\s*(\d+(?:\.\d+)?)\s*(?:m3/h|m³/h|㎥/h)',
    }
    for key,pattern in patterns.items():
        match=re.search(pattern,text,flags=re.IGNORECASE)
        if match:ret[key]=float(match.group(1))
    return ret

def water_heat_kw(flow_m3_h, hot_c, cold_c, rho_kg_m3=1000, cp_kj_kgk=4.186):
    if flow_m3_h<0 or hot_c<=cold_c:raise ValueError('온도차와 유량을 확인하세요.')
    return flow_m3_h*rho_kg_m3*cp_kj_kgk*(hot_c-cold_c)/3600
