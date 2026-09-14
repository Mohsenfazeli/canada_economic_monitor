"""Official API clients with bounded retries and exact source lineage."""
import csv
import io
import json
import math
import time
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from .metrics import enrich

WDS = 'https://www150.statcan.gc.ca/t1/wds/rest/'
START = '2019-01-01'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def request(url, payload=None, timeout=45):
    body = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, headers={'User-Agent': 'CanadaEconomicMonitor/1.0 (public statistical research)', 'Accept': '*/*', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise
        time.sleep(1 + attempt)


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def statcan(config):
    pids = sorted({s['pid'] for s in config})
    meta_args = [{'productId': n} for n in pids]
    metadata = json.loads(request(WDS + 'getCubeMetadata', meta_args))
    metas = {int(m['object']['productId']): m['object'] for m in metadata if m.get('status') == 'SUCCESS'}
    if len(metas) != len(pids):
        raise ValueError('Statistics Canada metadata request was incomplete.')
    for s in config:
        meta = metas[s['pid']]
        actual = []
        for dim, member_id in zip(meta['dimension'], s['coordinate'].split('.')):
            matches = [m for m in dim['member'] if m['memberId'] == int(member_id)]
            if len(matches) != 1:
                raise ValueError(f"Unresolved dimension: {s['id']}")
            actual.append(matches[0]['memberNameEn'])
        if actual != s['members']:
            raise ValueError(f"Schema changed for {s['id']}; review its definition before publishing.")
    result = {}
    for offset in range(0, len(config), 25):
        specs = config[offset:offset+25]
        args = [{'productId': s['pid'], 'coordinate': s['coordinate'], 'latestN': 120} for s in specs]
        records = json.loads(request(WDS + 'getDataFromCubePidCoordAndLatestNPeriods', args))
        returned = {(int(r['object']['productId']), r['object']['coordinate']): r['object']
                    for r in records if r.get('status') == 'SUCCESS' and 'object' in r}
        for spec in specs:
            obj = returned.get((spec['pid'], spec['coordinate']))
            if not obj or 'vectorDataPoint' not in obj:
                raise ValueError(f"Missing series response: {spec['id']}")
            series = {**spec, 'provider': 'Statistics Canada', 'fetched_at': now(), 'fetch_status': 'success',
                      'source_title': metas[spec['pid']]['cubeTitleEn'], 'vector': obj['vectorId'],
                      'source_url': f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={spec['pid']}01",
                      'request': {'url': WDS + 'getDataFromCubePidCoordAndLatestNPeriods', 'method': 'POST', 'body': [args[specs.index(spec)]]},
                      'observations': []}
            seen = set()
            for point in sorted(obj['vectorDataPoint'], key=lambda r: r['refPer']):
                period = point['refPer'][:10]
                if period < START or period > datetime.now(timezone.utc).date().isoformat():
                    continue
                if period in seen:
                    raise ValueError(f"Duplicate period in {spec['id']}: {period}")
                seen.add(period)
                raw = number(point.get('value'))
                status = int(point.get('statusCode', 0))
                security = int(point.get('securityLevelCode', 0))
                # Preserve suppressed, unavailable, and unreliable observations as null.
                if status in (1, 8, 9, 10) or security != 0:
                    raw = None
                scalar = int(point.get('scalarFactorCode', 0))
                series['observations'].append({'date': period,
                    'value': raw * 10**scalar / spec.get('divisor', 1) if raw is not None else None,
                    'raw_value': raw, 'scalar_factor': scalar, 'status_code': status,
                    'symbol_code': int(point.get('symbolCode', 0)), 'released_at': point.get('releaseTime')})
            if not any(r['value'] is not None for r in series['observations']):
                raise ValueError(f"No usable observations in {spec['id']}")
            result[spec['id']] = enrich(series)
    return result


def bank_of_canada():
    url = 'https://www.bankofcanada.ca/valet/observations/FXUSDCAD,V39079/json?start_date=' + START
    raw = json.loads(request(url))
    result = {}
    for key, sid, label, unit in [('FXUSDCAD', 'fx', 'Canadian dollars per U.S. dollar', 'CAD / USD'), ('V39079', 'ca_rate', 'Bank of Canada policy rate', '%')]:
        daily = [{'date': p['d'], 'value': number(p[key]['v'])} for p in raw['observations'] if key in p]
        if not daily:
            raise ValueError('No Bank of Canada observations for ' + key)
        # Preserve native business-day observations. Month-end is derived separately.
        monthly = {}
        for point in daily:
            monthly[point['date'][:7] + '-01'] = point
        s = dict(id=sid, label=label, geo='Canada', group='rates', unit=unit, frequency='monthly',
                 provider='Bank of Canada', source_title=raw['seriesDetail'][key]['label'],
                 source_url='https://www.bankofcanada.ca/valet/docs/', fetched_at=now(), fetch_status='success',
                 note='Last available business-day observation in each month. Latest month may be partial.',
                 request={'url': url, 'method': 'GET'}, daily=daily,
                 observations=[{'date': d, 'observed_date': p['date'], 'value': p['value'], 'partial_month': d[:7] == datetime.now(timezone.utc).strftime('%Y-%m')} for d,p in monthly.items()])
        result[sid] = enrich(s)
    return result


def fred():
    specs = [('CPIAUCNS', 'us_cpi', 'U.S. consumer price index', 'Index (1982–84=100)', 'monthly', 'U.S. Bureau of Labor Statistics', 1, 'Not seasonally adjusted. Urban consumers.'),
             ('UNRATE', 'us_unemployment', 'U.S. unemployment rate', '%', 'monthly', 'U.S. Bureau of Labor Statistics', 1, 'Seasonally adjusted; civilian noninstitutional population age 16+.'),
             ('GDPC1', 'us_gdp', 'U.S. real GDP', 'USD bn (2017)', 'quarterly', 'U.S. Bureau of Economic Analysis', 1, 'Chained 2017 USD; seasonally adjusted annual rate.'),
             ('FEDFUNDS', 'us_rate', 'U.S. effective federal funds rate', '%', 'monthly', 'Board of Governors of the Federal Reserve System', 1, 'Monthly average effective rate; not the target range.'),
             ('INDPRO', 'us_industrial', 'U.S. industrial production', 'Index (2017=100)', 'monthly', 'Board of Governors of the Federal Reserve System', 1, 'Seasonally adjusted. Manufacturing, mining and utilities.'),
             ('HOUST', 'us_housing', 'U.S. housing starts', 'Million units SAAR', 'monthly', 'U.S. Census Bureau / HUD', 1000, 'Housing units started; seasonally adjusted annual rate. Not comparable to permit values.')]
    url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=' + ','.join(s[0] for s in specs) + '&cosd=' + START
    raw = request(url)
    if raw.startswith(b'PK'):
        z = zipfile.ZipFile(io.BytesIO(raw))
        tables = [list(csv.DictReader(io.StringIO(z.read(n).decode('utf-8-sig')))) for n in z.namelist() if n.endswith('.csv')]
    else:
        tables = [list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))]
    result = {}
    for key, sid, label, unit, freq, provider, divisor, note in specs:
        rows = []
        for table in tables:
            if table and key in table[0]:
                for point in table:
                    period = point.get('observation_date', point.get('DATE', ''))
                    if START <= period <= datetime.now(timezone.utc).date().isoformat():
                        v = number(point[key])
                        if v is not None:
                            rows.append({'date': period, 'value': v / divisor})
        if not rows:
            raise ValueError('No FRED observations for ' + key)
        s = dict(id=sid, label=label, geo='United States', group='us', unit=unit, frequency=freq,
                 provider=provider + ' via FRED', source_title=label, source_url='https://fred.stlouisfed.org/series/' + key,
                 fetched_at=now(), fetch_status='success', note=note, request={'url': url, 'method': 'GET'},
                 observations=sorted(rows, key=lambda r:r['date']))
        result[sid] = enrich(s)
    return result


def supply_chain():
    url = 'https://www.newyorkfed.org/medialibrary/research/interactives/data/gscpi/gscpi_interactive_data.csv'
    text = request(url).decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    vintage = reader.fieldnames[-1]
    rows = []
    for p in reader:
        vals = list(p.values())
        if not vals or not vals[0] or not vals[0].strip():
            continue
        try:
            d = datetime.strptime(vals[0], '%d-%b-%Y').date().replace(day=1).isoformat()
        except ValueError:
            try:
                d = datetime.strptime(vals[0], '%m/%d/%Y').date().replace(day=1).isoformat()
            except ValueError:
                d = datetime.fromisoformat(vals[0][:10]).date().replace(day=1).isoformat()
        if START <= d <= datetime.now(timezone.utc).date().isoformat():
            rows.append({'date': d, 'value': number(p[vintage])})
    if not rows:
        raise ValueError('No GSCPI observations')
    return {'gscpi': enrich(dict(id='gscpi', label='Global supply chain pressure', geo='Global', group='costs',
        unit='Standard deviations', frequency='monthly', provider='Federal Reserve Bank of New York',
        source_title='Global Supply Chain Pressure Index', source_url='https://www.newyorkfed.org/research/policy/gscpi',
        fetched_at=now(), fetch_status='success', request={'url':url, 'method':'GET'},
        note='Latest published vintage (' + vintage + '). Standard deviations from the historical mean; positive values indicate above-average global pressure. Not a Canada-specific measure or a freight-price index.',
        observations=sorted(rows,key=lambda r:r['date'])))}


def fetch_all(config, previous=None):
    """A failed provider retains its dated snapshot and reports the failure."""
    jobs = {'statcan': lambda: statcan(config), 'bank_of_canada': bank_of_canada, 'fred': fred, 'supply_chain': supply_chain}
    datasets, errors = {}, []
    old = (previous or {}).get('series', {})
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fn): name for name,fn in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                datasets.update(future.result())
            except Exception as exc:
                errors.append({'provider':name, 'message': str(exc), 'attempted_at': now()})
                for sid, series in old.items():
                    category = 'statcan' if series.get('pid') else ('bank_of_canada' if sid in ('fx','ca_rate') else 'supply_chain' if sid=='gscpi' else 'fred')
                    if category == name:
                        datasets[sid] = {**series, 'fetch_status':'cached_after_error'}
    return datasets, errors
