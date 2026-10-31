"""Offline dashboard generation and a pre-display volatility calibration."""
import csv
import json
import math
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent

def signal_message(row, signal):
    if signal == 'UNAVAILABLE':
        return dict(title='Signal unavailable — Check missing data', detail='Both conditions need valid observations before a market signal can be shown.')
    if signal == 'RED':
        return dict(title='RED — Nasdaq below trend and yields rising', detail='Both pressure conditions are triggered. Escalate for analyst review.')
    if signal == 'GREEN':
        return dict(title='GREEN — Neither condition triggered', detail='No flag from equity trend or Treasury yield rise. Continue routine monitoring.')
    if row['price_below_ma20']:
        return dict(title='AMBER — Nasdaq below its 20-session average', detail='Equity trend triggered the alert. The Treasury yield-rise condition is not triggered.')
    return dict(title='AMBER — Treasury yield rise exceeds threshold', detail='Rising yields triggered the alert. Nasdaq remains at or above its 20-session average.')

def daily_changes(rows):
    latest, previous = rows[-1], rows[-2]
    def difference(key, scale):
        a,b=latest[key],previous[key]
        return round((a-b)*scale,10) if a is not None and b is not None else None
    return dict(previous_date=previous['date'],nasdaq_points=difference('nasdaq_close',1),
                treasury_bps=difference('treasury_yield_pct',100))

def percentile(values, fraction):
    values=sorted(values)
    if not values: raise ValueError('No calibration observations')
    position=(len(values)-1)*fraction
    lower=math.floor(position);upper=math.ceil(position)
    return values[lower]+(values[upper]-values[lower])*(position-lower)

def classify(price_flag, yield_flag):
    if price_flag is None or yield_flag is None: return 'UNAVAILABLE'
    return ['GREEN', 'AMBER', 'RED'][int(price_flag) + int(yield_flag)]

def yield_rise(change, threshold):
    if change is None or not math.isfinite(change): return None
    return change > 0 and change >= threshold

def add_signal_inputs(rows):
    """20 scheduled-session endpoint change; no filling of either endpoint."""
    for i, row in enumerate(rows):
        previous = rows[i-20] if i >= 20 else None
        current_yield = row['treasury_yield_pct']
        old_yield = previous['treasury_yield_pct'] if previous else None
        row['yield_change_20_bps'] = (round((current_yield-old_yield)*100, 10)
            if current_yield is not None and old_yield is not None else None)
        row['yield_comparison_date'] = previous['date'] if previous else None
        row['yield_comparison_pct'] = old_yield
        row['price_below_ma20'] = (row['nasdaq_close'] < row['nasdaq_ma20']
            if row['nasdaq_close'] is not None and row['nasdaq_ma20'] is not None else None)
    return rows

def read_rows(path):
    with Path(path).open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    for row in rows:
        for key in ['nasdaq_close','treasury_yield_pct','nasdaq_ma20','nasdaq_return_1d','nasdaq_volatility_14d']:
            row[key]=float(row[key]) if row[key] else None
        row['yield_missing']=row['yield_missing']=='True'
    return rows

def build_payload(run_dir):
    run_dir=Path(run_dir)
    summary=json.loads((run_dir/'summary.json').read_text(encoding='utf-8'))
    manifest=json.loads((run_dir/'manifest.json').read_text(encoding='utf-8'))
    all_rows=add_signal_inputs(read_rows(run_dir/'curated_sessions.csv'))
    rows=[r for r in all_rows if r['date']>=summary['display_start']]
    calibration=[r for r in all_rows if r['date']<summary['display_start'] and r['yield_change_20_bps'] is not None]
    if len(calibration)<40:raise ValueError('At least 40 prior yield-change observations required for calibration')
    raw_threshold=percentile([r['yield_change_20_bps'] for r in calibration],.8)
    # A positive rise is required even when the reference percentile is nonpositive.
    threshold=max(0,raw_threshold)
    for row in rows:
        change=row['yield_change_20_bps']
        row['yield_rise_triggered'] = yield_rise(change, threshold)
        row['rag']=classify(row['price_below_ma20'],row['yield_rise_triggered'])
    signal=dict(metric='Equity trend and 20-session Treasury yield rise',yield_threshold_bps=threshold,
                raw_p80_bps=raw_threshold,
                calibration_start=calibration[0]['date'],calibration_end=calibration[-1]['date'],
                calibration_observations=len(calibration),percentiles=[80],
                method='Linear interpolation at (n - 1) * percentile',
                rule='A: close < MA20; B: 20-session yield change > 0 and >= max(0, prior P80). Zero flags GREEN; one AMBER; two RED; missing input UNAVAILABLE.',
                counts=dict(Counter(r['rag'] for r in rows)),latest=rows[-1]['rag'])
    return dict(rows=rows,summary=summary,signal=signal,message=signal_message(rows[-1],signal['latest']),daily_changes=daily_changes(all_rows),
                run_id=manifest['run_id'],built_at_utc=manifest['ingested_at_utc'],
                sources=manifest['inputs'],snapshot=True)

def render_html(payload):
    template=(ROOT/'web'/'template.html').read_text(encoding='utf-8')
    styles=(ROOT/'web'/'styles.css').read_text(encoding='utf-8')
    script=(ROOT/'web'/'dashboard.js').read_text(encoding='utf-8')
    data=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    return template.replace('__STYLES__',styles).replace('__DATA__',data).replace('__SCRIPT__',script)

def build(run_dir):
    payload=build_payload(run_dir)
    page=render_html(payload)
    target=Path(run_dir)/'dashboard.html';target.write_text(page,encoding='utf-8')
    (Path(run_dir)/'signal_summary.json').write_text(json.dumps(payload['signal'],indent=2),encoding='utf-8')
    with (Path(run_dir)/'signal_observations.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['date','nasdaq_close','nasdaq_ma20','treasury_yield_pct','yield_comparison_date','yield_comparison_pct','yield_change_20_bps','price_below_ma20','yield_rise_triggered','rag']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(payload['rows'])
    return page,payload
