import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from economy.metrics import enrich, scenario, shift_month
from economy.outlook import summarize, generate_quarters
from economy.sources import supply_chain, fred, request, fetch_all

ROOT=Path(__file__).resolve().parents[1]


class CalculationTests(unittest.TestCase):
    def test_calendar_lags_do_not_bridge_missing_months(self):
        s={'frequency':'monthly','observations':[{'date':'2025-01-01','value':100},{'date':'2025-03-01','value':110},{'date':'2026-01-01','value':120}]}
        enrich(s)
        self.assertIsNone(s['observations'][1]['mom'])
        self.assertAlmostEqual(s['observations'][-1]['yoy'],20)
        self.assertIsNone(s['observations'][-1]['three_month_growth'])
        self.assertEqual(shift_month('2026-01-01',-1),'2025-12-01')

    def test_annualized_gdp_is_compounded(self):
        s={'frequency':'quarterly','observations':[{'date':'2026-01-01','value':100},{'date':'2026-04-01','value':101}]}
        enrich(s)
        self.assertAlmostEqual(s['observations'][1]['qoq_ann'],4.060401)

    def test_rates_use_percentage_point_changes(self):
        s={'unit':'%','frequency':'monthly','observations':[{'date':'2026-01-01','value':6},{'date':'2026-02-01','value':6.5}]}
        enrich(s)
        self.assertEqual(s['observations'][-1]['change'],.5)
        self.assertIsNone(s['observations'][-1]['mom'])

    def test_full_six_month_window(self):
        s={'frequency':'monthly','observations':[{'date':f'2026-{i:02d}-01','value':100 if i<=3 else 110} for i in range(1,7)]}
        enrich(s)
        self.assertAlmostEqual(s['observations'][-1]['three_month_growth'],10)

    def test_incomplete_quarter_is_not_extrapolated(self):
        s={'frequency':'monthly','observations':[{'date':'2026-01-01','value':10},{'date':'2026-02-01','value':20}]}
        r=summarize(s,'2026-01-01',aggregation='sum')
        self.assertEqual(r['value'],30)
        self.assertEqual(r['months'],2)
        self.assertFalse(r['complete'])

    def test_partial_daily_month_is_excluded_from_quarter(self):
        s={'frequency':'monthly','observations':[{'date':'2026-07-01','value':2.25},{'date':'2026-08-01','value':2.25},{'date':'2026-09-01','value':2.25,'partial_month':True}]}
        r=summarize(s,'2026-07-01')
        self.assertFalse(r['complete'])
        self.assertEqual(r['months'],2)

    def test_scenario_interactions_reconcile(self):
        r=scenario()
        self.assertAlmostEqual(r['components']['material_prices'],200000)
        self.assertAlmostEqual(r['components']['foreign_exchange'],84000)
        self.assertAlmostEqual(r['components']['tariffs'],176400)
        self.assertAlmostEqual(r['incremental_cost'],660400)
        self.assertAlmostEqual(r['revised_budget'],10660400)
        self.assertAlmostEqual(r['budget_change_pct'],6.604)

    def test_unchanged_tariff_does_not_double_count(self):
        r=scenario(material_inflation=0,wage_inflation=0,fx_change=0,tariff_before=25,tariff_after=25,rate_bps=0)
        self.assertEqual(r['incremental_cost'],0)
        with self.assertRaises(ValueError):scenario(material_share=75,labour_share=50)
        with self.assertRaises(ValueError):scenario(fx_change=-100)
        with self.assertRaises(ValueError):scenario(budget=float('nan'))

    @patch('economy.sources.request')
    def test_supply_chain_uses_latest_vintage_not_first_column(self, req):
        req.return_value=b'Date,Jan-22,Sep-26\r\n31-Jan-2019,9.99,-0.44\r\n31-Aug-2026,,0.65\r\n,,\r\n'
        s=supply_chain()['gscpi']
        self.assertEqual(s['observations'][0]['value'],-.44)
        self.assertEqual(s['observations'][1]['value'],.65)
        self.assertIn('Sep-26',s['note'])

    @patch('economy.sources.request')
    def test_fred_falls_back_to_per_series_when_bulk_is_empty(self, req):
        def fake(url, payload=None, timeout=45, attempts=5):
            if 'id=CPIAUCNS,UNRATE' in url or url.count(',') >= 2:
                return b'<html>rate limited</html>'
            key=url.split('id=')[1].split('&')[0]
            return f'observation_date,{key}\n2019-01-01,1.5\n2020-01-01,2.5\n'.encode()
        req.side_effect=fake
        series=fred()
        self.assertEqual(sorted(series),['us_cpi','us_gdp','us_housing','us_industrial','us_rate','us_unemployment'])
        self.assertEqual(series['us_cpi']['observations'][-1]['value'],2.5)

    @patch('economy.sources.time.sleep', return_value=None)
    @patch('urllib.request.urlopen')
    def test_request_retries_empty_bodies(self, urlopen, _sleep):
        class Resp:
            def __init__(self, data): self._data=data
            def read(self): return self._data
            def __enter__(self): return self
            def __exit__(self, *args): return False
        urlopen.side_effect=[Resp(b''), Resp(b'{"ok":true}')]
        self.assertEqual(request('https://example.test/data'), b'{"ok":true}')
        self.assertEqual(urlopen.call_count, 2)

    @patch('economy.sources.supply_chain', side_effect=RuntimeError('gscpi down'))
    @patch('economy.sources.fred', return_value={'us_cpi':{'id':'us_cpi','observations':[{'date':'2019-01-01','value':1}]}})
    @patch('economy.sources.bank_of_canada', return_value={'fx':{'id':'fx','observations':[{'date':'2019-01-01','value':1}]}})
    @patch('economy.sources.statcan', return_value={'cpi_CA':{'id':'cpi_CA','pid':1,'observations':[{'date':'2019-01-01','value':1}]}})
    def test_fetch_all_keeps_cached_provider_on_partial_failure(self, *_mocks):
        previous={'series':{'gscpi':{'id':'gscpi','observations':[{'date':'2019-01-01','value':0.1}],'fetched_at':'old'}}}
        series,errors=fetch_all([], previous)
        self.assertEqual([e['provider'] for e in errors],['supply_chain'])
        self.assertEqual(series['gscpi']['fetch_status'],'cached_after_error')
        self.assertIn('us_cpi',series)
        self.assertIn('cpi_CA',series)


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=json.loads((ROOT/'data/snapshot.json').read_text())

    def test_unique_dates_and_scalar_conversion(self):
        for sid,s in self.d['series'].items():
            dates=[r['date'] for r in s['observations']]
            self.assertEqual(len(dates),len(set(dates)),sid)
            self.assertEqual(dates,sorted(dates),sid)
            self.assertTrue(s['source_url'].startswith('https://'))
            for r in s['observations']:
                if r['value'] is not None:
                    self.assertTrue(math.isfinite(r['value']),sid)
                    if s.get('pid'):
                        self.assertAlmostEqual(r['value'],r['raw_value']*10**r['scalar_factor']/s['divisor'],places=7,msg=sid)

    def test_trade_denominators_and_industry_components(self):
        s=self.d['series']
        us={r['date']:r['value'] for r in s['exports_US']['observations']}
        for r in s['exports_World']['observations']:
            if r['value'] and us.get(r['date']) is not None:
                self.assertTrue(0<=us[r['date']]/r['value']<=1)
        # Current-dollar building investment is additive, unlike chained GDP.
        ids=['building_residential','building_industrial','building_commercial','building_institutional']
        maps={sid:{r['date']:r['value'] for r in s[sid]['observations']} for sid in ids}
        for r in s['investment_CA']['observations'][-12:]:
            vals=[maps[sid].get(r['date']) for sid in ids]
            if r['value'] is not None and all(v is not None for v in vals):
                self.assertAlmostEqual(sum(vals),r['value'],delta=.0001)

    def test_quarterly_outlook_paths_are_indexed_and_labeled(self):
        quarters=generate_quarters(self.d['series'],self.d['generated_at'][:10])
        self.assertEqual(len(quarters),12)
        q=next(q for q in quarters if q['paths'])
        for p in q['paths']:
            self.assertEqual(p['points'][0]['value'],100)
            self.assertAlmostEqual(p['points'][-1]['value'],100+p['annual_rate'])


if __name__=='__main__':unittest.main()
