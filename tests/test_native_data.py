import tempfile
from pathlib import Path
import unittest
from firelab.native_data import read_fds_csv, native_record


class NativeDataTests(unittest.TestCase):
    def test_no_ignition_not_extinction(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'x_hrr.csv').write_text('s,kW\nTime,HRR\n0,0\n5.5,0\n6,0\n8,0\n',encoding='utf-8')
            (p/'x_devc.csv').write_text('s,kW/m2\nTime,TARGET_Q\n0,0\n6,0\n7,0\n',encoding='utf-8')
            r=native_record(p,{'condition_id':'C0','observations':{'heat_flux_kW_m2':'TARGET_Q'}},
                            {'input':{'chid':'x'},'status':'completed'})
            self.assertEqual(r['run_status'],'incomplete')
            self.assertEqual(r['time_s'][-1],1.)
            self.assertFalse(r['pre_intervention_burning'])

    def test_nonfinite_native_data_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.csv';p.write_text('s,kW\nTime,HRR\n0,NaN\n1,1\n')
            with self.assertRaises(ValueError):
                read_fds_csv(p)
