"""Pre-transcribed published Daegu city totals from two KOSIS tables.
An independent, explicit mapping is required before combining city-level sector series.
"""
from pathlib import Path
import pandas as pd
from energy import validate_and_normalize
DATA=Path(__file__).resolve().parent/'data'
ELEC_TOTALS={2018:15675653,2019:15265585,2020:14758568,2021:15443949,2022:16039260}
GAS_TOTALS={2018:1158194,2019:1124697}
GAS_HEAT_KWH_M3=10.5 # illustrative calorific conversion, not observed nor certified

def load_official():
    e=pd.read_csv(DATA/'daegu_electricity_official_2018_2022.csv',encoding='utf-8-sig')
    g=pd.read_csv(DATA/'daegu_gas_official_2018_2019.csv',encoding='utf-8-sig')
    if len(e)!=20 or len(g)!=10: raise ValueError('공식 표 행 개수 불일치')
    if set(e.category)!={'가정','공공','서비스','산업'}: raise ValueError('전력 분류 오류')
    if set(g.category)!={'가정','일반','업무','산업','기타'}: raise ValueError('가스 분류 오류')
    if not e.region.eq('대구광역시').all() or not g.region.eq('대구광역시').all():raise ValueError('지역 오류')
    if e.duplicated(['year','category']).any() or g.duplicated(['year','category']).any():raise ValueError('중복')
    if e.isna().any().any() or g.isna().any().any():raise ValueError('결측')
    for year,total in ELEC_TOTALS.items():
        if e[e.year==year].mwh.sum()!=total:raise ValueError(f'{year} 전력 공식 합계 불일치')
    for year,total in GAS_TOTALS.items():
        if g[g.year==year].thousand_m3.sum()!=total:raise ValueError(f'{year} 가스 공식 합계 불일치')
    return e,g

def normalized_overlap(gas_kwh_per_m3=GAS_HEAT_KWH_M3):
    """2018,2019 comparable sectors only. Unmapped gas '기타' intentionally excluded.
       These are energy purchase statistics, NOT reconciled inventory emissions.
    """
    e,g=load_official()
    rows=[]
    e_mapping={'가정':'가정','공공':'상업공공','서비스':'상업공공','산업':'산업'}
    g_mapping={'가정':'가정','일반':'상업공공','업무':'상업공공','산업':'산업'}
    for year in sorted(GAS_TOTALS):
        for sec in ['가정','상업공공','산업']:
            for fuel,table,col,mapping,unit in [
                ('electricity',e,'mwh',e_mapping,'MWh'),('gas',g,'thousand_m3',g_mapping,'천m3')]:
                keys=[k for k,v in mapping.items() if v==sec]
                subset=table[(table.year==year)&(table.category.isin(keys))]
                if len(subset)!=len(keys):raise ValueError(f'{year} {sec} {fuel} 필수분류 결측')
                rows.append({'year':year,'sector':sec,'energy_source':fuel,'value':float(subset[col].sum()),
                   'unit':unit,'region':'대구광역시','source_name':'대구 북구 탄소중립계획 표 3-38·3-40 (원출처 KOSIS)',
                   'source_url':str(table.iloc[0].source_url)})
    frame=pd.DataFrame(rows)
    result=validate_and_normalize(frame,gas_kwh_per_m3)
    result['data_class']='공식 계획서 재수록 2018~2019 실적 / 열량환산만 가정'
    return result

def ai_diagnostic():
    """Exploratory train-before-test (2018-21 train; 2022 test) small-panel diagnostic.
       Do NOT claim long-term forecast accuracy or reuse for policy effect forecasting.
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error
    e,_=load_official()
    x=e.copy().sort_values(['category','year'])
    x['previous_mwh']=x.groupby('category')['mwh'].shift(1)
    x=x.dropna(subset=['previous_mwh']).copy()
    x['previous_mwh']=x.previous_mwh.astype(float)
    # 2019-2021 train: 12 samples, 2022 test: 4 samples; deliberately disclose tiny dataset
    train=x[x.year<=2021].copy();test=x[x.year==2022].copy()
    if len(train)!=12 or len(test)!=4:raise ValueError('훈련/검증 행 수 불일치')
    cols=['year','previous_mwh']
    a=pd.get_dummies(train[['year','previous_mwh','category']],columns=['category'])
    b=pd.get_dummies(test[['year','previous_mwh','category']],columns=['category']).reindex(columns=a.columns,fill_value=0)
    reg=RandomForestRegressor(n_estimators=160,max_depth=4,random_state=42,min_samples_leaf=1)
    reg.fit(a,train.mwh)
    result=test[['year','category','mwh','previous_mwh']].copy()
    result['ai_prediction_mwh']=reg.predict(b)
    result['previous_year_baseline_mwh']=result.previous_mwh
    ai_mae=mean_absolute_error(result.mwh,result.ai_prediction_mwh)
    base_mae=mean_absolute_error(result.mwh,result.previous_year_baseline_mwh)
    return {'rows':result.reset_index(drop=True),'ai_mae_mwh':ai_mae,'baseline_mae_mwh':base_mae,
            'train_count':len(train),'test_count':len(test),'model':'RandomForestRegressor(160 trees, max_depth=4)'}
