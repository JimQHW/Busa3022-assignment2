"""Repeatable local CSV proof of concept. Python 3.10+, standard library only."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
SERIES = ('DGS10', 'NASDAQCOM')
# Reviewed 28 October 2026 against Nasdaq Trader's official 2026 schedule.
# Calendar is explicitly bounded: do not extrapolate into another year.
CLOSED_2026 = set('2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03 2026-09-07 2026-11-26 2026-12-25'.split())
EVENT_FIELDS = ['source', 'row_number', 'date', 'raw_value', 'issue', 'action', 'detail']

class DataQualityError(ValueError):
    pass

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')

def write_csv(path, rows, fields):
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def event(events, source, row, day, raw, issue, action, detail=''):
    events.append(dict(zip(EVENT_FIELDS, [source, row, day, raw, issue, action, detail])))

def parse_source(path, series, events):
    """Keep missing observations; log every rejected row and every missing value."""
    table = {}
    stats = dict(input_rows=0, valid_rows=0, missing_rows=0, rejected_rows=0)
    conflicts = False
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        expected = ['observation_date', series]
        if reader.fieldnames != expected:
            event(events, series, 1, '', '', 'SCHEMA_MISMATCH', 'stop_run',
                  f'Expected {expected}; received {reader.fieldnames}')
            raise DataQualityError(f'{series}: unexpected CSV header')
        for rownum, row in enumerate(reader, 2):
            stats['input_rows'] += 1
            day = row.get('observation_date', '') or ''
            raw = row.get(series, '') or ''
            reason = None
            try:
                if None in row or row.get(series) is None:
                    raise ValueError('Malformed CSV row')
                parsed_day = date.fromisoformat(day)
                if parsed_day.isoformat() != day:
                    raise ValueError('Date must use YYYY-MM-DD')
                if parsed_day > datetime.now(timezone.utc).date():
                    raise ValueError('Future observation date')
                value = None if raw.strip() in ('', '.', 'NA', 'N/A') else float(raw)
                if value is not None and not math.isfinite(value):
                    raise ValueError('Non-finite value')
                if series == 'NASDAQCOM' and value is not None and value <= 0:
                    raise ValueError('Index close must be positive')
            except (ValueError, TypeError) as exc:
                reason = str(exc)
            if reason:
                stats['rejected_rows'] += 1
                event(events, series, rownum, day, raw, 'INVALID_RECORD', 'quarantine', reason)
                continue
            if day in table:
                stats['rejected_rows'] += 1
                conflict = table[day] != value
                conflicts |= conflict
                event(events, series, rownum, day, raw,
                      'CONFLICTING_DUPLICATE' if conflict else 'EXACT_DUPLICATE',
                      'stop_run' if conflict else 'exclude_duplicate', 'Original row retained in raw snapshot')
                continue
            table[day] = value
            if value is None:
                stats['missing_rows'] += 1
                event(events, series, rownum, day, raw, 'MISSING_VALUE', 'preserve_null',
                      'No zero substitution or imputation; calendar classification is separate')
            else:
                stats['valid_rows'] += 1
    if conflicts:
        raise DataQualityError(f'{series}: conflicting duplicate dates')
    if not table:
        raise DataQualityError(f'{series}: no usable dates')
    assert stats['input_rows'] == stats['valid_rows'] + stats['missing_rows'] + stats['rejected_rows']
    dates = sorted(table)
    stats.update(date_min=dates[0], date_max=dates[-1])
    return dict(sorted(table.items())), stats

def expected_sessions(start, end):
    if start.year != 2026 or end.year != 2026 or end < start:
        raise DataQualityError('Reviewed calendar supports 2026 only; check analysis interval')
    return [(start + timedelta(days=i)).isoformat() for i in range((end-start).days+1)
            if (start + timedelta(days=i)).weekday() < 5
            and (start + timedelta(days=i)).isoformat() not in CLOSED_2026]

def metric_rows(prices):
    """Rows must represent consecutive scheduled sessions, including missing ones."""
    returns = []
    result = []
    for i, close in enumerate(prices):
        previous = prices[i-1] if i else None
        ret = close / previous - 1 if close is not None and previous is not None and previous > 0 else None
        returns.append(ret)
        window = prices[max(0, i-19):i+1]
        ma = statistics.mean(window) if len(window) == 20 and all(v is not None for v in window) else None
        rw = returns[max(0, i-13):i+1]
        vol = statistics.stdev(rw) if len(rw) == 14 and all(v is not None for v in rw) else None
        result.append(dict(nasdaq_ma20=ma, nasdaq_return_1d=ret, nasdaq_volatility_14d=vol))
    return result

def transform(market, macro, start, end, events):
    sessions = expected_sessions(start, end)
    rows = []
    metrics = metric_rows([market.get(d) for d in sessions])
    missing_market = []
    for d, values in zip(sessions, metrics):
        close, yield_value = market.get(d), macro.get(d)
        if close is None:
            missing_market.append(d)
            event(events, 'NASDAQCOM', '', d, '', 'MISSING_EXPECTED_SESSION', 'block_publication',
                  'No valid close on a scheduled session; never bridge this gap')
        if yield_value is None:
            event(events, 'DGS10', '', d, '', 'YIELD_MISSING_ON_MARKET_SESSION', 'retain_market_row',
                  'Preserve null macro value and explicit flag')
        rows.append(dict(date=d, nasdaq_close=close, treasury_yield_pct=yield_value,
                         yield_missing=yield_value is None, **values))
    for d, value in market.items():
        if start.isoformat() <= d <= end.isoformat() and d not in sessions:
            event(events, 'NASDAQCOM', '', d, value, 'NON_SESSION_RECORD',
                  'exclude_from_session_table' if value is None else 'block_publication',
                  'Reviewed Nasdaq 2026 calendar')
            if value is not None:
                raise DataQualityError(f'Unexpected valid index value on closed day: {d}')
    if missing_market:
        raise DataQualityError(f'Missing expected market sessions: {missing_market}')
    return rows

def execute(input_dir, output_root=ROOT/'outputs', start='2026-04-01', end=None):
    output_root = Path(output_root)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid4().hex[:8]
    run_dir = output_root/'runs'/run_id
    run_dir.mkdir(parents=True)
    (run_dir/'raw').mkdir()
    events, profiles, provenance = [], {}, {}
    manifest = dict(run_id=run_id, ingested_at_utc=datetime.now(timezone.utc).isoformat(),
                    status='RUNNING', acquisition='supplied_local_csv_snapshot',
                    calendar='Nasdaq 2026 official full-day closures',
                    calendar_url='https://www.nasdaqtrader.com/trader.aspx?id=calendar',
                    observation_date_basis='US date labels; America/New_York session calendar',
                    publication_time_available=False, profiles=profiles, inputs=provenance)
    try:
        tables = {}
        for series in SERIES:
            source = Path(input_dir)/(series+'.csv')
            data = source.read_bytes()
            snapshot = run_dir/'raw'/source.name
            snapshot.write_bytes(data)
            provenance[series] = dict(file='raw/'+source.name, sha256=hashlib.sha256(data).hexdigest(),
                                      bytes=len(data), metadata_url='https://fred.stlouisfed.org/series/'+series)
            tables[series], profiles[series] = parse_source(snapshot, series, events)
            write_csv(run_dir/(series+'_clean.csv'),
                      [dict(date=d, value=v, is_missing=v is None) for d,v in tables[series].items()],
                      ['date','value','is_missing'])
        latest_market = max(d for d,v in tables['NASDAQCOM'].items() if v is not None)
        end = end or latest_market
        if end > latest_market:
            raise DataQualityError('Requested end exceeds latest valid market observation')
        rows = transform(tables['NASDAQCOM'], tables['DGS10'], date.fromisoformat(start), date.fromisoformat(end), events)
        window_start = (date.fromisoformat(end)-timedelta(days=89)).isoformat()
        serving = [r for r in rows if r['date'] >= window_start]
        if not serving or serving[0]['nasdaq_ma20'] is None or serving[0]['nasdaq_volatility_14d'] is None:
            raise DataQualityError('Insufficient warm-up data for the display interval')
        fields = ['date','nasdaq_close','treasury_yield_pct','yield_missing',
                  'nasdaq_ma20','nasdaq_return_1d','nasdaq_volatility_14d']
        write_csv(run_dir/'curated_sessions.csv', rows, fields)
        write_csv(run_dir/'dashboard_90d.csv', serving, fields)
        write_csv(run_dir/'quality_events.csv', events, EVENT_FIELDS)
        macro_only = [d for d,v in tables['DGS10'].items()
                      if start <= d <= end and v is not None and d not in {r['date'] for r in rows}]
        summary = dict(analysis_start=start, snapshot_end=end, display_start=window_start,
                       display_calendar_days=90, scheduled_sessions=len(rows), display_sessions=len(serving),
                       display_missing_yield=sum(r['yield_missing'] for r in serving),
                       macro_missing_dates=[r['date'] for r in rows if r['yield_missing']],
                       valid_macro_non_market_dates=macro_only,
                       events_by_type=dict(__import__('collections').Counter(e['issue'] for e in events)),
                       latest_metrics=rows[-1], source_profiles=profiles,
                       limitations=['Local historical snapshot; no network acquisition or scheduler implemented',
                                    'Two upstream series share the FRED distribution platform',
                                    'Same-date retrospective alignment is not a point-in-time backtest',
                                    'Calendar checked only for the 2026 calculation interval'])
        write_json(run_dir/'summary.json', summary)
        manifest.update(status='SUCCESS', analysis_start=start, snapshot_end=end,
                        output_rows=len(rows), serving_rows=len(serving), event_count=len(events))
        write_json(run_dir/'manifest.json', manifest)
        pointer_tmp=output_root/('latest_'+run_id+'.tmp')
        write_json(pointer_tmp, dict(run_id=run_id, run_path='runs/'+run_id, snapshot_end=end))
        os.replace(pointer_tmp, output_root/'latest.json')
        return run_dir, summary
    except Exception as exc:
        event(events, 'RUN', '', '', '', 'RUN_FAILED', 'retain_previous_publication', str(exc))
        write_csv(run_dir/'quality_events.csv', events, EVENT_FIELDS)
        manifest.update(status='FAILED', error=str(exc), event_count=len(events))
        write_json(run_dir/'manifest.json', manifest)
        raise

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=ROOT/'data'/'raw')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'outputs')
    parser.add_argument('--start', default='2026-04-01')
    parser.add_argument('--end', default=None)
    args=parser.parse_args()
    try:
        folder, summary=execute(args.input_dir, args.output_dir, args.start, args.end)
        print(json.dumps(dict(run_folder=str(folder), **summary), indent=2))
    except Exception as exc:
        parser.exit(1, f'Run failed; inspect the latest failed run manifest: {exc}\n')
