# Offline payment rules

`run_rules(df, mapping, config=None)` accepts a pandas DataFrame or a local DuckDB
relation and returns an `AnalysisResult` Pydantic model (`findings` + `summary`).
Use `.model_dump()` for a dictionary. No network, database or LLM calls occur.
DuckDB is a main dependency so relation callers work outside development installs.

```python
from app.analytics import run_rules

result = run_rules(
    df,
    {
        "vendor_id": "SupplierCode",
        "invoice_no": "InvoiceNumber",
        "payment_date": "PostingDate",
        "amount": "Gross",
        "currency": "Currency",
    },
    {
        "date_format": "%d.%m.%Y",
        "decimal_separator": ",",
        "approval_threshold": {"TRY": "10000", "USD": "2000"},
        "round_unit": {"TRY": "1000", "USD": "100"},
        "max_findings": 1000,
    },
)
```

## Contract with the upload feature

The upload layer should hand over typed `datetime64`/native dates and
`Decimal`/numeric amount columns, choosing the source locale at ingestion.
These typed values are authoritative: they are not stringified and reparsed using
locale settings. Float inputs use their Python numeric representation for Decimal
conversion; use Decimal for source-exact monetary precision. The input is not mutated.

Text parsing is a fallback for inline testing or legacy exports:

- `date_format=None`, `dayfirst=True` by default. Text columns are parsed in bulk
  with `pd.to_datetime(errors="coerce")`; ISO year-first text has an explicit ISO
  path so dayfirst never swaps ISO month/day. Other mixed text uses the configured
  dayfirst policy. An explicit format (e.g. `%d.%m.%Y`) overrides text inference.
  Ambiguous day/month values and unparsed cells produce warnings with row positions.
  Native datetimes retain their local calendar day; numeric cells are not Unix dates.
- `decimal_separator="."` by default for compatibility; set `","` for Turkish
  text such as `1.234,56` → 1234.56 and `12.500` → 12500. Whitespace is removed,
  grouping is validated, and the other separator denotes thousands. A value whose
  configured decimal separator could instead be a grouping separator (e.g. `12.500`
  in dot mode) generates an ambiguity warning. Typed 12.5 remains 12.5 in either mode.
  Invalid/nonfinite values and exponents outside -308..308 are excluded with warnings.

Allowed mapping keys: `vendor_id`, `vendor_name`, `invoice_no`, `invoice_date`,
`payment_date`, `amount`, `currency`, `iban`, `approver`, `created_by`, `row_id`.
Unknown keys and nonexistent mapped columns are errors. Missing mappings skip
only dependent rules, recorded in `summary.skipped_rules`. Vendor ID takes
precedence over name. Blank values never match one another.

`row_indices` are zero-based input positions. `row_ids` use mapped IDs as text,
falling back to DataFrame index labels. Sort a DuckDB relation first if stable
positions across materializations matter. Findings follow stable rule/input order.
Currency strings are trimmed and uppercased. Blank mapped currencies always warn;
`default_currency="TRY"` fills them, while `None` excludes them from currency-bound
rules. An unmapped currency retains the single-currency assumption and warning.

## Rule semantics

- **Exact duplicates**: same vendor, literal trimmed invoice number, Decimal amount,
  and currency; one finding per group.
- **Fuzzy duplicates**: same vendor/amount/currency and either dates within
  `fuzzy_days` (inclusive, default 3) or matching normalized invoice segments.
  Invoice tokenization happens **before** punctuation removal; each numeric token
  loses leading zeros, letters are uppercased, and token boundaries are retained.
  Thus `INV-001-05`, `inv-1-5`, and `INV 001 / 05` match, but `1-02` and `10-2`
  do not. Pure exact duplicate pairs remain the responsibility of the exact rule.
  A hash lookup handles normalized invoices; two directional sliding date windows
  link nearest different invoices. Union-find merges the connections into one
  finding per connected cluster in O(n log n) time / O(n) memory, without emitting
  or enumerating all pairs. Transitive clusters can span more than N days; the
  explanation explicitly says this. A row may appear in both exact and fuzzy
  findings when an exact group is connected to a distinct invoice representation.
- **Shared IBAN**: whitespace-free, uppercased IBAN shared by distinct vendors.
  This is a sharing check, not checksum validation.
- **Amount patterns**: positive multiples of `round_unit`, or amounts in
  `[approval_threshold - threshold_margin, approval_threshold)`. Threshold and unit
  each accept a positive scalar (legacy single policy) or a currency → Decimal map.
  If either map lacks a currency, that currency's amount-pattern rule is skipped
  with a warning; no currency conversion or hidden fallback occurs. The margin is
  a common numeric value (default 100). Evidence records the actual currency/limits.
- **Non-working day**: `payment_date`, or `invoice_date` via `posting_date_field`.
  Local JSON covers recurring Turkish holidays and 2023–2027 religious holidays,
  including eves. Sources are recorded in `holidays_tr.json`, including
  [Diyanet's calendar](https://mobil.diyanet.gov.tr/mobile/dinigunler/dinigunler.html).
  Uncovered religious years warn. `extra_holidays` adds local days. Half-days are
  conservatively flagged for the entire date; `flag_half_days=false` disables this.
  Trusted library callers can set `holidays_path` to an external JSON with the same
  schema. For the API, administrators set `ANALYTICS_HOLIDAYS_PATH`; request-supplied
  filesystem paths are rejected. No calendar API is contacted at runtime.
- **Segregation of duties**: trim and compare case-insensitively. ASCII-only account
  codes use ASCII case folding (`ali` = `ALI`). If either identifier contains Turkish
  characters, Turkish `İ→i`, `I→ı` casing applies (`İpek` = `ipek`, `IŞIK` = `ışık`),
  preserving the dotted/dotless distinction. Evidence retains both original values.
- **Vendor outliers**: per vendor/currency, positive amounts only; refunds and zero
  are excluded. At least 5 samples. Modified z-score is
  `0.67448975 * abs(log10(x) - median(log10(x))) / MAD`, strictly above 3.5.
  Zero MAD falls back to Tukey IQR bounds (multiplier 1.5) on log amounts.
  If both MAD and IQR are zero, also require a relative deviation from the median
  above `outlier_relative_tolerance` (default 0.10). Evidence labels log-scale
  medians/bounds and includes the original amount in the explanation.
- **Benford**: per currency, positive amounts, at least 100 samples. First-digit
  proportions are compared with log10(1 + 1/d); MAD above 0.015 yields a single
  summary finding without individual accused rows. This is a screening heuristic
  for suitable naturally occurring amounts, not proof of fraud.

`max_findings` caps the **total** returned findings (default 1000, maximum 10000).
Rules still count omitted findings without allocating Finding objects. A cap hit
sets `summary.truncated`, reports exact `omitted_by_rule` counts, and adds a warning.
`total_findings`, `by_rule`, `by_severity`, and `affected_rows` describe returned
findings only. Review omissions before treating the returned result as complete.

## Inline endpoint and limits

`POST /analysis/run`:

```json
{
  "rows": [{"maker": "Ali", "signer": "ALI", "id": "P-1"}],
  "mapping": {"created_by": "maker", "approver": "signer", "row_id": "id"},
  "config": {}
}
```

The route accepts at most 10,000 rows, 200 columns per row **and across the table**,
1,000 characters per cell/column name, and a 10 MiB JSON body. ASGI middleware
checks Content-Length and actual streamed bytes (including chunked requests)
**before** FastAPI/Pydantic parse JSON. Oversized bodies return 413; unknown mappings,
invalid configuration or table shape return 422. Apply ingress limits too when
operating behind a proxy. Large uploaded datasets should call the typed library
entrypoint in a background worker, not serialize a full table into this test route.

From `services/api`: `python -m pytest`. The suite includes all eight planted rules,
locale/typed regressions, segment collisions, a brute-force fuzzy-cluster oracle,
a dense 10,000-row case, truncation, currencies, log outliers, Turkish identities,
calendar years, custom calendars, request limits, DuckDB parity and offline execution.

Both ingestion and analytics now call `app/tabular/parsing.py`; there is no second
Turkish date/amount parser. Ingestion can infer a column locale (`auto`); analytics
uses the explicit configured fallback for text and treats typed columns as final.
Mixed timezone timestamps are evaluated by local posting date without UTC shifting.
