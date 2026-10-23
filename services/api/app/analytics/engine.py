import json
import math
import re
from collections import Counter, defaultdict
from fractions import Fraction
from importlib.resources import files
from pathlib import Path

import pandas as pd

from app.tabular.parsing import parse_amounts, parse_dates, text

from .fuzzy import clusters
from .models import MAPPING_KEYS, RULE_IDS, AnalysisResult, Finding, RulesConfig, Summary
from .parsing import invoice, same_identity


def run_rules(df, mapping: dict[str, str], config=None) -> AnalysisResult:
    """Accept a DataFrame or local DuckDB relation; positions are zero-based.

    A mapped row_id is returned verbatim as text; otherwise DataFrame index labels
    are used. Missing columns skip dependent rules; malformed values are excluded
    from dependent comparisons and reported in warnings.
    """
    cfg = config if isinstance(config, RulesConfig) else RulesConfig.model_validate(config or {})
    unknown = sorted(set(mapping) - MAPPING_KEYS)
    if unknown:
        raise ValueError(f"Bilinmeyen eşleme anahtarları: {unknown}")
    if not isinstance(df, pd.DataFrame):
        df = df.df()
    if not df.columns.is_unique:
        raise ValueError("Sütun adları benzersiz olmalıdır.")
    missing = sorted(set(mapping.values()) - set(df.columns))
    if missing:
        raise ValueError(f"Eşlenen sütunlar bulunamadı: {missing}")
    n = len(df)
    typed_fields = {"amount", "invoice_date", "payment_date"}
    values = {
        key: (df[col].tolist() if key in typed_fields else [text(v) for v in df[col]])
        for key, col in mapping.items()
    }
    rows = [{key: vals[i] for key, vals in values.items()} for i in range(n)]
    ids = values.get("row_id", [str(v) for v in df.index])
    findings, skipped, warnings = [], {}, []
    omitted = Counter()
    parsed_dates = (
        parse_dates(
            df[mapping[cfg.posting_date_field]],
            date_format=cfg.date_format,
            dayfirst=cfg.dayfirst,
            field=cfg.posting_date_field,
            warnings=warnings,
        )
        if cfg.posting_date_field in mapping
        else [None] * n
    )
    vendor = "vendor_id" if "vendor_id" in mapping else "vendor_name"
    parsed_amounts = parse_amounts(
        values.get("amount", [None] * n), decimal_separator=cfg.decimal_separator, warnings=warnings
    )
    blank_currencies = []
    for i, r in enumerate(rows):
        r["vendor"] = r.get(vendor)
        r["money"] = parsed_amounts[i]
        currency = r.get("currency")
        if "currency" in mapping and currency is None:
            blank_currencies.append(i)
        r["currency_key"] = currency.upper() if currency else cfg.default_currency
        if "currency" not in mapping and r["currency_key"] is None:
            r["currency_key"] = "UNSPECIFIED"
        r["normalized_invoice"] = invoice(r.get("invoice_no"))
        r["date"] = parsed_dates[i]
    if blank_currencies:
        warnings.append(
            f"Boş para birimi içeren satırlar {blank_currencies}; "
            + (
                f"{cfg.default_currency} varsayıldı."
                if cfg.default_currency
                else "para birimine bağlı kurallardan çıkarıldı."
            )
        )
    if "currency" not in mapping:
        warnings.append("Para birimi eşlenmedi; tüm tutarlar aynı para biriminde varsayıldı.")

    def ready(rule, *fields):
        absent = [f for f in fields if f not in mapping]
        if absent:
            skipped[rule] = "Eksik eşleme: " + ", ".join(absent)
        return not absent

    def add(rule, title, severity, explanation, positions, **evidence):
        if len(findings) >= cfg.max_findings:
            omitted[rule] += 1
            return
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
        for key, positions in groups("vendor", "money", "currency_key").items():
            for members in clusters(rows, positions, cfg.fuzzy_days):
                add(
                    "fuzzy_duplicate",
                    "Olası mükerrer ödeme",
                    "medium",
                    "Aynı tedarikçi, tutar ve para birimi; normalleştirilmiş fatura "
                    f"veya en fazla {cfg.fuzzy_days} günlük tarih bağlantılarıyla oluşan küme. "
                    "Kümenin uç tarihleri bu sınırı aşabilir.",
                    members,
                    vendor=key[0],
                    amount=str(key[1]),
                    currency=key[2],
                    fuzzy_days=cfg.fuzzy_days,
                    cluster_size=len(members),
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
        missing_limits = set()
        for i, r in enumerate(rows):
            amount, currency = r["money"], r["currency_key"]
            if amount is None or amount <= 0 or currency is None:
                continue
            threshold = (
                cfg.approval_threshold.get(currency)
                if isinstance(cfg.approval_threshold, dict)
                else cfg.approval_threshold
            )
            unit = (
                cfg.round_unit.get(currency) if isinstance(cfg.round_unit, dict) else cfg.round_unit
            )
            if threshold is None or unit is None:
                missing_limits.add(currency)
                continue
            round_amount = Fraction(amount) % Fraction(unit) == 0
            near = threshold - cfg.threshold_margin <= amount < threshold
            if round_amount or near:
                add(
                    "amount_pattern",
                    "Yuvarlak veya onay sınırına yakın tutar",
                    "low",
                    f"Tutar {amount} {currency}; yuvarlaklık birimi {unit}; "
                    f"onay sınırı {threshold}, alt marj {cfg.threshold_margin}.",
                    [i],
                    currency=currency,
                    approval_threshold=str(threshold),
                    round_unit=str(unit),
                    round_amount=round_amount,
                    below_threshold=near,
                )
        if missing_limits:
            warnings.append(f"Tutar kuralı için sınır/birim tanımsız: {sorted(missing_limits)}.")

    if ready("non_working_day", cfg.posting_date_field):
        holiday_file = (
            Path(cfg.holidays_path)
            if cfg.holidays_path
            else files(__package__).joinpath("holidays_tr.json")
        )
        try:
            holidays = json.loads(holiday_file.read_text(encoding="utf-8"))
            for field in (
                "religious_years",
                "annual_full_days",
                "annual_half_days",
                "full_days",
                "half_days",
            ):
                if not isinstance(holidays[field], list):
                    raise ValueError("Tatil listesi geçersiz.")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("Tatil yapılandırması okunamadı veya geçersiz.") from exc
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
            if same_identity(r.get("created_by"), r.get("approver")):
                add(
                    "segregation_of_duties",
                    "Görevler ayrılığı ihlali",
                    "high",
                    "Kaydı oluşturan kişi ile onaylayan kişi aynı.",
                    [i],
                    created_by=str(df.iloc[i][mapping["created_by"]]),
                    approver=str(df.iloc[i][mapping["approver"]]),
                )

    if ready("vendor_outlier", vendor, "amount"):
        for key, positions in groups("vendor", "currency_key").items():
            positions = [
                i for i in positions if rows[i]["money"] is not None and rows[i]["money"] > 0
            ]
            if len(positions) < cfg.outlier_min_samples:
                continue
            amounts = pd.Series([math.log10(rows[i]["money"]) for i in positions])
            if not all(math.isfinite(v) for v in amounts):
                warnings.append(f"{key}: istatistik hesabı için tutar aralığı çok büyük.")
                continue
            median = amounts.median()
            mad = (amounts - median).abs().median()
            q1, q3 = amounts.quantile([0.25, 0.75])
            lower, upper = q1 - cfg.iqr_multiplier * (q3 - q1), q3 + cfg.iqr_multiplier * (q3 - q1)
            median_amount = (
                sorted(rows[i]["money"] for i in positions)[len(positions) // 2]
                if mad == 0 and q3 == q1
                else None
            )
            for i, value in zip(positions, amounts, strict=True):
                score = 0.67448975 * abs(value - median) / mad if mad else None
                outlier = score > cfg.robust_z_threshold if mad else value < lower or value > upper
                if median_amount is not None:
                    deviation = abs(Fraction(rows[i]["money"]) / Fraction(median_amount) - 1)
                    outlier = outlier and deviation > Fraction(str(cfg.outlier_relative_tolerance))
                if outlier:
                    add(
                        "vendor_outlier",
                        "Tedarikçi bazında aykırı tutar",
                        "medium",
                        f"Tutar {rows[i]['money']}; log10 medyan {median}, MAD {mad}. "
                        + (
                            f"Sağlam z skoru {score:.4f} > {cfg.robust_z_threshold}."
                            if mad
                            else f"MAD sıfır; IQR sınırları [{lower}, {upper}] dışında."
                        ),
                        [i],
                        method="robust_z" if mad else "iqr",
                        scale="log10",
                        relative_tolerance=cfg.outlier_relative_tolerance,
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

    if omitted:
        warnings.append(
            f"Bulgu sınırı ({cfg.max_findings}) aşıldı; {sum(omitted.values())} bulgu döndürülmedi."
        )
    return AnalysisResult(
        findings=findings,
        summary=Summary(
            truncated=bool(omitted),
            omitted_by_rule=dict(omitted),
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
