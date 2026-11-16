# praesago (Python)

Python client for the [Praesago API](https://praesago.com/docs/api): property and area data for every postcode district in **England and Wales**. Sold prices, sector prices, price per square foot, rents and yields, weekly asking-market statistics, planning, crime, schools, flood risk, broadband and more, from official sources joined in one place.

No dependencies. Python 3.10 or later.

```bash
pip install praesago
```

## Start

Create a key at <https://praesago.com/settings/api-keys>. Every account gets 500 free credits each month.

```bash
export PRAESAGO_API_KEY=your-key
```

```python
from praesago import Praesago

client = Praesago()                      # reads PRAESAGO_API_KEY

e17 = client.district("E17")             # everything for one district
print(e17["area_name"], e17["median_sold_price_gbp"])

print(client.last_credits)               # Credits(charged=3, remaining=497)
```

Try it without a key:

```python
Praesago().demo()        # real figures for E17
Praesago().catalogue()   # every source, licence, period and coverage
```

## Examples

**Buy-to-let screen: districts with a 6% or higher asking yield under £250,000**

```python
for row in client.screen(min_yield_pct=6, max_median_price_gbp=250_000, sort_by="yield", limit=10):
    print(row)
```

**Compare two districts**

```python
client.compare("E17", "CF10")
```

**Headline facts for many districts in one call** (1 credit for each district found, up to 50)

```python
client.batch(["E17", "M14", "LS6", "CF24"])
```

## All methods

| Method | What it returns |
|---|---|
| `district(d, sections=None)` | Everything held for one district. `sections` limits the reply. |
| `context(d)` | Market context for a district |
| `sectors(d)` | Sold prices by postcode sector (a median needs 10 or more sales) |
| `sold_psf(d)` | Sold price per square foot (houses) |
| `rental(d)` | Rent and yield by bedrooms, rental demand, Local Housing Allowance |
| `price_history(d, months=None)` | Monthly HPI and yearly ONS medians |
| `planning(d, months=None)` | Planning activity (1 to 24 months) |
| `listings(d, channel=None, weeks=None, source=None)` | Weekly asking-market statistics (`sale` or `rent`) |
| `movers(channel=None, metric=None, limit=None)` | Biggest week-over-week changes (`price` or `inventory`) |
| `search(q, limit=None)` | Find districts by outcode or place name |
| `screen(**filters)` | Filter districts by price, rent, listings, price cuts, yield, region |
| `compare(a, b)` | Two districts side by side |
| `batch(districts)` | Headline facts for up to 50 districts |
| `catalogue()` | Sources and coverage (no key) |
| `demo()` | Fixed demo district (no key) |

Credit costs for each call are on the [pricing page](https://praesago.com/pricing).

## Errors

Every error is a `PraesagoError` with `status`, `code` (stable, branch on it), `request_id` (quote it to support) and `retry_after` when the server sends it.

```python
from praesago import InsufficientCreditsError, NotFoundError

try:
    client.district("ZZ99")
except NotFoundError:
    ...                      # not a district in England and Wales
except InsufficientCreditsError:
    ...                      # buy credits at https://praesago.com/pricing
```

The client retries rate limits (429) and server faults (5xx) twice, with back-off. Change it with `Praesago(max_retries=0)`.

## Also

- MCP server for AI assistants: <https://praesago.com/docs/mcp>
- JavaScript client: [Praesago/praesago-js](https://github.com/Praesago/praesago-js)

MIT licence.
