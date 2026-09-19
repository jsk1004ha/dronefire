import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from firelab.campaign import (validate_campaign, run_campaign, import_native_campaign,
                              _auxiliary_names, _auxiliary_fingerprint, _auxiliary_artifacts_complete)
from firelab.native_data import native_record


class CampaignTests(unittest.TestCase):
    def test_auxiliary_cache_binds_config_source_and_output_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dest=root/'output';dest.mkdir()
            (root/'firelab').mkdir()
            source=root/'firelab'/'drone.py';source.write_text('version = 1')
            cfg={'include_drone':False,'transport':{'duration_s':1},'ehd':{}}
            outputs={}
            for name in _auxiliary_names(cfg):
                (dest/name).write_text('{}')
                outputs[name]=hashlib.sha256((dest/name).read_bytes()).hexdigest()
            self.assertFalse(_auxiliary_artifacts_complete(root,dest,cfg))
            (dest/'auxiliary_provenance.json').write_text(json.dumps({
                'fingerprint':_auxiliary_fingerprint(root,cfg),'outputs':outputs}))
            self.assertTrue(_auxiliary_artifacts_complete(root,dest,cfg))
            changed=dict(cfg,transport={'duration_s':2})
            self.assertFalse(_auxiliary_artifacts_complete(root,dest,changed))
            source.write_text('version = 2')
            self.assertFalse(_auxiliary_artifacts_complete(root,dest,cfg))
            source.write_text('version = 1')
            artifact=dest/_auxiliary_names(cfg)[0];artifact.write_text('{"altered":true}')
            self.assertFalse(_auxiliary_artifacts_complete(root,dest,cfg))
            artifact.unlink()
            self.assertFalse(_auxiliary_artifacts_complete(root,dest,cfg))

    def test_partial_override_keeps_preregistered_criteria(self):
        cfg=validate_campaign({'metrics':{'tau_s':8}})
        self.assertEqual(cfg['metrics']['control_id'],'C0')
        self.assertEqual(cfg['metrics']['extinction']['sustain_s'],1.)

    def test_invalid_campaign_fails_before_execution(self):
        for cfg in ({'unknown':1},{'metrics':{'tau_s':-1}},{'metrics':{'tau_s':True}},
                    {'native_timeout_s':True},{'native_timeout_s':float('inf')},
                    {'omp_threads':True},{'reactive':{'case':{'mesh_cell_m':.001}}}):
            with self.assertRaises((ValueError,TypeError)):validate_campaign(cfg)

    def test_unsupported_methods_export_reasons_not_synthetic_results(self):
        # Writes a prepared-only package; no native process and no invented HRR.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'firelab').mkdir();(root/'requirements.txt').write_text('numpy\n')
            r=run_campaign(root,{'condition_ids':['M4','M5'],'execute_native':False,'include_drone':False})
            self.assertEqual(r['status'],'prepared_only')
            self.assertEqual(r['records'],[])
            self.assertTrue(all(x['status']=='needs_model' for x in r['cases']))
            self.assertTrue(all(x['reason']!='model unavailable' for x in r['cases']))
            self.assertEqual(r['comparison_scope'],'descriptive_only_no_C0')
            self.assertTrue((root/'runs'/r['campaign_id']/'research_results.zip').is_file())

    def test_optional_sensor_and_CG_config_passes_to_real_model(self):
        cfg=validate_campaign({'transport':{'sensor':{'latency_s':.2},'drone':{'device_mount_position_m':[0,0,-.1]}}})
        self.assertEqual(cfg['transport']['sensor']['latency_s'],.2)
        self.assertEqual(cfg['transport']['drone']['device_mount_position_m'],[0,0,-.1])

    def test_native_import_requires_every_corrected_supported_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runs'/'study_reference').mkdir(parents=True)
            (root/'runs'/'study_reference'/'campaign.json').write_text(json.dumps({
                'config':validate_campaign({'include_drone':False}),
                'design':[{'id':'C0','methods':[]}],
                'cases':[],
            }),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'exactly match'):
                import_native_campaign(root,{},'study_reference')

    def test_native_record_uses_case_path_and_does_not_promote_raw_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)/'case_key_123'/'output';run.mkdir(parents=True)
            hrr='kW,s\nHRR,Time\n1,5\n1,5.5\n1,6\n0.8,7\n'
            dev='C,m/s,s\nTARGET_T,SOURCE_M1_U,Time\n20,0,5\n21,0,5.5\n22,1,6\n23,1,7\n'
            (run/'sample_hrr.csv').write_text(hrr,encoding='utf-8')
            (run/'sample_devc.csv').write_text(dev,encoding='utf-8')
            descriptor={'condition_id':'M1','condition':{'methods':['M1'],'dose_fraction':{'M1':1.},
                                                        'schedule':{'M1':{'start_s':6.,'duration_s':1.}}},
                        'intervention_start_s':6.,'intervention_end_s':10.,
                        'input_energy_J':None,'resource':[{'kind':'unverified_proxy'}],
                        'analysis_criteria':{'source':'test'},
                        'intervention_activation':{'status':'unverified','active_methods':['M1'],
                                                   'method_windows_s':{'M1':[6.,7.]},
                                                   'required_channels':{'M1':['source_m1_u_m_s']},
                                                   'thresholds':{'M1':{'source_m1_u_m_s':{
                                                       'value':.05,'unit':'m/s','comparison':'abs_gte'}}},'proof':None},
                        'observations':{'temperature_C':'TARGET_T','source_m1_u_m_s':'SOURCE_M1_U','hrr_kW':'HRR'}}
            manifest={'status':'completed','input':{'chid':'sample'}}
            record=native_record(run,descriptor,manifest)
            self.assertEqual(record['case_id'],'case_key_123/output')
            self.assertNotIn('resource',record)
            self.assertEqual(record['provenance']['raw_resource_components'],[{'kind':'unverified_proxy'}])
            self.assertEqual(record['provenance']['resource_ledger_status'],'unverified_not_used_for_budget_matching')
            self.assertEqual(record['provenance']['analysis_criteria'],{'source':'test'})
            self.assertEqual(record['intervention_activation']['status'],'verified')
            self.assertEqual(record['run_status'],'completed')

            legacy=dict(descriptor);legacy.pop('intervention_activation')
            invalid=native_record(run,legacy,manifest)
            self.assertEqual(invalid['run_status'],'incomplete')
            self.assertEqual(invalid['intervention_activation']['status'],'failed')

            # A declared zero-dose sham is eligible only when its diagnostic
            # remains near zero over its own schedule.
            (run/'sample_devc.csv').write_text(
                'C,m/s,s\nTARGET_T,SOURCE_M1_U,Time\n20,0,5\n21,0,5.5\n22,0,6\n23,0,7\n',encoding='utf-8')
            sham=dict(descriptor);sham['condition']={'methods':['M1'],'dose_fraction':{'M1':0.},
                                                     'schedule':{'M1':{'start_s':6.,'duration_s':1.}}}
            off=native_record(run,sham,manifest)
            self.assertEqual(off['intervention_activation']['status'],'verified')
            self.assertEqual(off['intervention_activation']['proof'][0]['expected_state'],'off')

            bad_threshold=dict(descriptor)
            bad_threshold['intervention_activation']=dict(descriptor['intervention_activation'])
            bad_threshold['intervention_activation']['thresholds']={
                'M1':{'source_m1_u_m_s':{'value':float('inf'),'unit':'m/s','comparison':'abs_gte'}}}
            with self.assertRaisesRegex(ValueError,'finite nonnegative'):
                native_record(run,bad_threshold,manifest)

            bad_unit=dict(descriptor)
            bad_unit['intervention_activation']=dict(descriptor['intervention_activation'])
            bad_unit['intervention_activation']['thresholds']={
                'M1':{'source_m1_u_m_s':{'value':.05,'unit':'kg','comparison':'abs_gte'}}}
            with self.assertRaisesRegex(ValueError,'does not match native unit'):
                native_record(run,bad_unit,manifest)
