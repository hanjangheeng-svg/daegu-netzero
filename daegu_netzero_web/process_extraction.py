"""User-confirmed local rule extraction and bounded heat balance.
No extracted value is fed to the optimizer until the user confirms every numeric field.
"""
from __future__ import annotations
import math
import re

FIELDS = (
    'source_in_c', 'source_out_c', 'source_flow_m3_h',
    'sink_in_c', 'sink_target_c', 'sink_flow_m3_h', 'annual_hours',
)
LABELS = {
    'source_in_c': '폐열원 입구온도 (℃)',
    'source_out_c': '폐열원 냉각 목표온도 (℃)',
    'source_flow_m3_h': '폐열원 유량 (m³/h)',
    'sink_in_c': '가열 대상 입구온도 (℃)',
    'sink_target_c': '가열 대상 목표온도 (℃)',
    'sink_flow_m3_h': '가열 대상 유량 (m³/h)',
    'annual_hours': '연간 동시 운전시간 (h/년)',
}


def normalize_numbers(obj):
    if not isinstance(obj, dict):
        raise ValueError('추출 결과는 JSON 객체여야 합니다.')
    # Whitelist only; numerical values must be explicit or null, never strings with units.
    result = {}
    for k in FIELDS:
        value = obj.get(k)
        if value is None or value == '':
            result[k] = None
            continue
        if isinstance(value, bool):
            raise ValueError(f'{LABELS[k]}의 숫자가 올바르지 않습니다.')
        try:
            f = float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f'{LABELS[k]}의 숫자가 올바르지 않습니다.') from e
        if not math.isfinite(f):
            raise ValueError('무한대나 NaN은 입력할 수 없습니다.')
        result[k] = f
    return result


def extract_rules(text):
    """Conservative local fallback. It purposely leaves ambiguous numbers null."""
    if not isinstance(text, str):
        raise ValueError('공정 설명은 문자열이어야 합니다.')
    out = {k: None for k in FIELDS}
    patterns = {
        'source_in_c': [r'(?:폐수|배출수|폐열원|열원)(?:의|의\s*입구|\s*입구)?\s*(?:온도)?\s*(?:는|가|은|이|:)?\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|도)', r'(\d+(?:\.\d+)?)\s*(?:℃|°C|도)(?:의|인)?\s*(?:폐수|배출수)'],
        'source_out_c': [r'(?:폐수|배출수|열원)(?:를|의)?\s*(?:약\s*)?(\d+(?:\.\d+)?)\s*(?:℃|°C|도)\s*(?:까지|로)\s*(?:냉각|낮춤)', r'(?:냉각|배출)\s*(?:목표)?\s*(?:온도)?\s*(?:는|가|:)?\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|도)'],
        'source_flow_m3_h': [r'(?:폐수|배출수|열원)(?:의)?\s*(?:유량|발생량)?\s*(?:은|는|이|가|:)?\s*(?:시간당\s*)?(\d+(?:\.\d+)?)\s*(?:m³/h|m3/h|㎥/h|m³\s*/\s*시간)', r'시간당\s*(\d+(?:\.\d+)?)\s*(?:m³|m3|㎥)(?:의)?\s*(?:폐수|배출수)'],
        'sink_in_c': [r'(?:급수|보충수|가열대상|냉수)(?:의)?\s*(?:입구|초기)?\s*(?:온도)?\s*(?:는|가|은|이|:)?\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|도)'],
        'sink_target_c': [r'(?:급수|보충수|가열대상)(?:의)?\s*(?:목표|출구|가열)\s*(?:온도)?\s*(?:는|가|은|이|:)?\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|도)', r'(?:급수|보충수|가열대상).{0,65}?(?:목표|출구|가열)\s*(?:온도)?\s*(?:는|가|은|이|:)?\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|도)'],
        'sink_flow_m3_h': [r'(?:급수|보충수|가열대상)(?:의)?\s*유량\s*(?:은|는|:)?\s*(\d+(?:\.\d+)?)\s*(?:m³/h|m3/h|㎥/h)'],
        'annual_hours': [r'(?:연간|1년\s*동안)\s*(\d+(?:\.\d+)?)\s*(?:시간|h)', r'하루\s*(\d+(?:\.\d+)?)\s*시간.{0,24}?(?:연간|1년)\s*(\d+(?:\.\d+)?)\s*일'],
    }
    for k, pats in patterns.items():
        for pattern in pats:
            m = re.search(pattern, text, re.I)
            if m:
                out[k] = float(m.group(1)) * float(m.group(2)) if k == 'annual_hours' and m.lastindex == 2 else float(m.group(1))
                break
    return out



def heat_balance(values, approach_c=10.0, recovery_fraction=0.7,
                 rho_kg_m3=1000.0, cp_kj_kg_k=4.186):
    """Conservative upper bound, NOT a pinch/network design.
    Requires source, sink and overlap data. Returns verified-input conditional heat only.
    """
    v=normalize_numbers(values)
    if any(v[k] is None for k in FIELDS):
        missing=[LABELS[k] for k in FIELDS if v[k] is None]
        raise ValueError('필수 정보 누락: '+', '.join(missing))
    si,so,sf,di,dt,df,h=(v[k] for k in FIELDS)
    if not (-20 <= so < si <= 250 and -20 <= di < dt <= 250):
        raise ValueError('열원 냉각 및 급수 가열의 온도 범위를 확인하세요.')
    if sf<=0 or df<=0 or h<=0 or h>8784:
        raise ValueError('열원·열수요 유량은 양수, 동시 운전시간은 연간 8,784h 이하여야 합니다.')
    if not 0 < approach_c < 100 or not 0 <= recovery_fraction <= 1:
        raise ValueError('최소 접근온도와 회수계수를 확인하세요.')
    source_kw=sf*rho_kg_m3*cp_kj_kg_k*(si-so)/3600
    demand_kw=df*rho_kg_m3*cp_kj_kg_k*(dt-di)/3600
    # Temperature-limited proxy: cannot cool source below sink inlet+approach,
    # nor heat sink above source inlet-approach. Does not establish exchangers.
    source_thermal_limit=sf*rho_kg_m3*cp_kj_kg_k*max(0,si-max(so,di+approach_c))/3600
    demand_thermal_limit=df*rho_kg_m3*cp_kj_kg_k*max(0,min(dt,si-approach_c)-di)/3600
    upper=min(source_kw,demand_kw,source_thermal_limit,demand_thermal_limit)
    usable=upper*recovery_fraction
    return {'source_kw':source_kw,'demand_kw':demand_kw,'temperature_cap_kw':upper,
            'conditional_recovery_kw':usable,'annual_recovered_heat_mwh':usable*h/1000,
            'annual_hours':h,'source_in_c':si,'source_out_c':so,'sink_in_c':di,'sink_target_c':dt,
            'approach_c':approach_c,'recovery_fraction':recovery_fraction}


def cap_recovery_fuel_mwh(heat_mwh, boiler_efficiency, gas_fuel_mwh, heat_share):
    if not 0<boiler_efficiency<=1:
        raise ValueError('보일러 효율이 올바르지 않습니다.')
    if heat_mwh<0 or gas_fuel_mwh<0 or not 0<=heat_share<=1:
        raise ValueError('음수 열량이나 잘못된 열사용 비율입니다.')
    return min(heat_mwh/boiler_efficiency,gas_fuel_mwh*heat_share)
