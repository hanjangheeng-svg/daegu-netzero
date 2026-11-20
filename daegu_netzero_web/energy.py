"""v0.3 physical-energy calculator. All observed inputs must be user-supplied, documented.
Results are conditional, not an official GHG inventory or causal policy evaluation.
"""
import io
import numpy as np
import pandas as pd

VALID_SECTORS = {'가정','상업공공','산업','수송','기타'}
FUELS = {'electricity','gas','oil','district_heat'}
UNITS = {'kWh':1e-6, 'MWh':1e-3, 'GWh':1., 'TJ':1/3.6,
         'MJ':1/3_600_000, 'm3':None, 'Nm3':None, '천m3':None}
REQ = ['year','sector','energy_source','value','unit','region','source_name','source_url']
GAS_KWH_PER_M3_DEFAULT = 10.5 # an assumption, NOT official observed conversion


def read_energy(upload, filename):
    name=filename.lower()
    if name.endswith('.csv'):
        raw=upload.read() if hasattr(upload,'read') else upload
        for codec in ('utf-8-sig','cp949'):
            try: return pd.read_csv(io.BytesIO(raw),encoding=codec)
            except UnicodeDecodeError: pass
        raise ValueError('CSV 인코딩은 UTF-8 또는 CP949만 지원합니다.')
    if name.endswith('.xlsx'):
        return pd.read_excel(upload)
    raise ValueError('CSV 또는 XLSX만 지원합니다.')


def validate_and_normalize(df, gas_kwh_per_m3=GAS_KWH_PER_M3_DEFAULT):
    """Strict normalized schema; no guessing of units/columns or geographic join."""
    if set(REQ)-set(df.columns):
        raise ValueError('표준 입력 열이 없습니다: '+', '.join(sorted(set(REQ)-set(df.columns))))
    x=df[REQ].copy()
    if x.empty or x.isna().any().any(): raise ValueError('빈 데이터 또는 필수 열 결측값이 있습니다.')
    x['year']=pd.to_numeric(x.year,errors='raise')
    if not np.isfinite(x.year).all() or (x.year%1!=0).any() or not x.year.between(1990,2100).all():
        raise ValueError('year는 유효한 정수 연도여야 합니다.')
    x['year']=x.year.astype(int)
    x['value']=pd.to_numeric(x.value,errors='raise')
    if not np.isfinite(x.value).all() or (x.value<0).any():raise ValueError('사용량은 0 이상의 유한한 수치여야 합니다.')
    if not set(x.sector).issubset(VALID_SECTORS):raise ValueError('sector 값은 가정/상업공공/산업/수송/기타만 허용합니다.')
    if not set(x.energy_source).issubset(FUELS):raise ValueError('energy_source 값은 electricity/gas/oil/district_heat만 허용합니다.')
    if not set(x.unit).issubset(UNITS):raise ValueError('지원 단위: '+', '.join(UNITS))
    if not x.region.astype(str).str.strip().eq('대구광역시').all():
        raise ValueError('대구광역시 외 데이터가 포함되어 있습니다. 원본 필터링 후 업로드하세요.')
    if x.duplicated(['year','sector','energy_source']).any():
        raise ValueError('연도×부문×에너지원이 중복됩니다. 원본의 월별/지역별 데이터를 합산 후 입력하세요.')
    if (x.energy_source!='gas').loc[x.unit.isin(['m3','Nm3','천m3'])].any():
        raise ValueError('부피 단위(m3)는 가스에만 사용할 수 있습니다.')
    if not 5 <=gas_kwh_per_m3<=20:raise ValueError('가스 환산계수는 5~20 kWh/m³ 범위여야 합니다.')
    def converted(row):
        if row.unit=='m3' or row.unit=='Nm3': return row.value*gas_kwh_per_m3/1e6
        if row.unit=='천m3': return row.value*1000*gas_kwh_per_m3/1e6
        return row.value*UNITS[row.unit]
    x['gwh']=x.apply(converted,axis=1)
    x['data_class']='업로드 관측자료(출처 미검증)'
    return x


def input_coverage(x, year, sectors=('가정','상업공공')):
    present={(r.sector,r.energy_source) for r in x[x.year==year].itertuples()}
    return {sec:{fuel:(sec,fuel) in present for fuel in ('electricity','gas')} for sec in sectors}


def physical_transition(energy, year, sector, *, efficiency=0., heat_fraction=0.5,
                        switch_fraction=0., cop=3., boiler_efficiency=.85,
                        grid_kg_kwh=.45, gas_kg_kwh=.20,
                        electricity_price=160., gas_price=100.):
    """Energy GWh/year -> emissions ktCO2e and expenses 억 KRW/year.
    Heat fraction is fraction of AFTER-efficiency gas final energy used for useful heat.
    Switch fraction refers to heat load switched to electric heat pumps.
    No equipment embodied carbon or capex included.
    """
    constraints={'efficiency':(efficiency,0,.6),'heat_fraction':(heat_fraction,0,1),
                 'switch_fraction':(switch_fraction,0,1),'cop':(cop,1,8),
                 'boiler_efficiency':(boiler_efficiency,.1,1),
                 'grid_kg_kwh':(grid_kg_kwh,0,2), 'gas_kg_kwh':(gas_kg_kwh,0,1),
                 'electricity_price':(electricity_price,0,10000),'gas_price':(gas_price,0,10000)}
    for k,(v,lo,hi) in constraints.items():
        if not np.isfinite(v) or not lo<=v<=hi: raise ValueError(f'{k}: 범위 {lo}~{hi} 위반')
    q=energy[(energy.year==int(year))&(energy.sector==sector)]
    electricity=q.loc[q.energy_source=='electricity','gwh'].sum()
    gas=q.loc[q.energy_source=='gas','gwh'].sum()
    if not {'electricity','gas'}.issubset(set(q.energy_source)):
        raise ValueError('해당 연도·부문의 전력 및 가스 데이터가 모두 필요합니다. 누락을 0으로 간주하지 않습니다.')
    elec_after_eff=electricity*(1-efficiency)
    gas_after_eff=gas*(1-efficiency)
    heat_gas=gas_after_eff*heat_fraction*switch_fraction
    # Heat delivered from boiler = fuel energy * boiler efficiency, replaced by HP COP
    new_electric=heat_gas*boiler_efficiency/cop
    after_elec=elec_after_eff+new_electric
    after_gas=gas_after_eff-heat_gas
    before_kt=electricity*grid_kg_kwh+gas*gas_kg_kwh # 1 GWh * kg/kWh == 1 kt
    after_kt=after_elec*grid_kg_kwh+after_gas*gas_kg_kwh
    before_cost=electricity*electricity_price/100+gas*gas_price/100 # 1GWh *1e6 kWh *won/kWh /1e8 == /100
    after_cost=after_elec*electricity_price/100+after_gas*gas_price/100
    return {'year':int(year),'sector':sector,'electricity_before_gwh':electricity,'gas_before_gwh':gas,
            'electricity_after_gwh':after_elec,'gas_after_gwh':after_gas,
            'electricity_added_gwh':new_electric,'before_kt':before_kt,'after_kt':after_kt,
            'reduction_kt':before_kt-after_kt,'reduction_pct':100*(before_kt-after_kt)/before_kt if before_kt>0 else 0,
            'before_cost_eok':before_cost,'after_cost_eok':after_cost,
            'annual_energy_saving_eok':before_cost-after_cost}


def pathway(energy, base_year, sector, until_year, *, efficiency_target, switch_target,
            heat_fraction, cop, boiler_efficiency, grid_base, grid_end,
            gas_factor, electricity_price, gas_price):
    if until_year<=base_year:raise ValueError('목표연도는 기준연도 이후여야 합니다.')
    results=[]
    for year in range(base_year,until_year+1):
        t=(year-base_year)/(until_year-base_year)
        r=physical_transition(energy,base_year,sector,efficiency=efficiency_target*t,
                 switch_fraction=switch_target*t,heat_fraction=heat_fraction,cop=cop,
                 boiler_efficiency=boiler_efficiency,grid_kg_kwh=grid_base+(grid_end-grid_base)*t,
                 gas_kg_kwh=gas_factor,electricity_price=electricity_price,gas_price=gas_price)
        r['target_year']=year
        results.append(r)
    x=pd.DataFrame(results)
    x['cumulative_reduction_kt']=0.
    # annual net change against an assumed UNCHANGED-energy baseline at the SAME year's grid factor
    for i,row in x.iterrows():
        g=grid_base+(grid_end-grid_base)*(row.target_year-base_year)/(until_year-base_year)
        baseline=physical_transition(energy,base_year,sector,grid_kg_kwh=g,
                   gas_kg_kwh=gas_factor,electricity_price=electricity_price,gas_price=gas_price)
        x.loc[i,'policy_only_reduction_kt']=baseline['after_kt']-row['after_kt']
    x['cumulative_reduction_kt']=x['policy_only_reduction_kt'].cumsum()
    return x


def reconcile_to_inventory(energy, inventory_kt, year,sector,grid_factor,gas_factor,tolerance=.05):
    r=physical_transition(energy,year,sector,grid_kg_kwh=grid_factor,gas_kg_kwh=gas_factor)
    if not np.isfinite(inventory_kt) or inventory_kt<=0:raise ValueError('인벤토리 값 오류')
    discrepancy=(r['before_kt']-inventory_kt)/inventory_kt
    return {'reconciled':abs(discrepancy)<=tolerance,'relative_gap':discrepancy,
            'estimated_kt':r['before_kt'],'inventory_kt':inventory_kt}


def blank_template():
    return pd.DataFrame(columns=REQ)
