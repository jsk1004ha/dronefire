import csv
import tempfile
from pathlib import Path
import unittest
from firelab.reporting import campaign_reports


class ReportingTests(unittest.TestCase):
    def test_administrative_censor_is_not_reported_as_extinction_time(self):
        fixture={'campaign_id':'unit_fixture','cases':[
            {'condition_id':'C0','condition':{'mode':'control'},'status':'completed'}],
            'analysis':{'extinction_runs':[
                {'condition_id':'C0','extinction':{'event':False,'time_s':None,'observed_through_s':10.}}]}}
        with tempfile.TemporaryDirectory() as tmp:
            campaign_reports(tmp,fixture)
            with (Path(tmp)/'case_matrix.csv').open(encoding='utf-8-sig',newline='') as stream:
                row=next(csv.DictReader(stream))
            self.assertEqual(row['extinction_time_s'],'')
            self.assertEqual(float(row['censor_time_s']),10.)
            self.assertEqual(row['event'],'False')
