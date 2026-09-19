"""Small, explicit, finite configuration surface for bounded local calculations."""
from copy import deepcopy
import math

METHODS = {
    "M1": {"name": "저주파 음향", "subtitle": "진동 유동 · acoustic", "color": "#48d9c0"},
    "M2": {"name": "공기 와류 링", "subtitle": "펄스 유동 · vortex", "color": "#7caaff"},
    "M3": {"name": "지향 수분무", "subtitle": "액적 전달 · water mist", "color": "#c0a0fa"},
    "M4": {"name": "응축 에어로졸", "subtitle": "입자 전달 · aerosol", "color": "#f0c36a"},
    "M5": {"name": "전도성 와류 / 이온풍", "subtitle": "복합 후보 · conductive vortex", "color": "#fa917d"},
}
DEFAULTS = {
    "scenario": {"duration_s": 4.0, "dt_s": .02, "distance_m": 1.0,
                 "crosswind_m_s": .2, "ambient_K": 293.15,
                 "target_radius_m": .2, "seed": 42},
    "methods": {
        "M1": {"frequency_hz": 60., "velocity_rms_m_s": .4, "aperture_m": .15,
               "power_W": 80., "mass_kg": .5},
        "M2": {"exit_velocity_m_s": 8., "diameter_m": .1, "pulse_duration_s": .05,
               "period_s": 1., "power_W": 15., "mass_kg": .6, "stored_energy_J": 100.},
        "M3": {"flow_kg_s": .005, "diameter_um": 100., "exit_velocity_m_s": 5.,
               "power_W": 35., "mass_kg": .5, "payload_kg": .1},
        "M4": {"flow_kg_s": .001, "diameter_um": 5., "exit_velocity_m_s": 2.,
               "power_W": 10., "mass_kg": .4, "payload_kg": .05},
        "M5": {"variant": "CV", "charge_density_C_m3": 0., "electric_field_V_m": 0.,
               "flow_kg_s": .001, "diameter_um": 10., "exit_velocity_m_s": 8.,
               "diameter_m": .1, "pulse_duration_s": .05, "period_s": 1.,
               "power_W": 20., "mass_kg": .7, "payload_kg": .05, "stored_energy_J": 100.},
    },
    "drone": {"mass_kg": 2., "battery_Wh": 120., "rotor_radius_m": .12,
              "rotor_count": 4, "max_thrust_N": 45., "max_power_W": 1200.,
              "hover_efficiency": .6, "reserve_fraction": .2, "approach_s": 15.,
              "return_s": 15., "avionics_W": 12., "inertia_kg_m2": [.04, .04, .08],
              "controller_enabled": True, "ambient_K": 293.15,
              "payload_capacity_kg":2., "max_torque_Nm":2.5,
              "reaction_lever_arm_m":[0.,0.,-.1], "airframe_cg_m":None,
              "device_mount_position_m":None,"consumable_position_m":None},
}

# These are computational/model bounds, not equipment operating recommendations.
BOUNDS = {
    "duration_s": (.1, 20), "dt_s": (.002, .1), "distance_m": (.1, 5),
    "crosswind_m_s": (-3, 3), "ambient_K": (250, 600), "target_radius_m": (.02, .5),
    "seed": (0, 2**31 - 1), "frequency_hz": (1, 200), "velocity_rms_m_s": (0, 2),
    "aperture_m": (.01, .5), "power_W": (0, 1000), "mass_kg": (.01, 20),
    "exit_velocity_m_s": (0, 30), "diameter_m": (.01, .5), "pulse_duration_s": (.002, .5),
    "period_s": (.05, 5), "stored_energy_J": (0, 10000), "flow_kg_s": (0, .1),
    "diameter_um": (1, 1000), "payload_kg": (0, 5), "charge_density_C_m3": (0, .001),
    "electric_field_V_m": (0, 1e6), "battery_Wh": (0, 2000), "rotor_radius_m": (.04, .5),
    "rotor_count": (2, 12), "max_thrust_N": (0, 1000), "max_power_W": (0, 10000),
    "hover_efficiency": (.1, 1), "reserve_fraction": (0, .8),
    "approach_s": (0, 120), "return_s": (0, 120), "avionics_W": (0, 200),
    "payload_capacity_kg":(0,20), "max_torque_Nm":(0,100),
}

def validate_config(overrides=None):
    result = deepcopy(DEFAULTS)
    if overrides is None:
        return result
    if not isinstance(overrides, dict):
        raise ValueError("설정은 JSON 객체여야 합니다.")
    overrides=deepcopy(overrides)
    extensions={key:overrides.pop(key) for key in ('sensor','thermal') if key in overrides}

    def merge(target, source, prefix=""):
        if not isinstance(source, dict):
            raise ValueError(f"{prefix}: 객체가 필요합니다.")
        for key, value in source.items():
            path = f"{prefix}.{key}".strip(".")
            if key not in target:
                raise ValueError(f"알 수 없는 설정: {path}")
            if isinstance(target[key], dict):
                merge(target[key], value, path)
            elif key == "variant":
                if value not in ("CV", "EHD", "COMBINED"):
                    raise ValueError("M5 variant는 CV/EHD/COMBINED 중 하나입니다.")
                target[key] = value
            elif key == "controller_enabled":
                if not isinstance(value, bool):
                    raise ValueError(f"{path}: boolean이 필요합니다.")
                target[key] = value
            elif key in ('reaction_lever_arm_m','airframe_cg_m','device_mount_position_m','consumable_position_m'):
                if value is None and key!='reaction_lever_arm_m':
                    target[key]=None
                    continue
                if not isinstance(value,list) or len(value)!=3 or any(type(v) is bool or not isinstance(v,(float,int)) or not math.isfinite(v) or abs(v)>2 for v in value):
                    raise ValueError(path+': requires finite xyz within 2m')
                target[key]=list(value)
            elif key == "inertia_kg_m2":
                if not isinstance(value, list) or len(value) != 3 or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or
                    not math.isfinite(v) or not .001 <= v <= 10 for v in value
                ):
                    raise ValueError("관성은 양의 유한수 3개여야 합니다.")
                target[key] = list(value)
            else:
                low, high = BOUNDS[key]
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                    raise ValueError(f"{path}: 유한수가 필요합니다.")
                if not low <= value <= high:
                    raise ValueError(f"{path}: 계산 범위는 {low}–{high}입니다.")
                if key in ("seed", "rotor_count") and int(value) != value:
                    raise ValueError(f"{path}: 정수가 필요합니다.")
                target[key] = value
    merge(result, overrides)
    if extensions:
        from .drone import _sensor_config, _thermal_config
        if 'sensor' in extensions:
            result['sensor']=_sensor_config(extensions,int(result['scenario']['seed']))
        if 'thermal' in extensions:
            result['thermal']=_thermal_config(extensions,result['drone']['ambient_K'])
    for key in ("M2", "M5"):
        m = result["methods"][key]
        if m["pulse_duration_s"] > m["period_s"]:
            raise ValueError(f"{key}: pulse duration cannot exceed period")
    if result["scenario"]["duration_s"] / result["scenario"]["dt_s"] > 10000:
        raise ValueError("계산 step은 10,000개 이하로 설정하세요.")
    return result
