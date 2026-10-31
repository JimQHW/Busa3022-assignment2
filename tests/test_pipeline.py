"""Meaningful correctness and failure-path tests; all failures use synthetic copies."""
import csv
import io
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import ROOT, DataQualityError, execute, metric_rows, parse_source, transform

@contextmanager
def workspace_temp():
    base=(ROOT/'test_outputs').resolve()
    base.mkdir(exist_ok=True)
    path=Path(tempfile.mkdtemp(dir=base)).resolve()
    if base not in path.parents:
        raise RuntimeError('Temporary directory escaped test workspace')
    try:
        yield path
    finally:
        if base in path.resolve().parents:
            shutil.rmtree(path)

class MetricTests(unittest.TestCase):
    def test_mean_window_and_warmup(self):
        out=metric_rows(list(range(1,26)))
        self.assertIsNone(out[18]['nasdaq_ma20'])
        self.assertEqual(out[19]['nasdaq_ma20'], 10.5)
        self.assertEqual(out[20]['nasdaq_ma20'], 11.5)

    def test_return(self):
        out=metric_rows([100,110,99])
        self.assertIsNone(out[0]['nasdaq_return_1d'])
        self.assertAlmostEqual(out[1]['nasdaq_return_1d'], .1)
        self.assertAlmostEqual(out[2]['nasdaq_return_1d'], -.1)

    def test_sample_volatility_and_warmup(self):
        prices=[100]
        expected_returns=[.01,-.01]*7
        for r in expected_returns: prices.append(prices[-1]*(1+r))
        out=metric_rows(prices)
        self.assertIsNone(out[13]['nasdaq_volatility_14d'])
        expected=math.sqrt(14*.01**2/13)
        self.assertAlmostEqual(out[14]['nasdaq_volatility_14d'], expected, places=12)

    def test_missing_session_not_bridged(self):
        out=metric_rows([100]*20+[None]+[100]*20)
        self.assertIsNone(out[20]['nasdaq_return_1d'])
        self.assertIsNone(out[21]['nasdaq_return_1d'])
        self.assertIsNone(out[39]['nasdaq_ma20'])
        self.assertEqual(out[40]['nasdaq_ma20'], 100)
        self.assertIsNone(out[34]['nasdaq_volatility_14d'])
        self.assertEqual(out[35]['nasdaq_volatility_14d'], 0)

class FailureTests(unittest.TestCase):
    def test_rejects_and_missing_reconcile(self):
        with workspace_temp() as d:
            p=Path(d)/'sample.csv'
            p.write_text('observation_date,NASDAQCOM\n2026-04-01,100\n2026-04-02,\nbad,101\n2026-04-06,-2\n2026-04-01,100\n2026-04-07,nan\n')
            events=[]
            table, counts=parse_source(p,'NASDAQCOM',events)
            self.assertEqual((counts['input_rows'],counts['valid_rows'],counts['missing_rows'],counts['rejected_rows']),(6,1,1,4))
            self.assertEqual(len(events),5)
            self.assertIsNone(table['2026-04-02'])

    def test_conflicting_duplicate_blocks(self):
        with workspace_temp() as d:
            p=Path(d)/'sample.csv'
            p.write_text('observation_date,DGS10\n2026-04-01,4\n2026-04-01,5\n')
            with self.assertRaises(DataQualityError): parse_source(p,'DGS10',[])

    def test_missing_expected_session_blocks(self):
        from datetime import date
        events=[]
        with self.assertRaises(DataQualityError):
            transform({'2026-04-01':100},{},date(2026,4,1),date(2026,4,2),events)
        self.assertTrue(any(e['issue']=='MISSING_EXPECTED_SESSION' for e in events))

    def test_failed_schema_preserves_last_good_and_raw(self):
        with workspace_temp() as d:
            base=Path(d); inputs=base/'inputs';inputs.mkdir()
            for name in ['DGS10.csv','NASDAQCOM.csv']:shutil.copy2(ROOT/'data'/'raw'/name,inputs/name)
            run, summary=execute(inputs,base/'out')
            old=(base/'out'/'latest.json').read_bytes()
            self.assertEqual((run/'raw'/'DGS10.csv').read_bytes(),(inputs/'DGS10.csv').read_bytes())
            p=inputs/'DGS10.csv';p.write_text(p.read_text().replace('DGS10','RENAMED_YIELD',1))
            with self.assertRaises(DataQualityError):execute(inputs,base/'out')
            self.assertEqual(old,(base/'out'/'latest.json').read_bytes())
            manifests=[json.loads(p.read_text()) for p in (base/'out'/'runs').glob('*/manifest.json')]
            self.assertEqual(sorted(x['status'] for x in manifests),['FAILED','SUCCESS'])

class SnapshotTests(unittest.TestCase):
    def test_real_data_independent_recalculation_and_repeatability(self):
        with workspace_temp() as d:
            run, summary=execute(ROOT/'data'/'raw',Path(d))
            with (ROOT/'data'/'raw'/'NASDAQCOM.csv').open() as f:
                prices=[float(r['NASDAQCOM']) for r in csv.DictReader(f) if r['NASDAQCOM'] and r['observation_date']>='2026-04-01']
            rets=[prices[i]/prices[i-1]-1 for i in range(1,len(prices))][-14:]
            mean=sum(rets)/14
            expected=math.sqrt(sum((r-mean)**2 for r in rets)/13)
            latest=summary['latest_metrics']
            self.assertAlmostEqual(latest['nasdaq_ma20'],sum(prices[-20:])/20,places=9)
            self.assertAlmostEqual(latest['nasdaq_volatility_14d'],expected,places=12)
            self.assertEqual(summary['display_sessions'],63)
            self.assertEqual(summary['macro_missing_dates'],['2026-10-12'])
            self.assertEqual(summary['display_missing_yield'],1)
            run2,_=execute(ROOT/'data'/'raw',Path(d))
            for name in ['curated_sessions.csv','dashboard_90d.csv','quality_events.csv']:
                self.assertEqual((run/name).read_bytes(),(run2/name).read_bytes())

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    report=stream.getvalue()
    (ROOT/'docs'/'test_results.txt').write_text(report,encoding='utf-8')
    print(report)
    sys.exit(not result.wasSuccessful())
