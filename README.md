# Canada Economic Monitor

A public-facing dashboard for Canadian and U.S. economic conditions, industry
activity, construction, procurement, trade exposure and quarterly planning.
The data pipeline, transformations, outlook generator, build system and local
server are written in Python. A small HTML/CSS/JavaScript interface provides
browser interactions and portable public hosting. Python 3.11+ is the only
runtime dependency; no API keys, database, paid chart service or npm build is
required.

## Run in two commands

From this project folder:

```sh
python app.py build
python app.py serve
```

Open http://localhost:8080. The included, dated official-data snapshot works
without downloading anything. The full project can be downloaded from the
dashboard sidebar on a deployed site.

To fetch current data and rebuild:

```sh
python app.py build --refresh
```

Without `--strict`, a failed provider retains its prior observations, original
retrieval timestamps, and a visible cached-data warning while the rest of the
build continues. Use `--strict` to abort before replacing the snapshot or build
if any provider fails. Either mode still fails when a provider leaves no usable
series at all. New or unresolvable series remain unavailable; no synthetic
values are substituted. Requests have timeouts and bounded retries (including
Statistics Canada HTTP 409 lock windows and empty responses). Network access to
the official source hosts is required for refresh. A browser reload does not
fetch new data.

## Publish publicly

The same `dist` folder can be served by any static web host. Visitors need no
account. The public view contains official public data only; the scenario tool
does not transmit user inputs. Deploy the entire folder, not only index.html.

### Recommended: GitHub Pages with automatic refresh

1. Create a public GitHub repository and upload this project, including the
   `.github/workflows/deploy-pages.yml` file. Use `main` as the default branch.
2. In Settings → Pages → Build and deployment, set Source to GitHub Actions.
3. In Actions, run “Refresh economic data and deploy.” Its deployed URL appears
   in the completed deployment job.

The included workflow fetches data and republishes on weekdays at 14:17 UTC,
on pushes to `main`, and on manual runs. This schedule is part of the supplied
code; it is not active until you install and enable it in your repository.
GitHub may delay scheduled workflows and may disable schedules after prolonged
repository inactivity. A failed refresh leaves the previously deployed site
in place. Check Actions for failures; the dashboard also warns when a published
snapshot is more than seven days old.

The bundled snapshot and source archive provide an offline starting point.
The workflow does not commit refreshed data to Git, so the successful deployment
is the current publication. Download its full snapshot from
`downloads/snapshot.json` if you need an exact historical artifact. For durable
real-time vintages, archive each successful snapshot separately; this app does
not claim to reconstruct past information sets.

Official setup: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

### Render static hosting

Connect the repository as a Static Site. Use `python3 app.py build --refresh
--strict` as the build command and `dist` as the publish directory. A
`render.yaml` blueprint is included. Refresh is build-triggered; set an external
schedule or trigger a deploy to update this host. Do not expose a deploy-hook
secret in browser code.

Official setup: [Render static sites](https://render.com/docs/static-sites).

### Docker / another Python cloud service

```sh
docker build -t economic-monitor .
docker run --rm -p 8080:8080 economic-monitor
```

The container builds from the included snapshot, runs as a non-root user, and
binds to `0.0.0.0:$PORT` (8080 by default). Refresh locally or in CI before
rebuilding the image. `python app.py serve` is a minimal demonstration server;
prefer the static-hosting options for a public production site. Public HTTPS
and a domain are supplied by your host.

If this project is hosted through ChatGPT Sites, it is a static snapshot:
updates require the Python refresh and republishing the same Site. The included
GitHub workflow does not update a ChatGPT Sites URL.

## Dashboard views

| View | What it supports |
| --- | --- |
| Overview | Canadian and U.S. GDP growth, inflation, labour markets and interest rates |
| Industries and construction | Ten selected Canadian industries, all-industry benchmark, regional permits and investment, U.S. industry and housing, provincial labour and price comparisons |
| Costs and supply chains | Producer and raw-material prices, construction material categories, building costs and global supply pressure |
| Trade and tariffs | Canadian exports/imports, same-month U.S. export share, Mexico and other partners, currency exposure and selected official policy notices |
| Business scenarios | Separate project-cost and revenue stress tests, validated assumptions and downloadable results |
| Quarterly outlook | Twelve rolling quarter selections, conditions, business implications, risks, coverage, illustrative four-quarter paths and a downloadable briefing |
| Sources and definitions | Exact source selections, table/vector identifiers, dated observations, query arguments, transformations, source health and CSV downloads |

Canada and the U.S. are the macroeconomic scope. Mexico is included as a trade
partner; this version does not include a standalone Mexican macroeconomic
dataset. No firm-level profitability, occupation-specific wages, real-time
freight quotes or complete HS-level tariff engine is implied.

## Source inventory

Statistics Canada supplies 100 configured series from these current tables:

| Table | Measure |
| --- | --- |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | Monthly CPI, not seasonally adjusted |
| [14-10-0287-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410028701) | Monthly labour-force characteristics |
| [36-10-0434-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610043401) | Real GDP by industry |
| [36-10-0104-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610010401) | Quarterly expenditure-based GDP and capital investment |
| [18-10-0265-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810026501) | Industrial product price indices |
| [18-10-0268-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810026801) | Raw materials price index |
| [34-10-0292-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410029201) | Building permits |
| [34-10-0293-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410029301) | Building construction investment |
| [18-10-0289-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810028901) | Building construction price indices |
| [12-10-0011-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1210001101) | Merchandise trade by partner |

Supplementary series:

- [Bank of Canada Valet](https://www.bankofcanada.ca/valet/docs/): V39079
  overnight target and FXUSDCAD exchange rate. Monthly charts use the last
  observation in each month and identify the exact latest observation date.
- [FRED](https://fred.stlouisfed.org/): CPIAUCNS and UNRATE (BLS); GDPC1 (BEA);
  FEDFUNDS and INDPRO (Federal Reserve); HOUST (Census Bureau/HUD). FRED is the
  distributor and the underlying public agency is retained in attribution.
- [New York Fed GSCPI](https://www.newyorkfed.org/research/policy/gscpi): global
  supply-chain pressure. The download has one column per release vintage;
  the pipeline explicitly uses the latest column, not the first vintage.
- Finance Canada, the White House, CBP and USTR for dated policy notices and
  official monitoring links. Statistical APIs do not supply tariff rulings.

StatCan table metadata is verified against all expected dimension members on
each refresh. A changed coordinate meaning fails the refresh for review.
Reproduction requests are stored beside each series. See the
[WDS documentation](https://www.statcan.gc.ca/en/developers/wds/user-guide).

## Measurement rules

- Statistics Canada values are normalized as raw value × 10^scalar factor ÷
  the configured display divisor. Currency series display billions; employment
  displays millions. Source scaling is never guessed from magnitude.
- Growth rates require exact calendar lags. Missing months are not
  forward-filled or treated as zero. Suppressed, unavailable and unreliable
  values stay null; source status and revision flags are retained.
- Annualized quarterly GDP growth is `((level / previous_quarter) ** 4 - 1)
  * 100`. Month-on-month growth is not mislabeled as quarterly GDP growth.
- Rate changes are differences in percentage points. Relative percent growth
  is suppressed for percentage-rate series and the zero-centered GSCPI.
- Three-month growth uses six contiguous months: sum(last 3) / sum(previous 3)
  − 1. Quarterly flow totals require all three months for a complete-quarter
  label. A partial total is explicitly partial, not extrapolated.
- U.S. export share matches numerator and denominator on the same month and
  basis. Rest-of-world exports subtract U.S. exports from world exports.
- Construction price data cover a 15-CMA composite. Permit and investment
  values are nominal; industry and expenditure GDP are real. Chained-dollar
  industry levels are not summed.
- Canadian and U.S. CPI baskets and labour-force populations differ. Canadian
  overnight-target observations and U.S. monthly-average effective rates are
  different concepts, identified directly on the chart.
- Quarterly selections use current-vintage data. They do not provide
  real-time historical backtests or reconstruct information available then.
- The forward paths are illustrative, not estimated forecasts or confidence
  intervals. The central growth assumption is the median of the latest four
  annualized quarterly GDP growth rates; alternative paths add/subtract two
  percentage points. The quarterly compounding formula is
  `100 * (1 + annual_growth / 100) ** (quarters_ahead / 4)`.
- Business recommendations are conditional screening interpretations, not
  causal estimates or firm-specific investment advice. Screening thresholds
  (producer-price inflation 3%, GSCPI +1 standard deviation) are stated,
  configurable analytical choices rather than official risk boundaries.

## Keep the tariff watch current

Edit `data/policies.json` only after reading the official notice and annexes.
Record the announcement date, effective date, concise interpretation, source
URL and the actual substantive review date. Do not update `last_reviewed`
merely because an HTTP request succeeds. Refresh checks existing notice pages
for content changes and records failures in `data/policy_checks.json`. A change
is a prompt for review, not proof of a policy change; navigation edits can also
change a page hash. After reviewing a changed page, remove its old `checks`
record and refresh to establish the reviewed baseline. The display warns
after seven days without substantive policy review. Visit the official hubs
to discover new notices; this lightweight monitor is not exhaustive.

## Project-cost scenario

Budget shares must sum to 100% or less. The imported-material share is a share
of materials, not of the whole project. The baseline budget already includes
the baseline tariff. Imported materials are assumed priced in USD, unhedged
and fully exposed to the scenario tariff.

Imported cost multiplier = `(1 + material inflation) * (1 + CAD/USD change)
* (1 + scenario tariff) / (1 + baseline tariff)`.

Material-price, FX and tariff contributions are calculated sequentially to
include interaction effects exactly once. Labour is its budget share times
the labour-cost shock. Financing is constant drawn debt × basis points /
10,000 × months / 12; interest compounding and a draw schedule are omitted.
The independent revenue scenario is not added to capital-project costs.

## Extend or modify

| File | Role |
| --- | --- |
| `data/series.json` | Exact series coordinates, expected dimension names, units and divisors |
| `economy/sources.py` | Official data clients and failure handling |
| `economy/metrics.py` | Calendar-aligned growth and Python scenario calculations |
| `economy/outlook.py` | Quarterly aggregation, briefing text and forward paths |
| `templates/` | Responsive interface, SVG charts and browser interactions |
| `app.py` | Refresh, build, CSV/source exports and local serving |
| `tests/` | Calculation, missing-data, parser and rendered-markup checks |

To add a series, resolve its table dimensions using current WDS metadata,
add its exact expected members, set its real source units and display divisor,
and add it to the relevant dashboard view. Merely adding a series to the
source list does not place it into an analytical view.

## Validation

```sh
python -m unittest discover -s tests
node --check templates/app.js
node tests/interface-check.cjs
```

Node is optional for the last two developer checks, not required to run or
deploy the dashboard. The interface check exercises all views, export and
scenario calculations against a lightweight DOM stub; it is not a browser
layout test. Before a production rollout, inspect desktop and mobile layouts
in a browser. No browser-rendered visual QA was performed in the creation
environment.

## Attribution and reuse

Original code is MIT licensed. Source data retain their terms. Statistics
Canada data are reproduced/adapted under its
[Open Licence](https://www.statcan.gc.ca/en/reference/licence). This is not
an official Statistics Canada product or an endorsement. See also
[Bank of Canada terms](https://www.bankofcanada.ca/terms/),
[FRED terms](https://fred.stlouisfed.org/legal/terms-of-use), and
[New York Fed terms](https://www.newyorkfed.org/termsofuse). Preserve source
attribution when sharing the dashboard or its exports. Government logos are
not used.
