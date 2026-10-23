import json
import math
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from importlib.resources import files
from itertools import combinations

import pandas as pd

from .models import RULE_IDS, AnalysisResult, Finding, RulesConfig, Summary


def _text(value):
    if value is None or pd.isna(value):
        return None
    return str(value).strip() or None


def _amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _invoice(value):
    if not value:
        return None
    value = "".join(c for c in value if c.isalnum())
    return re.sub(r"\d+", lambda m: m.group().lstrip("0") or "0", value) or None


def run_rules(df, mapping: dict[str, str], config=None) -> AnalysisResult:
    """Accept a DataFrame or local DuckDB relation; positions are zero-based.

    A mapped row_id is returned verbatim as text; otherwise DataFrame index labels
    are used. Missing columns skip dependent rules; malformed values are excluded
    from dependent comparisons and reported in warnings.
    """
    cfg = config if isinstance(config, RulesConfig) else RulesConfig.model_validate(config or {})
    if not isinstance(df, pd.DataFrame):
        df = df.df()
    if not df.columns.is_unique:
        raise ValueError("Sütun adları benzersiz olmalıdır.")
    missing = sorted(set(mapping.values()) - set(df.columns))
    if missing:
        raise ValueError(f"Eşlenen sütunlar bulunamadı: {missing}")
    n = len(df)
    values = {key: [_text(v) for v in df[col]] for key, col in mapping.items()}
    rows = [{key: vals[i] for key, vals in values.items()} for i in range(n)]
    ids = values.get("row_id", [str(v) for v in df.index])
    findings, skipped, warnings = [], {}, []
    vendor = "vendor_id" if "vendor_id" in mapping else "vendor_name"
    for r in rows:
        r["vendor"] = r.get(vendor)
        r["money"] = _amount(r.get("amount"))
        r["currency_key"] = r.get("currency") if "currency" in mapping else "UNSPECIFIED"
        r["normalized_invoice"] = _invoice(r.get("invoice_no"))
        raw_date = r.get(cfg.posting_date_field)
        try:
            parsed_date = pd.Timestamp(raw_date) if raw_date else None
            r["date"] = (
                parsed_date.date() if parsed_date is not None and not pd.isna(parsed_date) else None
            )
        except (ValueError, TypeError, OverflowError):
            r["date"] = None
    for field, parsed in [("amount", "money"), (cfg.posting_date_field, "date")]:
        bad = [i for i, r in enumerate(rows) if r.get(field) and r[parsed] is None]
        if bad:
            warnings.append(f"{field}: geçersiz değer içeren satırlar {bad}.")
    if "currency" not in mapping:
        warnings.append("Para birimi eşlenmedi; tüm tutarlar aynı para biriminde varsayıldı.")

    def ready(rule, *fields):
        absent = [f for f in fields if f not in mapping]
        if absent:
            skipped[rule] = "Eksik eşleme: " + ", ".join(absent)
        return not absent

    def add(rule, title, severity, explanation, positions, **evidence):
        findings.append(
            Finding(
                rule_id=rule,
                title=title,
                severity=severity,
                explanation=explanation,
                row_indices=positions,
                row_ids=[ids[i] or str(df.index[i]) for i in positions],
                evidence=evidence,
            )
        )

    def groups(*keys):
        result = defaultdict(list)
        for i, r in enumerate(rows):
            key = tuple(r.get(k) for k in keys)
            if all(v is not None for v in key):
                result[key].append(i)
        return result

    if ready("exact_duplicate", vendor, "invoice_no", "amount"):
        for key, positions in groups("vendor", "invoice_no", "money", "currency_key").items():
            if len(positions) > 1:
                add(
                    "exact_duplicate",
                    "Aynı ödemenin tekrarı",
                    "high",
                    "Tedarikçi, fatura numarası, tutar ve para birimi aynı.",
                    positions,
                    vendor=key[0],
                    invoice_no=key[1],
                    amount=str(key[2]),
                    currency=key[3],
                )

    if ready("fuzzy_duplicate", vendor, "amount"):
        for _, positions in groups("vendor", "money", "currency_key").items():
            for a, b in combinations(positions, 2):
                left, right = rows[a], rows[b]
                if left.get("invoice_no") and left.get("invoice_no") == right.get("invoice_no"):
                    continue  # Already represented by the exact rule.
                normalized = (
                    left["normalized_invoice"] is not None
                    and left["normalized_invoice"] == right["normalized_invoice"]
                )
                days = (
                    abs((left["date"] - right["date"]).days)
                    if left["date"] and right["date"]
                    else None
                )
                if normalized or (days is not None and days <= cfg.fuzzy_days):
                    add(
                        "fuzzy_duplicate",
                        "Olası mükerrer ödeme",
                        "medium",
                        "Aynı tedarikçi, tutar ve para birimi; "
                        + (
                            "fatura numaraları normalleştirilince aynı."
                            if normalized
                            else f"Tarih farkı {days} gün (sınır {cfg.fuzzy_days})."
                        ),
                        [a, b],
                        normalized_invoice_match=normalized,
                        days_apart=days,
                    )

    if ready("shared_iban", vendor, "iban"):
        for r in rows:
            r["iban_key"] = re.sub(r"\s+", "", r.get("iban") or "").upper() or None
        for (iban,), positions in groups("iban_key").items():
            positions = [i for i in positions if rows[i]["vendor"]]
            vendors = sorted({rows[i]["vendor"] for i in positions})
            if len(vendors) > 1:
                add(
                    "shared_iban",
                    "Ortak IBAN kullanan tedarikçiler",
                    "high",
                    "Aynı IBAN birden fazla tedarikçiye bağlı.",
                    positions,
                    iban=iban,
                    vendors=vendors,
                )

    if ready("amount_pattern", "amount"):
        for i, r in enumerate(rows):
            amount = r["money"]
            if amount is None or amount <= 0:
                continue
            round_amount = Fraction(amount) % Fraction(cfg.round_unit) == 0
            near = cfg.approval_threshold - cfg.threshold_margin <= amount < cfg.approval_threshold
            if round_amount or near:
                add(
                    "amount_pattern",
                    "Yuvarlak veya onay sınırına yakın tutar",
                    "low",
                    f"Tutar {amount}; yuvarlaklık birimi {cfg.round_unit}; "
                    f"onay sınırı {cfg.approval_threshold}, alt marj {cfg.threshold_margin}.",
                    [i],
                    round_amount=round_amount,
                    below_threshold=near,
                )

    if ready("non_working_day", cfg.posting_date_field):
        holidays = json.loads(files(__package__).joinpath("holidays_tr.json").read_text())
        uncovered = sorted(
            {r["date"].year for r in rows if r["date"]} - set(holidays["religious_years"])
        )
        if uncovered:
            warnings.append(f"Dini bayram takvimi bu yılları kapsamıyor: {uncovered}.")
        for i, r in enumerate(rows):
            d = r["date"]
            if not d:
                continue
            full = (
                d.strftime("%m-%d") in holidays["annual_full_days"]
                or d.isoformat() in holidays["full_days"]
                or d in cfg.extra_holidays
            )
            half = (
                d.strftime("%m-%d") in holidays["annual_half_days"]
                or d.isoformat() in holidays["half_days"]
            )
            if d.weekday() >= 5 or full or (half and cfg.flag_half_days):
                add(
                    "non_working_day",
                    "Tatil gününde kayıt",
                    "low",
                    f"{d}: hafta sonu veya resmi tatil. Yarım günler tarih düzeyinde incelenir.",
                    [i],
                    date=d.isoformat(),
                    weekend=d.weekday() >= 5,
                    public_holiday=full,
                    half_day=half,
                )

    if ready("segregation_of_duties", "created_by", "approver"):
        for i, r in enumerate(rows):
            if r.get("created_by") and r["created_by"] == r.get("approver"):
                add(
                    "segregation_of_duties",
                    "Görevler ayrılığı ihlali",
                    "high",
                    "Kaydı oluşturan kişi ile onaylayan kişi aynı.",
                    [i],
                    user=r["created_by"],
                )

    if ready("vendor_outlier", vendor, "amount"):
        for key, positions in groups("vendor", "currency_key").items():
            positions = [i for i in positions if rows[i]["money"] is not None]
            if len(positions) < cfg.outlier_min_samples:
                continue
            amounts = pd.Series([float(rows[i]["money"]) for i in positions])
            if not all(math.isfinite(v) for v in amounts):
                warnings.append(f"{key}: istatistik hesabı için tutar aralığı çok büyük.")
                continue
            median = amounts.median()
            mad = (amounts - median).abs().median()
            q1, q3 = amounts.quantile([0.25, 0.75])
            lower, upper = q1 - cfg.iqr_multiplier * (q3 - q1), q3 + cfg.iqr_multiplier * (q3 - q1)
            for i, value in zip(positions, amounts, strict=True):
                score = 0.67448975 * abs(value - median) / mad if mad else None
                outlier = score > cfg.robust_z_threshold if mad else value < lower or value > upper
                if outlier:
                    add(
                        "vendor_outlier",
                        "Tedarikçi bazında aykırı tutar",
                        "medium",
                        f"Tutar {value}; medyan {median}, MAD {mad}. "
                        + (
                            f"Sağlam z skoru {score:.4f} > {cfg.robust_z_threshold}."
                            if mad
                            else f"MAD sıfır; IQR sınırları [{lower}, {upper}] dışında."
                        ),
                        [i],
                        method="robust_z" if mad else "iqr",
                        median=median,
                        mad=mad,
                        robust_z=score,
                        lower=lower,
                        upper=upper,
                    )

    if ready("benford", "amount"):
        for (currency,), positions in groups("currency_key").items():
            eligible = [
                i for i in positions if rows[i]["money"] is not None and rows[i]["money"] > 0
            ]
            if len(eligible) < cfg.benford_min_samples:
                continue
            counts = Counter(rows[i]["money"].as_tuple().digits[0] for i in eligible)
            expected = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
            mad = sum(abs(counts[d] / len(eligible) - expected[d]) for d in expected) / 9
            if mad > cfg.benford_mad_threshold:
                add(
                    "benford",
                    "Benford ilk basamak sapması",
                    "medium",
                    f"{len(eligible)} pozitif tutarda ilk basamak MAD {mad:.6f}; "
                    f"sınır {cfg.benford_mad_threshold}. Bu toplu tarama hile kanıtı değildir.",
                    [],
                    currency=currency,
                    sample_size=len(eligible),
                    mad=mad,
                    observed_counts={str(d): counts[d] for d in expected},
                    expected_proportions={str(d): v for d, v in expected.items()},
                )

    return AnalysisResult(
        findings=findings,
        summary=Summary(
            total_rows=n,
            total_findings=len(findings),
            affected_rows=len({i for f in findings for i in f.row_indices}),
            by_rule={rule: sum(f.rule_id == rule for f in findings) for rule in RULE_IDS},
            by_severity={
                s: sum(f.severity == s for f in findings) for s in ["low", "medium", "high"]
            },
            skipped_rules=skipped,
            warnings=warnings,
        ),
    )
