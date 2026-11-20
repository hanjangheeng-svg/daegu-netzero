from backend.api import PlantInput,HeatInput,analyze,heat_route,region_route

def test_engine_results_are_preserved():
 r=analyze(PlantInput())
 assert round(r['baseline']['baseline_tco2'],1)==474.5
 assert round(r['chosen']['net_reduction_tco2'],1)==49.6
 assert r['candidate_count']==125
 assert r['ranges'][0]['목표 충족'] is False
 assert any(s['조건']=='실제 기술 적용률 70%' and not s['목표 충족'] for s in r['stress'])

def test_heat_changes_recommendation():
 vals={'source_in_c':70,'source_out_c':30,'source_flow_m3_h':5,'sink_in_c':20,'sink_target_c':55,'sink_flow_m3_h':4,'annual_hours':4000}
 heat=heat_route(HeatInput(values=vals))
 assert round(heat['temperature_cap_kw'],1)==162.8
 assert round(heat['annual_recovered_heat_mwh'],1)==455.8
 r=analyze(PlantInput(recovery_cap_fuel_mwh=heat['recovery_cap_fuel_mwh']))
 assert r['chosen']['net_reduction_tco2']>50
 assert r['chosen']['rec']>0

def test_region_series():
 r=region_route()
 assert len(r['electricity'])==20
 assert len(r['gas'])==10
