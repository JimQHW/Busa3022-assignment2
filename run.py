"""Build the complete offline portfolio from the two supplied CSV files."""
import argparse
import json
import os
from pathlib import Path
import webbrowser
from pipeline import ROOT, execute
from dashboard import build

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,default=ROOT/'data'/'raw')
    parser.add_argument('--start',default='2026-04-01')
    parser.add_argument('--end',default=None)
    parser.add_argument('--open',action='store_true',help='Open the completed dashboard in your browser')
    args=parser.parse_args()
    lock=ROOT/'.run.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:parser.exit(1,'A run is active, or .run.lock remains after interruption. Check before removing the lock.\n')
    os.close(fd)
    try:
        run_dir,summary=execute(args.input_dir,ROOT/'outputs',args.start,args.end)
        page,payload=build(run_dir)
        temp=ROOT/'dashboard.tmp.html';temp.write_text(page,encoding='utf-8')
        os.replace(temp,ROOT/'dashboard.html')
        published=dict(run_path=str(run_dir.relative_to(ROOT)).replace('\\','/'),
                       snapshot_end=summary['snapshot_end'],signal=payload['signal'],
                       acquisition='offline supplied snapshot; manually triggered repeatable run')
        temp=ROOT/'outputs'/'dashboard_latest.tmp.json';temp.write_text(json.dumps(published,indent=2),encoding='utf-8')
        os.replace(temp,ROOT/'outputs'/'dashboard_latest.json')
        print('Complete: dashboard.html')
        print(f"Snapshot: {summary['snapshot_end']} | Sessions: {summary['display_sessions']} | Signal: {payload['signal']['latest']}")
        print('Evidence:',run_dir)
        if args.open:webbrowser.open((ROOT/'dashboard.html').as_uri())
    except Exception as exc:
        parser.exit(1,f'Build failed: {exc}. Previous dashboard.html retained unless HTML publication already completed. Inspect outputs/runs.\n')
    finally:lock.unlink(missing_ok=True)

if __name__=='__main__':main()
