"""Quarterly evidence summaries and explicitly illustrative forward scenarios."""
from statistics import mean, median
from .metrics import shift_month, latest, pct


def quarter_id(d):
    return f"{d[:4]} Q{(int(d[5:7]) - 1) // 3 + 1}"


def quarter_start(y, q):
    return f'{y:04d}-{3*q-2:02d}-01'


def summarize(series, start, field='value', aggregation='mean'):
    if not series:
        return {'value': None, 'months': 0, 'expected': 3}
    period = 3 if series['frequency'] == 'quarterly' else 1
    expected = 1 if period == 3 else 3
    wanted = {shift_month(start, n) for n in range(0,3,period)}
    rows = [r for r in series['observations'] if r['date'] in wanted and r.get(field) is not None and not r.get('partial_month')]
    values = [r[field] for r in rows]
    value = ((sum(values) if aggregation == 'sum' else mean(values)) if values else None)
    return {'value': value, 'months': len(values), 'expected': expected, 'complete': len(values) == expected}


def fmt(v, suffix='%'):
    return 'unavailable' if v is None else f'{v:.1f}{suffix}'


def generate_quarters(series, today):
    y, q = int(today[:4]), (int(today[5:7])-1)//3+1
    last = quarter_start(y,q)
    quarters = []
    for i in range(12):
        start = shift_month(last,-3*i)
        end = shift_month(start,3)
        fields = {
            'gdp': ('ca_gdp','qoq_ann','mean'),
            'us_gdp': ('us_gdp','qoq_ann','mean'),
            'inflation': ('cpi_CA','yoy','mean'),
            'unemployment': ('unemployment_CA','value','mean'),
            'capex': ('ca_business_capex','qoq_ann','mean'),
            'materials': ('ippi','yoy','mean'),
            'supply': ('gscpi','value','mean'),
            'permits': ('permits_CA','value','sum'),
            'exports': ('exports_US','value','sum'),
            'rate': ('ca_rate','value','mean')}
        values = {k:summarize(series.get(sid),start,field,agg) for k,(sid,field,agg) in fields.items()}
        prev_un = summarize(series.get('unemployment_CA'),shift_month(start,-3))
        gdp = values['gdp']['value']; inf = values['inflation']['value']; un = values['unemployment']['value']; mat = values['materials']['value']; sup=values['supply']['value']
        facts = []
        if gdp is not None:
            facts.append({'title':'Demand and capital investment','finding':f"Canada’s real GDP grew at an annualized {gdp:.1f}% in {quarter_id(start)}. Business investment growth was {fmt(values['capex']['value'])} annualized.",
                          'implication':'Use staged capital approvals and test customer demand before committing to a large expansion.' if gdp < 1 else 'Prioritize expansion where orders and sector activity confirm the broader growth signal; keep a downside case in the investment model.',
                          'sources':['ca_gdp','ca_business_capex']})
        else:
            facts.append({'title':'Demand and capital investment','finding':f"GDP for {quarter_id(start)} is not yet available in this snapshot.",'implication':'Treat this quarter as an interim outlook; avoid presenting incomplete monthly signals as a reported quarterly growth rate.','sources':['ca_gdp']})
        facts.append({'title':'Pricing and procurement','finding':f"Average CPI inflation was {fmt(inf)}; industrial producer-price inflation averaged {fmt(mat)}. Coverage is shown below.",
                      'implication':'Shorten quote-validity periods, check supplier escalation clauses and test higher input costs against project margins.' if mat is not None and mat>3 else 'Refresh supplier bids and seek selective fixed-price commitments; lower inflation does not mean lower price levels.',
                      'sources':['cpi_CA','ippi']})
        change = un-prev_un['value'] if un is not None and prev_un['value'] is not None and values['unemployment']['complete'] and prev_un['complete'] else None
        facts.append({'title':'People and delivery','finding':f"The unemployment rate averaged {fmt(un)}" + (f", a {change:+.1f} percentage-point change from the preceding quarter." if change is not None else '. The preceding-quarter comparison is incomplete.') + f" Global supply pressure averaged {fmt(sup,' standard deviations')}.",
                      'implication':('Review long-lead orders and supplier alternatives before finalizing delivery dates.' if sup is not None and sup>1 else 'Use normal inventory planning while tracking long-lead items separately.') + ' Check occupation-level wages and local availability before changing staffing plans.',
                      'sources':['unemployment_CA','gscpi']})
        paths = []
        growth = [r['qoq_ann'] for r in series.get('ca_gdp',{}).get('observations',[]) if r['date'] < end and r.get('qoq_ann') is not None]
        base = median(growth[-4:]) if len(growth)>=4 else None
        anchor = latest(series.get('ca_gdp',{'observations':[]}),shift_month(start,0))
        if base is not None and anchor:
            for name, rate in [('Slower growth',base-2),('Recent pace',base),('Faster growth',base+2)]:
                points=[{'date':anchor['date'],'value':100}]
                for step in range(1,5):
                    points.append({'date':shift_month(anchor['date'],step*3),'value':100*(1+rate/100)**(step/4)})
                paths.append({'name':name,'annual_rate':rate,'points':points})
        quarters.append(dict(id=quarter_id(start),start=start,end=end,values=values,facts=facts,paths=paths,
            interim=not values['gdp']['complete'] or not values['inflation']['complete'],
            scenario_anchor=anchor['date'] if anchor else None,
            triggers=[
                {'risk':'Demand weakens','watch':'A second consecutive negative quarterly GDP reading, supported by weaker orders.','action':'Stage discretionary investment and protect working capital.'},
                {'risk':'Input or logistics pressure rises','watch':'Producer-price inflation above 3% or global supply pressure above +1 standard deviation. These are dashboard screening thresholds.','action':'Reprice procurement packages and validate delivery buffers.'},
                {'risk':'Trade rules change','watch':'A new official notice affecting your product classification, origin or shipment date.','action':'Confirm landed costs and customer exposure before signing or shipping.'},
                {'risk':'Demand and financing improve','watch':'Positive sector growth plus confirmed customer orders and an affordable borrowing quote.','action':'Advance the strongest projects while retaining scenario contingencies.'}]))
    return quarters


def markdown(quarter, generated_at, series, policies):
    parts=[f"# Economic outlook — {quarter['id']}",f"Prepared {generated_at[:10]}. {'Interim: incomplete quarter coverage.' if quarter['interim'] else 'Quarterly data summary.'} Current data vintage; not a reconstruction of information available at the historical date.",
           '\n## Current conditions and business implications']
    for item in quarter['facts']:
        parts += [f"\n### {item['title']}",item['finding'],item['implication']]
        parts += ['Sources: '+', '.join(f"[{series[s]['source_title']}]({series[s]['source_url']})" for s in item['sources'] if s in series)]
    parts+=['\n## Evidence coverage','Metric | Value | Observations / expected','--- | ---: | ---:']
    for k,v in quarter['values'].items():
        parts.append(f"{k} | {fmt(v['value'],'')} | {v['months']} / {v['expected']}")
    parts+=['\n## Forward-looking scenarios','Illustrations, not economic forecasts or confidence intervals. Recent pace is the median annualized GDP growth of the latest four available quarters; slower/faster paths subtract/add 2 percentage points. Values are indexed to 100 at the most recent observed GDP quarter. No probabilities or causal impact estimates are assigned.']
    for p in quarter['paths']:
        parts.append(f"- {p['name']}: {p['annual_rate']:.2f}% annual growth assumption; index {p['points'][-1]['value']:.2f} after four quarters.")
    parts+=['\n## Risks and decision triggers']
    for t in quarter['triggers']:
        parts.append(f"- {t['risk']}: {t['watch']} {t['action']}")
    parts+=['\n## Trade policy watch',f"Selected notices last substantively reviewed {policies['last_reviewed']}; this section is a current policy addendum, not historical policy reconstruction. A successful data refresh does not revalidate tariff rules."]
    for p in policies['notices']:
        parts.append(f"- [{p['title']}]({p['url']}) — effective {p['effective']}. {p['summary']}")
    return '\n\n'.join(parts)+'\n'
