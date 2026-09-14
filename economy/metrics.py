"""Calendar-aligned transformations; missing periods are never forward-filled."""
import math
from datetime import date


def shift_month(period, months):
    d = date.fromisoformat(period[:10])
    n = d.year * 12 + d.month - 1 + months
    return f"{n // 12:04d}-{n % 12 + 1:02d}-01"


def pct(value, base, power=1):
    if value is None or base is None or base <= 0 or value < 0:
        return None
    return ((value / base) ** power - 1) * 100


def enrich(series):
    rows = series['observations']
    lookup = {r['date']: r['value'] for r in rows}
    quarterly = series['frequency'] == 'quarterly'
    for row in rows:
        d, v = row['date'], row['value']
        row['yoy'] = pct(v, lookup.get(shift_month(d, -12)))
        row['change'] = None
        lag = 3 if quarterly else 1
        old = lookup.get(shift_month(d, -lag))
        row['mom'] = pct(v, old)
        row['qoq_ann'] = pct(v, old, 4) if quarterly else None
        if v is not None and old is not None:
            row['change'] = v - old
        # A six-month contiguous window is required for 3m-on-3m growth.
        six = [lookup.get(shift_month(d, -i)) for i in range(6)]
        row['three_month_growth'] = (pct(sum(six[:3]), sum(six[3:]))
            if not quarterly and all(x is not None for x in six) else None)
        if series.get('unit') == '%' or series.get('id') == 'gscpi':
            # Relative percent changes of rates or a zero-centered index are
            # not used. Their absolute period change remains available.
            for field in ['yoy', 'mom', 'qoq_ann', 'three_month_growth']:
                row[field] = None
    return series


def latest(series, end=None):
    rows = [r for r in series['observations'] if r['value'] is not None and (not end or r['date'] <= end)]
    return rows[-1] if rows else None


def scenario(budget=10_000_000, material_share=40, labour_share=35,
             import_share=40, material_inflation=5, wage_inflation=4,
             fx_change=5, tariff_before=0, tariff_after=10,
             debt=6_000_000, rate_bps=100, months=12):
    """Incremental project cost. Budget already includes the baseline tariff.

    Imported materials are denominated in USD, fully exposed and unhedged.
    Financing assumes constant drawn principal; all other shares are unchanged.
    """
    args = locals().copy()
    if any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in args.values()):
        raise ValueError('Every assumption must be a finite number.')
    if budget <= 0 or debt < 0 or months < 0:
        raise ValueError('Budget must be positive; debt and duration cannot be negative.')
    if not (0 <= material_share <= 100 and 0 <= labour_share <= 100 and material_share + labour_share <= 100):
        raise ValueError('Material and labour shares must sum to 100% or less.')
    if not 0 <= import_share <= 100 or min(tariff_before, tariff_after) < 0:
        raise ValueError('Invalid import share or tariff.')
    if min(material_inflation, wage_inflation, fx_change) <= -100:
        raise ValueError('Price changes must exceed -100%.')
    materials = budget * material_share / 100
    imported = materials * import_share / 100
    inflation = materials * material_inflation / 100
    fx = imported * (1 + material_inflation / 100) * fx_change / 100
    tariff = imported * (1 + material_inflation / 100) * (1 + fx_change / 100) * ((1 + tariff_after / 100) / (1 + tariff_before / 100) - 1)
    labour = budget * labour_share / 100 * wage_inflation / 100
    financing = debt * rate_bps / 10000 * months / 12
    components = dict(material_prices=inflation, foreign_exchange=fx, tariffs=tariff, labour=labour, financing=financing)
    extra = sum(components.values())
    return dict(components=components, incremental_cost=extra, revised_budget=budget + extra, budget_change_pct=extra / budget * 100)
