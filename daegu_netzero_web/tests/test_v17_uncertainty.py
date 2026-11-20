from backend.api import PlantInput, HeatInput, analyze, heat_route
from factory_engine import Plant, simulate
from evidence_features import range_evaluation

EXAMPLE = {'source_in_c':70,'source_out_c':30,'source_flow_m3_h':5,
           'sink_in_c':20,'sink_target_c':55,'sink_flow_m3_h':4,'annual_hours':4000}

def test_approved_heat_uses_distinct_real_parameter_ranges():
    heat = heat_route(HeatInput(values=EXAMPLE))
    r = analyze(PlantInput(recovery_cap_fuel_mwh=heat['recovery_cap_fuel_mwh']))
    low, middle, high = r['ranges']
    assert low['회수열 상한 배율(%)'] == 60
    assert middle['회수열 상한 배율(%)'] == 100
    assert high['회수열 상한 배율(%)'] == 120
    assert low['순감축(tCO₂/년)'] < middle['순감축(tCO₂/년)'] < high['순감축(tCO₂/년)']
    assert abs(middle['순감축(tCO₂/년)']-r['chosen']['net_reduction_tco2'])<1e-7
    assert low['시나리오 근거']


def test_unapproved_ranges_preserved():
    r=analyze(PlantInput())
    assert r['ranges'][0]['순감축(tCO₂/년)'] < r['ranges'][1]['순감축(tCO₂/년)']
    assert all(row['회수열 상한 배율(%)'] is None for row in r['ranges'])


def test_approved_heat_capacity_never_exceeds_plant_heat_pool():
    p=Plant(recovery_cap_fuel_mwh=1e9)
    r=simulate(p, 1, 1, 1)
    assert r['saved_fuel_mwh']<=r['fuel_mwh']*p.heat_share + 1e-9
