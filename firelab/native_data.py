"""Strict native FDS time-series ingestion, with explicit support and unit checks."""
import csv
import hashlib
from pathlib import Path
import numpy as np


def _finite_nonnegative(value, label):
    if type(value) is bool or not isinstance(value,(int,float)) or not np.isfinite(value) or value<0:
        raise ValueError(label+' must be a finite nonnegative number')
    return float(value)


def _activation_threshold(declared, method, canonical, observed_unit, expected_state):
    """Return a unit-checked channel threshold while retaining old descriptors."""
    thresholds=declared.get('thresholds',{})
    spec=thresholds.get(method,{}).get(canonical) if isinstance(thresholds,dict) else None
    if spec is not None:
        if not isinstance(spec,dict):
            raise ValueError(f'{method}:{canonical} activation threshold must be an object')
        value=_finite_nonnegative(spec.get('value'),f'{method}:{canonical} activation threshold')
        unit=spec.get('unit')
        comparison=spec.get('comparison')
        if unit!=observed_unit:
            raise ValueError(f'{method}:{canonical} activation threshold unit {unit!r} does not match native unit {observed_unit!r}')
        if comparison not in ('abs_gte','gte'):
            raise ValueError(f'{method}:{canonical} activation threshold comparison is invalid')
        return value,unit,comparison
    # Compatibility for already-saved descriptors.  A zero-dose source must
    # remain numerically near zero, so an active-source minimum is never used
    # as its off tolerance.
    proof=declared.get('proof')
    value=proof.get('threshold',1e-9) if isinstance(proof,dict) else 1e-9
    value=_finite_nonnegative(value,f'{method}:{canonical} activation threshold')
    return value,observed_unit,'abs_gte' if expected_state=='active' else 'abs_lte'


def read_fds_csv(path):
    path = Path(path)
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        units = [s.strip() for s in next(reader)]
        names = [s.strip() for s in next(reader)]
        if len(units) != len(names) or len(set(names)) != len(names):
            raise ValueError('native CSV header/units mismatch or duplicate names')
        data = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(names):
                raise ValueError('truncated native CSV row')
            values = [float(v) for v in row]
            if not all(np.isfinite(values)):
                raise ValueError('non-finite native CSV')
            data.append(values)
    a = np.asarray(data, dtype=float)
    if len(a) < 2 or 'Time' not in names:
        raise ValueError('at least two native times required')
    columns = {n:a[:,i] for i,n in enumerate(names)}
    if units[names.index('Time')] != 's' or np.any(np.diff(columns['Time']) <= 0):
        raise ValueError('strictly increasing time in seconds required')
    return {'columns':columns, 'units':dict(zip(names,units)),
            'source':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def _intervention_activation(descriptor, dev, start, end):
    condition=descriptor.get('condition',{})
    methods=list(condition.get('methods',[]))
    if not methods:
        return {'status':'not_applicable_control','eligible':True,'reason':None,'methods':[],'proof':[]}
    declared=descriptor.get('intervention_activation')
    if not isinstance(declared,dict):
        return {'status':'failed','eligible':False,
                'reason':'legacy run has no explicit intervention activation diagnostics; invalid pending rerun',
                'methods':methods,'proof':[]}
    if declared.get('status')=='failed':
        return {'status':'failed','eligible':False,'reason':declared.get('reason') or 'descriptor marks source activation failed',
                'methods':methods,'proof':declared.get('proof') or []}
    required=declared.get('required_channels',{})
    observations=descriptor.get('observations',{})
    proof=[];missing=[];failed=[]
    time=dev['columns']['Time']
    for method in methods:
        schedule=condition.get('schedule',{}).get(method,{})
        method_start=float(schedule.get('start_s',start))
        method_end=method_start+float(schedule.get('duration_s',max(0.,end-method_start)))
        if not np.isfinite(method_start) or not np.isfinite(method_end) or method_end<=method_start:
            raise ValueError(method+' intervention schedule must be finite with positive duration')
        declared_window=declared.get('method_windows_s',{}).get(method)
        if declared_window is not None and (not isinstance(declared_window,list) or len(declared_window)!=2
                or any(type(x) is bool or not isinstance(x,(int,float)) or not np.isfinite(x) for x in declared_window)
                or not np.allclose(declared_window,[method_start,method_end],rtol=0,atol=1e-9)):
            raise ValueError(method+' activation window does not match condition schedule')
        before=(time<method_start)&(time>=max(float(time[0]),method_start-1.0))
        active=(time>=method_start)&(time<=method_end)
        if np.count_nonzero(before)<1 or np.count_nonzero(active)<1:
            missing.append(method+':insufficient_window_samples')
            continue
        raw_dose=condition.get('dose_fraction',{}).get(method,1.0)
        dose=_finite_nonnegative(raw_dose,method+' dose_fraction')
        expected_state='off' if dose==0.0 else 'active'
        channel_names=required.get(method,[])
        if not channel_names:
            missing.append(method+':required_channels')
            continue
        for canonical in channel_names:
            column=observations.get(canonical)
            if not column or column not in dev['columns']:
                missing.append(method+':'+canonical)
                continue
            unit=dev['units'].get(column)
            threshold,threshold_unit,comparison=_activation_threshold(declared,method,canonical,unit,expected_state)
            raw_values=dev['columns'][column]
            values=np.abs(raw_values) if comparison.startswith('abs_') or expected_state=='off' else raw_values
            baseline=float(np.max(values[before]));activated=float(np.max(values[active]))
            if expected_state=='off':
                passed=activated<=threshold
                comparison_used='abs_lte'
            else:
                passed=activated>=threshold and activated>baseline
                comparison_used=comparison
            item={'window_s':[method_start,method_end],'method_id':method,'channel':canonical,'column':column,
                  'baseline_statistic':baseline,'active_statistic':activated,'threshold':threshold,
                  'threshold_unit':threshold_unit,'comparison':comparison_used,
                  'dose_fraction':dose,'expected_state':expected_state,'unit':unit,'passed':bool(passed)}
            proof.append(item)
            if not passed:failed.append(method+':'+canonical)
    if missing:
        return {'status':'unverified','eligible':False,'reason':'missing source diagnostics: '+','.join(missing),
                'methods':methods,'proof':proof}
    if failed:
        return {'status':'failed','eligible':False,'reason':'source activation threshold failed: '+','.join(failed),
                'methods':methods,'proof':proof}
    return {'status':'verified','eligible':True,'reason':None,'methods':methods,'proof':proof}


def native_record(run_dir, descriptor, manifest, *, block_id='assumed_environment_0',
                  burning_threshold_kW=.01):
    """Intervention-relative channels, never extrapolated; failed solves stay failures."""
    run_dir=Path(run_dir)
    chid=manifest['input']['chid']
    hrr=read_fds_csv(run_dir/f'{chid}_hrr.csv')
    dev=read_fds_csv(run_dir/f'{chid}_devc.csv')
    if hrr['units'].get('HRR') != 'kW':
        raise ValueError('HRR must be kW')
    start=float(descriptor.get('intervention_start_s',6.))
    end=float(descriptor.get('intervention_end_s',10.))
    stop=min(float(hrr['columns']['Time'][-1]),float(dev['columns']['Time'][-1]))
    lo=max(start,float(hrr['columns']['Time'][0]),float(dev['columns']['Time'][0]))
    if stop<=lo:
        raise ValueError('no shared post-intervention native support')
    times=np.unique(np.concatenate(([lo],hrr['columns']['Time'][(hrr['columns']['Time']>lo)&(hrr['columns']['Time']<stop)],
                                    dev['columns']['Time'][(dev['columns']['Time']>lo)&(dev['columns']['Time']<stop)],[stop])))
    channels={'hrr_kW':np.interp(times,hrr['columns']['Time'],hrr['columns']['HRR']).tolist()}
    expected={'heat_flux_kW_m2':'kW/m2','temperature_C':'C','CO_volume_fraction':'mol/mol','O2_volume_fraction':'mol/mol'}
    missing=[]
    for quantity, column in descriptor.get('observations',{}).items():
        if quantity == 'hrr_kW':
            continue
        quantity={'oxygen_volume_fraction':'O2_volume_fraction','carbon_monoxide_volume_fraction':'CO_volume_fraction'}.get(quantity,quantity)
        if column not in dev['columns']:
            missing.append(quantity)
            continue
        unit=dev['units'][column]
        if quantity in expected and unit!=expected[quantity]:
            raise ValueError(f'{quantity}: expected {expected[quantity]}, got {unit}')
        channels[quantity]=np.interp(times,dev['columns']['Time'],dev['columns'][column]).tolist()
    before=(hrr['columns']['Time']<start)&(hrr['columns']['Time']>=max(0,start-1))
    burning=bool(np.count_nonzero(before)>=2 and np.min(hrr['columns']['HRR'][before])>burning_threshold_kW)
    status='completed' if manifest['status']=='completed' else 'incomplete'
    if not burning:
        status='incomplete'
    activation=_intervention_activation(descriptor,dev,start,end)
    if not activation['eligible']:
        status='incomplete'
    # ``output`` is the conventional leaf for every cached native case and is
    # therefore not a unique identifier.  Include the immutable case-key
    # directory (and an attempt leaf when present) without embedding an
    # absolute machine path.
    case_path_identity='/'.join(run_dir.parts[-2:]) if len(run_dir.parts)>=2 else run_dir.name
    raw_resource=descriptor.get('resource')
    verified_resource=descriptor.get('verified_resource_ledger')
    record={'case_id':case_path_identity,'block_id':block_id,'condition_id':descriptor['condition_id'],
            'location_id':descriptor.get('location_id','TARGET'),
            'run_status':status,'time_s':(times-start).tolist(),'channels':channels,
            'intervention_end_s':end-start,'input_energy_J':descriptor.get('input_energy_J'),
            'native_status':manifest['status'],'pre_intervention_burning':burning,
            'intervention_activation':activation,
            'missing_channels':missing,
            'failure_reason':('no_confirmed_pre_intervention_flame' if not burning else
                              None if activation['eligible'] else 'intervention_activation_'+activation['status']),
            'provenance':{'source':str((run_dir/'run_manifest.json').resolve()),'solver':'FDS',
                          'evidence_type':'native_unvalidated','hrr_sha256':hrr['sha256'],'devc_sha256':dev['sha256'],
                          'time_alignment':'linear within shared support only','units_checked':True,
                          'case_path_identity':case_path_identity,
                          'analysis_criteria':descriptor.get('analysis_criteria'),
                          'intervention_activation':activation,
                          'raw_resource_components':raw_resource,
                          'resource_ledger_status':('verified' if verified_resource is not None else 'unverified_not_used_for_budget_matching')}}
    if verified_resource is not None:
        record['resource']=verified_resource
    return record
