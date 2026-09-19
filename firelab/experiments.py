"""Preregistered schedules and deduplicated SI resource ledgers."""
from copy import deepcopy
from itertools import combinations
import hashlib
import json
import math

METHODS = ('M1', 'M2', 'M3', 'M4', 'M5')


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


def build_design(start_s=6., duration_s=4., transition_delay_s=0., supplemental=True,
                 selected_combinations=()):
    """Base36 plus exact schedule-matched component controls and M5 ablations.

    Dose fractions are generator requests, not evidence of equal realized energy.
    Sequential stages share the same total actuation window including delay.
    """
    for name, value in [('start', start_s), ('duration', duration_s), ('delay', transition_delay_s)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{name} must be finite and nonnegative')
    if duration_s <= transition_delay_s:
        raise ValueError('operation duration must exceed switching delay')
    rows = []

    def row(cid, methods, mode, schedule, doses, **metadata):
        result = {'id': cid, 'methods': list(methods), 'order': list(methods), 'mode': mode,
                  'schedule': schedule, 'dose_fraction': doses,
                  'metadata': {'main_design': len(rows) < 36, 'dose_basis': 'requested_fraction_not_resource_equivalence',
                               'm5_variant': 'CV', **metadata}}
        rows.append(result)
        return result

    def slot(start=start_s, duration=duration_s):
        return {'start_s': float(start), 'duration_s': float(duration)}

    row('C0', [], 'control', {}, {})
    for m in METHODS:
        row(m, [m], 'single', {m: slot()}, {m: 1.})
    for a, b in combinations(METHODS, 2):
        row(f'{a}+{b}:SIM', [a, b], 'simultaneous', {a: slot(), b: slot()}, {a: .5, b: .5})
    stage = (duration_s - transition_delay_s) / 2
    for a, b in combinations(METHODS, 2):
        for first, second in [(a, b), (b, a)]:
            row(f'{first}>{second}:SEQ', [first, second], 'sequential',
                {first: slot(start_s, stage), second: slot(start_s + stage + transition_delay_s, stage)},
                {first: 1., second: 1.}, transition_delay_s=transition_delay_s)
    if supplemental:
        seen = {}
        for combined in list(rows[6:]):
            combined['partial_controls'] = {}
            for m in combined['methods']:
                key = stable_hash([m, combined['schedule'][m], combined['dose_fraction'][m]])[:12]
                cid = 'PARTIAL_' + key
                combined['partial_controls'][m] = cid
                if key not in seen:
                    seen[key] = cid
                    row(cid, [m], 'single', {m: deepcopy(combined['schedule'][m])},
                        {m: combined['dose_fraction'][m]}, main_design=False, partial_control=True)
        for m in METHODS:
            row('SHAM_' + m, [], 'control', {}, {}, main_design=False, mounted_devices=[m], sham=True)
        for variant in ('VORTEX_ONLY', 'PARTICLE_ONLY', 'EHD', 'COMBINED'):
            row('M5_' + variant, ['M5'], 'single', {'M5': slot()}, {'M5': 1.},
                main_design=False, m5_variant=variant, ablation=True)
    for combo in selected_combinations:
        if len(combo) < 3 or len(combo) > 5 or len(set(combo)) != len(combo) or set(combo) - set(METHODS):
            raise ValueError('selected combinations need 3-5 distinct supported methods')
        row('+'.join(combo) + ':MULTI', combo, 'simultaneous', {m: slot() for m in combo},
            {m: 1 / len(combo) for m in combo}, main_design=False, preregistered_extension=True)
    return rows


def resource_ledger(components):
    """Count each actual component once; different chemicals keep distinct masses."""
    unique = {}
    for item in components:
        item = deepcopy(item)
        cid = item.get('component_id')
        if not isinstance(cid, str) or not cid:
            raise ValueError('component_id required')
        if cid in unique and unique[cid] != item:
            raise ValueError('conflicting shared component: ' + cid)
        for key in ('electrical_energy_J', 'pneumatic_energy_J', 'mass_kg', 'peak_power_W'):
            v = item.get(key, 0.)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError('invalid resource ' + key)
        for material, mass in item.get('consumables_kg', {}).items():
            if not material or not isinstance(mass, (int, float)) or isinstance(mass, bool) or not math.isfinite(mass) or mass < 0:
                raise ValueError('invalid material-specific mass')
        unique[cid] = item
    result = {key: sum(c.get(key, 0.) for c in unique.values()) for key in
              ('electrical_energy_J', 'pneumatic_energy_J', 'mass_kg', 'peak_power_W')}
    result['consumables_kg'] = {}
    for c in unique.values():
        for material, mass in c.get('consumables_kg', {}).items():
            result['consumables_kg'][material] = result['consumables_kg'].get(material, 0.) + mass
    result.update(components=list(unique.values()), peak_power_basis='conservative simultaneous sum; not inferred from timing')
    return result
