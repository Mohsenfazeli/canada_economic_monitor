#!/usr/bin/env python3
"""Build, refresh and serve Canada Economic Monitor using only Python's stdlib."""
import argparse
import csv
import functools
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from economy.sources import fetch_all, now, request
from economy.outlook import generate_quarters, markdown
from economy.metrics import enrich

ROOT=Path(__file__).resolve().parent


def read_json(p, default=None):
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def atomic_json(path, value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False),encoding='utf-8')
    temp.replace(path)


def check_policies(policy, previous):
    old={c['url']:c for c in previous.get('checks',[])}
    def check(notice):
        url=notice['url']
        try:
            raw=request(url,timeout=25)
            checksum=hashlib.sha256(raw).hexdigest()
            before=old.get(url,{})
            return {'url':url,'checked_at':now(),'sha256':checksum,'status':'retrieved',
                    'changed': bool(before.get('changed') or (before.get('sha256') and before['sha256']!=checksum))}
        except Exception as exc:
            return {**old.get(url,{}),'url':url,'checked_at':now(),'status':'check_failed','error':str(exc)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        policy['checks']=list(pool.map(check,policy['notices']))
    return policy


def export_csv(snapshot):
    buf=io.StringIO(newline='');writer=csv.writer(buf)
    writer.writerow(['series_id','label','geography','date','value','unit','yoy_pct','period_change_pct','period_change_absolute','qoq_annualized_pct','source','source_url','fetched_at','status_code','symbol_code'])
    for sid,s in snapshot['series'].items():
        for r in s['observations']:
            writer.writerow([sid,s['label'],s['geo'],r['date'],r['value'],s['unit'],r.get('yoy'),r.get('mom'),r.get('change'),r.get('qoq_ann'),s['provider'],s['source_url'],s['fetched_at'],r.get('status_code'),r.get('symbol_code')])
    return buf.getvalue()


def source_zip(destination):
    # A portable public source export. Excludes hosting identity, Git, secrets,
    # cached HTTP pages, temporary work and recursive build outputs.
    files=[ROOT/'app.py',ROOT/'README.md',ROOT/'Dockerfile',ROOT/'requirements.txt',ROOT/'render.yaml',ROOT/'.gitignore',ROOT/'LICENSE']
    for folder in ['economy','templates','tests','data','.github/workflows']:
        files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.tmp')]
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(set(files)):
            if p.exists():
                archive.write(p,'canada-economic-monitor/'+str(p.relative_to(ROOT)))


def build(refresh=False, strict=False):
    data=ROOT/'data';config=read_json(data/'series.json');snapshot=read_json(data/'snapshot.json',{})
    policy=read_json(data/'policies.json')
    if refresh or not snapshot:
        series,errors=fetch_all(config,snapshot)
        if strict and errors:
            raise RuntimeError('Refresh incomplete; prior snapshot and published build were preserved: '+json.dumps(errors))
        if not series:
            raise RuntimeError('No source data available. Check network access and retry.')
        snapshot={'generated_at':now(),'series':series,'errors':errors}
        policy=check_policies(policy,read_json(data/'policy_checks.json',{}))
        atomic_json(data/'policy_checks.json',{'checks':policy['checks']})
        atomic_json(data/'snapshot.json',snapshot)
    else:
        policy['checks']=read_json(data/'policy_checks.json',{}).get('checks',[])
    # Older snapshots may not yet have partial-month metadata.
    current_month=snapshot['generated_at'][:7]
    for series in snapshot['series'].values():
        enrich(series)
    for sid in ['ca_rate','fx']:
        for r in snapshot['series'].get(sid,{}).get('observations',[]):
            r['partial_month']=r['date'][:7]==current_month
    payload={**snapshot,'policies':policy,'schema_version':1}
    payload['quarters']=generate_quarters(snapshot['series'],snapshot['generated_at'][:10])
    for q in payload['quarters']:
        q['markdown']=markdown(q,snapshot['generated_at'],snapshot['series'],policy)
    # Build separately before copying the completed payload into dist.
    stage=ROOT/'build-stage';stage.mkdir(exist_ok=True)
    (stage/'downloads').mkdir(exist_ok=True)
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html=(ROOT/'templates/index.html').read_text(encoding='utf-8').replace('__DATA__',encoded)
    (stage/'index.html').write_text(html,encoding='utf-8')
    for name in ['app.js','styles.css']:
        shutil.copy2(ROOT/'templates'/name,stage/name)
    (stage/'downloads/economic-data.csv').write_text(export_csv(snapshot),encoding='utf-8-sig')
    (stage/'downloads/snapshot.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    source_zip(stage/'downloads/canada-economic-monitor-python.zip')
    dist=ROOT/'dist';dist.mkdir(exist_ok=True)
    shutil.copytree(stage,dist,dirs_exist_ok=True);shutil.rmtree(stage)
    print(f"Built {len(snapshot['series'])} series and {len(payload['quarters'])} quarterly briefings. Snapshot: {snapshot['generated_at']}")
    if snapshot['errors']:
        print('WARNING: cached or missing providers:',', '.join(e['provider'] for e in snapshot['errors']))
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    b=commands.add_parser('build',help='Build a portable static dashboard')
    b.add_argument('--refresh',action='store_true',help='Fetch official data and rebuild')
    b.add_argument('--strict',action='store_true',help='Abort if any data provider fails; preserve old output')
    s=commands.add_parser('serve',help='Serve only the public dist directory')
    s.add_argument('--host',default='127.0.0.1')
    s.add_argument('--port',type=int,default=int(os.environ.get('PORT','8080')))
    args=parser.parse_args()
    if args.command=='build':
        build(args.refresh,args.strict)
    else:
        if not (ROOT/'dist/index.html').exists():
            build()
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'dist'))
        server=http.server.ThreadingHTTPServer((args.host,args.port),handler)
        print(f"Serving on http://{args.host}:{args.port}. Data refresh is a separate build operation.")
        try:server.serve_forever()
        except KeyboardInterrupt:server.server_close()


if __name__=='__main__':
    main()
