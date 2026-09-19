"""End-to-end native experiment orchestration with resumable, hashed case identity."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import uuid
import math
import zipfile
from .intake import json_write
from .experiments import build_design, stable_hash


def _source_hashes(root):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(root)/'firelab').glob('*.py')}


def _write_reanalysis_snapshot(root, dest):
    """Archive current repair code without labelling it as the original snapshot."""
    root=Path(root);dest=Path(dest)
    target=dest/'reanalysis_source_snapshot.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((root/'firelab').glob('*.py')):archive.write(file,'firelab/'+file.name)
        archive.write(root/'requirements.txt','requirements.txt')
    return target


def _stamp_analysis_contract(descriptor, metrics):
    """Persist the exact campaign criteria used after native generation."""
    descriptor['analysis_criteria']=deepcopy(metrics)
    descriptor['analysis_criteria_source']='campaign config saved before analysis'
    contract=descriptor.get('observation_contract')
    if isinstance(contract,dict):
        gate=contract.get('preregistered_extinction_gate')
        if isinstance(gate,dict):
            gate['maximum_hrr_kW']=metrics['extinction']['hrr_threshold_kW']
            gate['minimum_hold_s']=metrics['extinction']['sustain_s']
            gate['reignition_threshold_kW']=metrics['extinction']['reignition_threshold_kW']
            gate['reignition_followup_s']=metrics['extinction']['reignition_followup_s']


def _finish_numerical_and_drone(root, dest, result):
    """Regenerate cheap verified models/exports without rerunning native CFD."""
    cfg=result['config']
    from .acoustics import verification
    result['acoustics']=verification(dest)['status']
    from .ehd import DEFAULT_CONFIG,simulate_ehd,verification as ehd_verification
    ehd_config=cfg.get('ehd',deepcopy(DEFAULT_CONFIG))
    json_write(dest/'ehd_numerical_model.json',simulate_ehd(ehd_config))
    result['ehd_verification']=ehd_verification(dest)['status']
    if cfg.get('include_drone'):
        from .physics import simulate_method
        from .drone_study import run_drone_study,write_drone_study_exports
        physical={m:simulate_method(cfg['transport'],m) for m in ('M1','M2','M3','M4','M5')}
        drone=run_drone_study(cfg['transport'],physical)
        write_drone_study_exports(drone,dest)
        result['drone_summary']={m:{'thermal':v['thermal_assessment_status'],'fire_retention':v['fire_retention']} for m,v in drone['methods'].items()}
    json_write(Path(dest)/'auxiliary_provenance.json',{
        'fingerprint':_auxiliary_fingerprint(root,cfg),
        'outputs':{name:hashlib.sha256((Path(dest)/name).read_bytes()).hexdigest()
                   for name in _auxiliary_names(cfg)}})


def _auxiliary_names(config):
    required=['acoustic_verification.json','ehd_numerical_model.json','ehd_verification.json']
    if config.get('include_drone'):
        required.extend(['drone_study.json','drone_feasibility.csv','drone_requirements.csv','drone_mission_series.csv'])
    return required


def _auxiliary_fingerprint(root, config):
    modules=('physics.py','drone.py','drone_study.py','config.py','acoustics.py','ehd.py')
    return stable_hash({'transport':config.get('transport'), 'ehd':config.get('ehd'),
                        'include_drone':config.get('include_drone'),
                        'source':{n:hashlib.sha256((Path(root)/'firelab'/n).read_bytes()).hexdigest()
                                  for n in modules if (Path(root)/'firelab'/n).is_file()}})


def _auxiliary_artifacts_complete(root, dest, config):
    try:
        manifest=json.loads((Path(dest)/'auxiliary_provenance.json').read_text(encoding='utf-8'))
        return (manifest['fingerprint']==_auxiliary_fingerprint(root,config)
                and all(hashlib.sha256((Path(dest)/name).read_bytes()).hexdigest()==manifest['outputs'].get(name)
                        for name in _auxiliary_names(config)))
    except (OSError,ValueError,KeyError):
        return False


def _final_campaign_status(result):
    if not result['config'].get('execute_native',True):return 'prepared_only'
    if not result.get('records'):return 'no_analyzable_records'
    gaps=any(case.get('status')!='completed' or case.get('observation_status','completed')!='completed'
             or case.get('data_error') or case.get('data_warning') for case in result.get('cases',[]))
    return 'partial_analysis_with_evidence_gaps' if gaps else 'completed_native_analysis'


def _unsupported_reason(descriptor):
    capabilities=descriptor.get('physical_scope',{}).get('method_capabilities',{})
    reasons=[]
    for method in descriptor.get('unsupported_methods',[]):
        reason=capabilities.get(method,{}).get('reason')
        if reason:reasons.append(f'{method}: {reason}')
    return '; '.join(reasons) or descriptor.get('reason') or descriptor.get('reasons') or 'model unavailable'


def _condition_signature(condition):
    """Fields that define treatment identity; metadata remains provenance."""
    return {key:deepcopy(condition.get(key)) for key in ('id','methods','order','mode','schedule','dose_fraction')}


def defaults():
    from .reactive import default_reactive_config
    from .ehd import DEFAULT_CONFIG
    return {'reactive':default_reactive_config(), 'transport':{}, 'native_timeout_s':300.,
            'ehd':deepcopy(DEFAULT_CONFIG),
            'omp_threads':1, 'supplemental':True, 'selected_combinations':[],
            'condition_ids':None,'execute_native':True, 'include_drone':True,
            'metrics':{'control_id':'C0','tau_s':10.,
                       'extinction':{'hrr_threshold_kW':.1,'sustain_s':1.,
                                     'reignition_threshold_kW':.2,'reignition_followup_s':4.},
                       'source':'declared research screening criteria; not experimentally calibrated',
                       'declared_before_results':True},
            'exposure_criteria':{
                'heat_flux_kW_m2':{'limit':1.,'direction':'above','source':'illustrative instrument threshold, not human tenability'},
                'temperature_C':{'limit':50.,'direction':'above','source':'illustrative instrument threshold, not human tenability'},
                'CO_volume_fraction':{'limit':.001,'direction':'above','source':'illustrative channel threshold, not human tenability'},
                'O2_volume_fraction':{'limit':.18,'direction':'below','source':'illustrative channel threshold, not human tenability'}}}


def validate_campaign(overrides=None):
    from .config import validate_config
    cfg=defaults()
    if overrides is not None:
        if not isinstance(overrides,dict):raise ValueError('campaign must be a JSON object')
        def merge(target,source,prefix=''):
            for key,value in source.items():
                if key not in target:raise ValueError('unknown campaign option '+prefix+key)
                if isinstance(target[key],dict) and isinstance(value,dict) and key!='transport':
                    merge(target[key],value,prefix+key+'.')
                else:target[key]=deepcopy(value)
        merge(cfg,overrides)
    if type(cfg['native_timeout_s']) is bool or not isinstance(cfg['native_timeout_s'],(int,float)) \
            or not math.isfinite(cfg['native_timeout_s']) or not 1<=cfg['native_timeout_s']<=10800:
        raise ValueError('native_timeout_s must be 1..10800')
    if type(cfg['omp_threads']) is not int or not 1<=cfg['omp_threads']<=16:
        raise ValueError('omp_threads must be integer 1..16')
    for key in ('execute_native','include_drone','supplemental'):
        if type(cfg[key]) is not bool:raise ValueError(key+' must be bool')
    ids=cfg['condition_ids']
    if ids is not None and (not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or len(ids)>100):
        raise ValueError('condition_ids must be null or <=100 string IDs')
    cfg['transport']=validate_config(cfg['transport'])
    from .reactive import capabilities
    capabilities(cfg['reactive'])
    c=cfg['reactive']['case'];cell=c['mesh_cell_m']
    cells=math.prod(math.ceil((c[k][1]-c[k][0])/cell) for k in ('domain_x_m','domain_y_m','domain_z_m'))
    if cells>500000 or c['duration_s']>120:raise ValueError('campaign limits: 500000 cells, 120s; original benchmark uses separate native runner')
    metrics=cfg['metrics']
    if metrics['declared_before_results'] is not True or not metrics['source']:
        raise ValueError('preregistered metric source required')
    if type(metrics['tau_s']) is bool or not isinstance(metrics['tau_s'],(int,float)) \
            or not math.isfinite(metrics['tau_s']) or not 0<metrics['tau_s']<=c['duration_s']-c['intervention_start_s']:
        raise ValueError('tau_s must be inside post-intervention observation window')
    for key,value in metrics['extinction'].items():
        if type(value) is bool or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError('extinction criteria must be finite positive values')
    for channel,criterion in cfg['exposure_criteria'].items():
        if criterion.get('direction') not in ('above','below') or not criterion.get('source') or not math.isfinite(criterion['limit']):
            raise ValueError('invalid exposure criterion '+channel)
    # JSON's finite contract also rejects nonfinite nested values before running.
    stable_hash(cfg)
    return cfg


def run_campaign(root, overrides=None, progress=None, cancel_event=None):
    from .reactive import build_reactive_case, capabilities
    from .native import find_bundled_fds, run_fds_case, validate_fds_cache
    from .native_data import native_record
    from .study_analysis import analyze_study, latin_hypercube, split_cases
    from .exposure import summarize_exposure
    from .reporting import campaign_reports
    root=Path(root).resolve();cfg=validate_campaign(overrides)
    start=datetime.now(timezone.utc)
    cid=start.strftime('study_%Y%m%dT%H%M%S_')+uuid.uuid4().hex[:8]
    dest=root/'runs'/cid;dest.mkdir(parents=True)
    casecfg=cfg['reactive']['case']
    design=build_design(casecfg['intervention_start_s'],casecfg['intervention_end_s']-casecfg['intervention_start_s'],
                        supplemental=cfg['supplemental'],selected_combinations=cfg['selected_combinations'])
    if cfg['condition_ids'] is not None:
        unknown=set(cfg['condition_ids'])-{x['id'] for x in design}
        if unknown:raise ValueError('unknown condition IDs: '+str(sorted(unknown)))
        design=[x for x in design if x['id'] in cfg['condition_ids']]
    if not design:raise ValueError('empty study design')
    code=_source_hashes(root)
    result={'campaign_id':cid,'started_utc':start.isoformat(),'status':'running','config':cfg,
            'config_sha256':stable_hash(cfg),'code_sha256':code,'capabilities':capabilities(cfg['reactive']),
            'cases':[],'records':[],'analysis':{},'exposure':{},'design':design,
            'declared_scope':'native proxy fire scenarios + analytical flight; not five experimentally validated suppression methods'}
    result['comparison_scope']='paired_with_C0' if any(c['id']=='C0' for c in design) else 'descriptive_only_no_C0'
    json_write(dest/'config.json',cfg);json_write(dest/'experiment_design.json',design)
    with zipfile.ZipFile(dest/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((root/'firelab').glob('*.py')):archive.write(file,'firelab/'+file.name)
        archive.write(root/'requirements.txt','requirements.txt')
    json_write(root/'runs'/'campaign_latest.json',{'campaign_id':cid})
    executable=find_bundled_fds(root)
    runtime_hash=hashlib.sha256(Path(executable).read_bytes()).hexdigest() if executable else None

    def checkpoint(message, fraction):
        json_write(dest/'campaign.json',result)
        if progress:progress(fraction,message)

    for i,condition in enumerate(design):
        if cancel_event is not None and cancel_event.is_set():
            result['status']='cancelled';break
        checkpoint(f"native {i+1}/{len(design)} · {condition['id']}",.05+.7*i/len(design))
        key=stable_hash({'condition':condition,'reactive':cfg['reactive'],
                         'generator':code.get('reactive.py'),'runtime':runtime_hash,
                         'omp_threads':cfg['omp_threads']})[:24]
        case_dir=root/'runs'/'native_cases'/key
        descriptor=build_reactive_case(cfg['reactive'],condition,case_dir/'input')
        _stamp_analysis_contract(descriptor,cfg['metrics'])
        descriptor['intervention_start_s']=casecfg['intervention_start_s']
        descriptor['intervention_end_s']=casecfg['intervention_end_s']
        descriptor['input_energy_J']=descriptor.get('resource_summary',{}).get('input_energy_J')
        row={'condition_id':condition['id'],'condition':condition,'descriptor':descriptor,
             'status':descriptor['status'],'run_directory':str(case_dir/'output')}
        result['cases'].append(row)
        if descriptor['status']!='ready':
            row['reason']=_unsupported_reason(descriptor)
            continue
        if not cfg['execute_native']:
            row['status']='prepared_not_executed';continue
        if executable is None:
            row.update(status='runtime_unavailable',reason='FDS runtime not found');continue
        out=case_dir/'output';manifest_path=out/'run_manifest.json'
        cached=None
        input_hash=hashlib.sha256(Path(descriptor['input_path']).read_bytes()).hexdigest()
        if manifest_path.is_file():
            candidate=json.loads(manifest_path.read_text(encoding='utf-8'))
            if (candidate.get('status')=='completed' and candidate.get('input',{}).get('sha256')==input_hash
                    and candidate.get('runtime',{}).get('sha256')==runtime_hash):
                cache_check=validate_fds_cache(out,candidate)
                if cache_check['valid']:
                    cached=candidate;row['cache_validation']=cache_check
                else:
                    row['cache_invalidated']=cache_check['reasons']
        if cached:
            row['cache_reused']=True;manifest=cached
        else:
            # Failed/incomplete attempts remain intact; rerun into a fresh attempt.
            if out.exists():
                out=case_dir/('attempt_'+uuid.uuid4().hex[:8]);row['run_directory']=str(out)
            try:
                manifest=run_fds_case(descriptor['input_path'],out,executable=executable,trusted_root=root,
                                      timeout_s=cfg['native_timeout_s'],omp_threads=cfg['omp_threads'])
            except Exception as exc:
                row.update(status='solver_failed',reason=str(exc));continue
        row.update(status=manifest['status'],native=manifest)
        try:
            record=native_record(out,descriptor,manifest)
            result['records'].append(record)
            row['observation_status']=record['run_status']
            row['observation_reason']=record.get('failure_reason')
            if not record.get('intervention_activation',{}).get('eligible',False):
                row['data_warning']=record['intervention_activation'].get('reason')
        except (ValueError,OSError,KeyError) as exc:
            row['data_error']=str(exc)
        checkpoint(f"{condition['id']} · {row['status']}",.05+.7*(i+1)/len(design))
    checkpoint('소화·재점화·노출 분석',.77)
    if result['records']:
        specs=[{'control_id':'C0','combination_id':x['id'],'partial_single_ids':x['partial_controls']}
               for x in design if 'partial_controls' in x]
        result['analysis']=analyze_study(result['records'],cfg['metrics'],synergy_specs=specs)
        result['exposure']=summarize_exposure(result['records'],cfg['exposure_criteria'],cfg['metrics']['tau_s'])
    checkpoint('D0–D5·센서·열·탑재 요구조건 계산',.82)
    _finish_numerical_and_drone(root,dest,result)
    if result['status']!='cancelled':
        result['status']=_final_campaign_status(result)
    result['finished_utc']=datetime.now(timezone.utc).isoformat()
    checkpoint('두 연구 보고서·CSV·PNG·재현 ZIP 저장',.96)
    campaign_reports(dest,result)
    checkpoint('연구 실행 완료 · 항목별 근거/미지원 상태 확인',1.)
    return result


def import_native_campaign(root, source_runs, reference_campaign_id):
    """Assemble a new study from completed, hash-validated native runs.

    This path never invokes FDS.  It is intended for independently executed
    corrected cases whose immutable outputs must replace a quarantined study
    without rewriting that historical campaign.
    """
    from .native import validate_fds_cache
    from .native_data import native_record
    from .study_analysis import analyze_study
    from .exposure import summarize_exposure
    from .reporting import campaign_reports
    root=Path(root).resolve()
    if not re.fullmatch(r'study_[A-Za-z0-9_]+',reference_campaign_id):
        raise ValueError('invalid reference study ID')
    if not isinstance(source_runs,dict) or any(not isinstance(k,str) or not isinstance(v,(str,Path)) for k,v in source_runs.items()):
        raise ValueError('source_runs must map condition IDs to run directories')
    reference_path=root/'runs'/reference_campaign_id/'campaign.json'
    reference=json.loads(reference_path.read_text(encoding='utf-8'))
    design=deepcopy(reference['design'])
    expected={x['id'] for x in design if x['id'] in {'C0','M1','M2','M3'}}
    if set(source_runs)!=expected:
        raise ValueError('corrected native sources must exactly match '+str(sorted(expected)))
    # The corrected descriptors are the authoritative reactive configuration.
    # This also avoids carrying obsolete generator-only keys from the
    # quarantined campaign into a newly validated config.
    prepared_sources={}
    reactive_hash=None
    for condition_id,run in source_runs.items():
        run_dir=Path(run).resolve()
        descriptor_path=run_dir/'case_manifest.json';manifest_path=run_dir/'run_manifest.json'
        descriptor=json.loads(descriptor_path.read_text(encoding='utf-8'))
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        current_reactive_hash=stable_hash(descriptor['config'])
        if reactive_hash is not None and current_reactive_hash!=reactive_hash:
            raise ValueError('corrected native descriptors do not share one reactive config')
        reactive_hash=current_reactive_hash
        prepared_sources[condition_id]=(run_dir,descriptor_path,manifest_path,descriptor,manifest)
    config_override=deepcopy(reference['config'])
    config_override['reactive']=deepcopy(next(iter(prepared_sources.values()))[3]['config'])
    cfg=validate_campaign(config_override)
    start=datetime.now(timezone.utc)
    cid=start.strftime('study_%Y%m%dT%H%M%S_corrected_')+uuid.uuid4().hex[:8]
    dest=root/'runs'/cid;dest.mkdir(parents=True)
    current_hashes=_source_hashes(root)
    reference_sha=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    result={'campaign_id':cid,'started_utc':start.isoformat(),'status':'importing_validated_native_outputs',
            'config':cfg,'config_sha256':stable_hash(cfg),'code_sha256':current_hashes,
            'capabilities':deepcopy(reference.get('capabilities',{})),'cases':[],'records':[],
            'analysis':{},'exposure':{},'design':design,
            'comparison_scope':'paired_with_C0' if any(x['id']=='C0' for x in design) else 'descriptive_only_no_C0',
            'declared_scope':reference.get('declared_scope'),
            'import_provenance':{'reference_campaign_id':reference_campaign_id,
                                 'reference_campaign_sha256':reference_sha,
                                 'native_solvers_rerun':False,'source_runs':{}}}
    json_write(dest/'config.json',cfg);json_write(dest/'experiment_design.json',design)
    with zipfile.ZipFile(dest/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((root/'firelab').glob('*.py')):archive.write(file,'firelab/'+file.name)
        archive.write(root/'requirements.txt','requirements.txt')
    reference_cases={x['condition_id']:x for x in reference.get('cases',[])}
    try:
        for condition in design:
            condition_id=condition['id']
            if condition_id not in source_runs:
                old=reference_cases.get(condition_id,{})
                descriptor=deepcopy(old.get('descriptor',{}))
                row={'condition_id':condition_id,'condition':condition,'descriptor':descriptor,
                     'status':'needs_model','reason':_unsupported_reason(descriptor)}
                result['cases'].append(row)
                continue
            run_dir,descriptor_path,manifest_path,descriptor,manifest=prepared_sources[condition_id]
            if descriptor.get('condition_id')!=condition_id \
                    or _condition_signature(descriptor.get('condition',{}))!=_condition_signature(condition):
                raise ValueError(condition_id+' descriptor does not match saved experiment design')
            cache_check=validate_fds_cache(run_dir,manifest)
            if not cache_check['valid']:
                raise ValueError(condition_id+' native cache integrity failed: '+'; '.join(cache_check['reasons']))
            analysis_descriptor=deepcopy(descriptor)
            _stamp_analysis_contract(analysis_descriptor,cfg['metrics'])
            case_cfg=cfg['reactive']['case']
            analysis_descriptor['intervention_start_s']=case_cfg['intervention_start_s']
            analysis_descriptor['intervention_end_s']=case_cfg['intervention_end_s']
            analysis_descriptor['input_energy_J']=analysis_descriptor.get('resource_summary',{}).get('input_energy_J')
            record=native_record(run_dir,analysis_descriptor,manifest)
            result['records'].append(record)
            row={'condition_id':condition_id,'condition':condition,'descriptor':descriptor,
                 'status':manifest['status'],'run_directory':str(run_dir),'native':manifest,
                 'cache_validation':cache_check,'observation_status':record['run_status'],
                 'observation_reason':record.get('failure_reason')}
            if not record.get('intervention_activation',{}).get('eligible',False):
                row['data_warning']=record['intervention_activation'].get('reason')
            result['cases'].append(row)
            result['import_provenance']['source_runs'][condition_id]={
                'run_directory':str(run_dir),
                'descriptor_sha256':hashlib.sha256(descriptor_path.read_bytes()).hexdigest(),
                'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                'cache_validation':cache_check,
            }
        if result['records']:
            specs=[{'control_id':'C0','combination_id':x['id'],'partial_single_ids':x['partial_controls']}
                   for x in design if 'partial_controls' in x]
            result['analysis']=analyze_study(result['records'],cfg['metrics'],synergy_specs=specs)
            result['exposure']=summarize_exposure(result['records'],cfg['exposure_criteria'],cfg['metrics']['tau_s'])
        # Recompute analytical verification and D0-D5 exports with the current
        # source/config.  Historical exports are not silently relabelled.
        _finish_numerical_and_drone(root,dest,result)
        result['import_provenance']['auxiliary_artifacts_reused']=False
        result['status']=_final_campaign_status(result)
        result['finished_utc']=datetime.now(timezone.utc).isoformat()
        campaign_reports(dest,result)
        json_write(root/'runs'/'campaign_latest.json',{'campaign_id':cid})
        return result
    except Exception as exc:
        result['status']='native_import_failed';result['finished_utc']=datetime.now(timezone.utc).isoformat()
        result['failure']={'type':type(exc).__name__,'reason':str(exc)}
        json_write(dest/'campaign.json',result)
        raise


def latest_campaign(root):
    root=Path(root);p=root/'runs'/'campaign_latest.json'
    if not p.exists():return None
    cid=json.loads(p.read_text(encoding='utf-8'))['campaign_id']
    if not re.fullmatch(r'study_[A-Za-z0-9_]+',cid):raise ValueError('invalid campaign id')
    f=root/'runs'/cid/'campaign.json'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else None


def reanalyze_campaign(root, campaign_id):
    """Refresh analysis from hashed native files without repeating expensive solvers."""
    from .native_data import native_record
    from .native import validate_fds_cache
    from .study_analysis import analyze_study
    from .exposure import summarize_exposure
    from .reporting import campaign_reports
    root=Path(root).resolve()
    if not re.fullmatch(r'study_[A-Za-z0-9_]+',campaign_id):raise ValueError('invalid study ID')
    dest=root/'runs'/campaign_id
    result=json.loads((dest/'campaign.json').read_text(encoding='utf-8'))
    recovered_from=result.get('reanalysis',{}).get('recovered_from_status',result.get('status'))
    original_hashes=deepcopy(result.get('code_sha256',{}))
    current_hashes=_source_hashes(root)
    reanalysis_started=datetime.now(timezone.utc).isoformat()
    try:
        records=[]
        for case in result['cases']:
            if not case.get('native'):
                if case.get('descriptor',{}).get('status')!='ready':
                    case['reason']=_unsupported_reason(case['descriptor'])
                continue
            try:
                run_dir=Path(case['run_directory'])
                cache_check=validate_fds_cache(run_dir,case['native'])
                case['cache_validation']=cache_check
                if not cache_check['valid']:
                    raise ValueError('native cache integrity failed: '+'; '.join(cache_check['reasons']))
                # Preserve the original saved descriptor/preregistration.  A
                # repaired analysis applies the campaign config explicitly to
                # a working copy and records any difference as an override.
                original_descriptor=case['descriptor']
                analysis_descriptor=deepcopy(original_descriptor)
                original_gate=deepcopy(original_descriptor.get('observation_contract',{}).get('preregistered_extinction_gate'))
                _stamp_analysis_contract(analysis_descriptor,result['config']['metrics'])
                applied_gate=analysis_descriptor.get('observation_contract',{}).get('preregistered_extinction_gate')
                case['reanalysis_criteria_override']={
                    'source':'saved campaign config; applied during repair without rewriting original descriptor',
                    'original_descriptor_gate':original_gate,
                    'applied_gate':deepcopy(applied_gate),
                    'criterion_mismatch':original_gate!=applied_gate,
                }
                record=native_record(run_dir,analysis_descriptor,case['native'])
                case['observation_status']=record['run_status'];case.pop('data_error',None)
                case['observation_reason']=record.get('failure_reason')
                if not record.get('intervention_activation',{}).get('eligible',False):
                    case['data_warning']=record['intervention_activation'].get('reason')
                else:case.pop('data_warning',None)
                records.append(record)
            except (ValueError,OSError,KeyError) as exc:
                case['data_error']=str(exc)
        result['records']=records
        result['analysis']={};result['exposure']={}
        if records:
            specs=[{'control_id':'C0','combination_id':x['id'],'partial_single_ids':x['partial_controls']} for x in result['design'] if 'partial_controls' in x]
            result['analysis']=analyze_study(records,result['config']['metrics'],synergy_specs=specs)
            result['exposure']=summarize_exposure(records,result['config']['exposure_criteria'],result['config']['metrics']['tau_s'])
        reused_auxiliary=_auxiliary_artifacts_complete(root,dest,result['config'])
        if not reused_auxiliary:_finish_numerical_and_drone(root,dest,result)
        finished=datetime.now(timezone.utc).isoformat()
        result['status']=_final_campaign_status(result)
        result['finished_utc']=finished
        result['original_code_sha256']=original_hashes
        result['reanalysis']={
            'status':'completed','started_utc':reanalysis_started,'finished_utc':finished,
            'recovered_from_status':recovered_from,
            'original_source_sha256':original_hashes,
            'reanalysis_source_sha256':current_hashes,
            'source_changed':original_hashes!=current_hashes,
            'native_solvers_rerun':False,
            'auxiliary_artifacts_reused':reused_auxiliary,
        }
        _write_reanalysis_snapshot(root,dest)
        campaign_reports(dest,result)
        return result
    except Exception as exc:
        finished=datetime.now(timezone.utc).isoformat()
        result['status']='reanalysis_failed';result['finished_utc']=finished
        result['original_code_sha256']=original_hashes
        result['reanalysis']={
            'status':'failed','started_utc':reanalysis_started,'finished_utc':finished,
            'recovered_from_status':recovered_from,'failure_type':type(exc).__name__,
            'failure_reason':str(exc),'original_source_sha256':original_hashes,
            'reanalysis_source_sha256':current_hashes,'native_solvers_rerun':False,
        }
        json_write(dest/'campaign.json',result)
        raise
