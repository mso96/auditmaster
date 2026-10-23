# Offline payment rules

`run_rules(df, mapping, config=None)` accepts a pandas DataFrame or an already-created
local DuckDB relation. It returns an `AnalysisResult` Pydantic model (`findings` and
`summary`); call `.model_dump()` for a dictionary. No LLM, database, holiday service,
or network is used by the analytics module. Dependencies must be installed before
moving the application on-prem.

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
    {"fuzzy_days": 3, "approval_threshold": "10000", "threshold_margin": "100"},
)
```

Map any subset of `vendor_id`, `vendor_name`, `invoice_no`, `invoice_date`,
`payment_date`, `amount`, `currency`, `iban`, `approver`, `created_by`, `row_id`.
Vendor ID takes precedence over vendor name. Missing mappings skip dependent rules
and appear in `summary.skipped_rules`; mapped nonexistent columns are errors.
Null/blank values never match one another. Invalid dates/amounts are excluded from
dependent calculations, with row positions reported in warnings. Use ISO dates
and numeric amounts (or decimal strings, without thousands separators). Dates
retain their supplied local calendar day; there is no implicit timezone conversion.

`row_indices` are always zero-based input positions, including nonunique DataFrame
indices. `row_ids` are stringified mapped IDs, falling back to DataFrame index labels.
DuckDB relations use their materialized order; order the relation first when stable
cross-run row positions matter. Findings have stable rule order and input row order.

Rules and interpretation:

- Exact duplicates group vendor, literal trimmed invoice number, Decimal amount,
  and currency. Groups produce one finding.
- Fuzzy duplicates produce pairs with the same vendor, amount, and currency when
  dates differ by at most `fuzzy_days` (inclusive), or invoice numbers match after
  removing whitespace/punctuation and leading zeros from each numeric segment.
  Invoice letter case is preserved. Exact duplicate pairs are excluded.
- Shared IBAN removes whitespace and uppercases; at least two distinct nonblank
  vendors must share it. It does not validate IBAN checksums.
- Amount patterns flag positive multiples of `round_unit` (default 1000) and the
  interval `[approval_threshold - threshold_margin, approval_threshold)`.
  Thresholds apply numerically to each currency; run currency-specific batches
  with separate configuration when approval policies differ.
- Non-working dates use `payment_date` by default; select `invoice_date` with
  `posting_date_field`. `holidays_tr.json` contains recurring Turkish public
  holidays and 2026 religious holidays, verified against the Diyanet source URL
  in that file. Extend the packaged JSON for additional years; missing religious
  years produce warnings. `extra_holidays` adds local dates. Half-days are flagged
  for the entire date because inputs may have no time; disable with
  `flag_half_days=false` if this conservative screening is unsuitable.
- Duties compare trimmed nonblank creator/approver identities exactly.
- Vendor/currency outliers need at least 5 valid amounts. Modified absolute z-score
  is `0.67448975 * abs(x - median) / MAD`, flagged strictly above 3.5. Zero MAD
  falls back to Tukey bounds with multiplier 1.5 and pandas linear quartiles;
  with zero IQR, any value outside the common quartile value is flagged.
- Benford runs separately per currency on positive, nonzero amounts, including
  fractions; refunds are excluded. At least 100 samples are required. A single
  summary finding (no individual accused rows) reports first-digit counts,
  expected log10(1 + 1/d) proportions and mean absolute deviation, flagged above
  0.015. Benford is a screening heuristic, meaningful only for suitable naturally
  occurring amounts spanning orders of magnitude, not proof of fraud.

All configuration defaults and bounds are in `RulesConfig`. Monetary comparisons
never cross mapped currencies. Without a currency mapping, a warning explicitly
states the single-currency assumption. Summary counts count findings, not pairs
within exact groups; affected rows are the union of row-level findings.
Fuzzy matching can produce quadratically many pairs within a vendor/amount group;
use bounded batches for large exports.

## Inline test endpoint

`POST /analysis/run` (maximum 10,000 inline rows; no upload endpoint):

```json
{
  "rows": [{"maker": "Ali", "signer": "Ali", "id": "P-1"}],
  "mapping": {"created_by": "maker", "approver": "signer", "row_id": "id"},
  "config": {}
}
```

Response: `{ "findings": [...], "summary": {...} }`. Bad mappings/configuration
return HTTP 422; empty rows return an empty result. No UI or persistence is added.

From `services/api`: `python -m pytest`. Tests contain explicit planted matches,
negatives, currency isolation, MAD-zero fallback, Benford distributions, holidays,
column renaming, DuckDB parity and an endpoint test forbidding network connections.
