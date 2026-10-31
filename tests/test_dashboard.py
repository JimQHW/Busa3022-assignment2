"""Check signal boundaries, calibration separation and offline rendering."""
import json
import math
from pathlib import Path
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard import percentile, classify, build_payload, render_html, add_signal_inputs, yield_rise, signal_message, daily_changes
from pipeline import ROOT, execute
from test_pipeline import workspace_temp

class SignalTests(unittest.TestCase):
    def test_headline_follows_signal_and_identifies_amber_driver(self):
        for a,b,state,phrase in [(False,False,'GREEN','Neither'),(True,False,'AMBER','below its 20-session average'),(False,True,'AMBER','yield rise exceeds'),(True,True,'RED','below trend and yields rising'),(None,True,'UNAVAILABLE','missing data')]:
            row={'price_below_ma20':a,'yield_rise_triggered':b}
            self.assertEqual(classify(a,b),state)
            self.assertIn(phrase,signal_message(row,state)['title'])

    def test_previous_session_change_units_and_missing_values(self):
        rows=[dict(date='2026-10-23',nasdaq_close=25955.34,treasury_yield_pct=5.0),dict(date='2026-10-26',nasdaq_close=26169.38,treasury_yield_pct=5.0)]
        self.assertEqual(daily_changes(rows)['nasdaq_points'],214.04)
        self.assertEqual(daily_changes(rows)['treasury_bps'],0)
        rows[-1]['treasury_yield_pct']=4.9
        self.assertEqual(daily_changes(rows)['treasury_bps'],-10)
        rows[0]['treasury_yield_pct']=None
        self.assertIsNone(daily_changes(rows)['treasury_bps'])

    def test_yield_threshold_boundary_and_nonpositive_changes(self):
        self.assertTrue(yield_rise(17,17))
        self.assertFalse(yield_rise(16.99,17))
        self.assertFalse(yield_rise(0,0))
        self.assertFalse(yield_rise(-24,17))
        self.assertIsNone(yield_rise(None,17))

    def test_percentile_interpolation(self):
        self.assertEqual(percentile([40, 10, 30, 20], .8), 34)
        self.assertEqual(percentile([40, 10, 30, 20], .95), 38.5)

    def test_exact_thresholds_and_missing_values(self):
        self.assertEqual(classify(False, False), 'GREEN')
        self.assertEqual(classify(True, False), 'AMBER')
        self.assertEqual(classify(False, True), 'AMBER')
        self.assertEqual(classify(True, True), 'RED')
        self.assertEqual(classify(None, True), 'UNAVAILABLE')
        self.assertEqual(classify(False, None), 'UNAVAILABLE')

    def test_yield_change_units_endpoints_and_price_equality(self):
        rows=[dict(date=str(i), treasury_yield_pct=4.7, nasdaq_close=100, nasdaq_ma20=100) for i in range(22)]
        rows[20]['treasury_yield_pct']=5.0
        rows[1]['treasury_yield_pct']=None
        result=add_signal_inputs(rows)
        self.assertIsNone(result[19]['yield_change_20_bps'])
        self.assertAlmostEqual(result[20]['yield_change_20_bps'],30)
        self.assertFalse(result[20]['price_below_ma20'])
        self.assertIsNone(result[21]['yield_change_20_bps'])

    def test_empty_calibration_rejected(self):
        with self.assertRaises(ValueError): percentile([], .8)

class DashboardTests(unittest.TestCase):
    def test_real_calibration_is_before_display_and_no_lookahead(self):
        with workspace_temp() as d:
            run, _ = execute(ROOT/'data'/'raw', Path(d))
            payload = build_payload(run)
            signal = payload['signal']
            self.assertLess(signal['calibration_end'], payload['summary']['display_start'])
            self.assertGreaterEqual(signal['calibration_observations'], 40)
            self.assertEqual(sum(signal['counts'].values()), 63)
            self.assertEqual(signal['latest'], 'AMBER')
            # Alter a display-only yield. Calibration must be unchanged.
            import csv
            p=run/'curated_sessions.csv'
            with p.open(newline='') as f:
                reader=csv.DictReader(f); fields=reader.fieldnames; rows=list(reader)
            rows[-1]['treasury_yield_pct']='99.9'
            with p.open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            after=build_payload(run)
            self.assertEqual(signal['yield_threshold_bps'], after['signal']['yield_threshold_bps'])
            self.assertEqual(after['signal']['latest'],'RED')

    def test_offline_page_contains_all_components_and_explicit_gap(self):
        with workspace_temp() as d:
            run, _ = execute(ROOT/'data'/'raw', Path(d))
            payload=build_payload(run); html=render_html(payload)
            for component in ['id="trend"', 'id="macro"', 'id="rag"', 'id="download"']:
                self.assertIn(component,html)
            self.assertNotIn('<script src=',html)
            self.assertNotIn('__DATA__',html)
            gap=next(r for r in payload['rows'] if r['date']=='2026-10-12')
            self.assertIsNone(gap['treasury_yield_pct'])
            self.assertTrue(gap['yield_missing'])
            self.assertIsNotNone(gap['nasdaq_close'])
            self.assertEqual(gap['rag'],'UNAVAILABLE')

    def test_embedded_json_cannot_close_script(self):
        html=render_html({'note':'</script><script>alert(1)</script>'})
        self.assertIn('\\u003c/script>',html)
        self.assertNotIn('"note": "</script>',html)
