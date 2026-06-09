from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype


def infer_kind(series: pd.Series) -> str:
    if is_bool_dtype(series):
        return "categorical"
    if is_numeric_dtype(series):
        return "numeric"
    if is_datetime64_any_dtype(series):
        return "datetime"
    return "categorical"


def _safe_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def dataframe_overview(df: pd.DataFrame) -> dict[str, Any]:
    memory_bytes = int(df.memory_usage(deep=True).sum())
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "memory_bytes": memory_bytes,
        "memory_mb": round(memory_bytes / (1024 * 1024), 3),
    }


def dataset_profile(df: pd.DataFrame, preview_rows: int = 8) -> dict[str, Any]:
    """Return a compact, JSON-safe profile for the overview-first UI."""
    rows = len(df)
    columns = column_cards(df)
    missing_cells = int(df.isna().sum().sum())
    total_cells = max(rows * len(df.columns), 1)
    numeric_names = [card["name"] for card in columns if card["kind"] == "numeric"]
    categorical_names = [card["name"] for card in columns if card["kind"] == "categorical"]

    high_missing = sorted(
        (
            {"name": card["name"], "missing_pct": card["missing_pct"], "missing": card["missing"]}
            for card in columns
            if card["missing"] > 0
        ),
        key=lambda item: item["missing_pct"],
        reverse=True,
    )[:8]

    correlations: list[dict[str, Any]] = []
    correlation_names = numeric_names[:40]
    if len(correlation_names) >= 2:
        corr = df[correlation_names].corr(numeric_only=True)
        for left_index, left in enumerate(corr.columns):
            for right in corr.columns[left_index + 1 :]:
                value = corr.loc[left, right]
                if pd.notna(value):
                    correlations.append(
                        {"left": str(left), "right": str(right), "value": round(float(value), 4)}
                    )
        correlations.sort(key=lambda item: abs(item["value"]), reverse=True)

    preview = [
        {str(key): _safe_value(value) for key, value in row.items()}
        for row in df.head(preview_rows).to_dict(orient="records")
    ]

    return {
        "rows": int(rows),
        "columns": int(len(df.columns)),
        "numeric_columns": len(numeric_names),
        "categorical_columns": len(categorical_names),
        "datetime_columns": sum(card["kind"] == "datetime" for card in columns),
        "missing_cells": missing_cells,
        "missing_pct": round((missing_cells / total_cells) * 100, 2),
        "duplicate_rows": int(df.duplicated().sum()),
        "high_missing": high_missing,
        "top_correlations": correlations[:8],
        "correlation_columns_analyzed": len(correlation_names),
        "preview_columns": [str(column) for column in df.columns[:12]],
        "preview": preview,
    }


def column_cards(df: pd.DataFrame) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    rows = max(len(df), 1)
    for name in df.columns:
        series = df[name]
        missing = int(series.isna().sum())
        cards.append(
            {
                "name": str(name),
                "dtype": str(series.dtype),
                "kind": infer_kind(series),
                "missing": missing,
                "missing_pct": round((missing / rows) * 100, 2),
                "unique": int(series.nunique(dropna=True)),
            }
        )
    return cards


def column_stats(df: pd.DataFrame, column: str) -> dict[str, Any]:
    if column not in df.columns:
        raise KeyError(f"Unknown column: {column}")

    series = df[column]
    non_null = series.dropna()
    kind = infer_kind(series)
    base: dict[str, Any] = {
        "name": column,
        "dtype": str(series.dtype),
        "kind": kind,
        "rows": int(len(series)),
        "non_null": int(series.notna().sum()),
        "missing": int(series.isna().sum()),
        "missing_pct": round((series.isna().sum() / max(len(series), 1)) * 100, 2),
        "unique": int(series.nunique(dropna=True)),
        "sample_values": [_safe_value(v) for v in non_null.head(12).tolist()],
    }

    if kind == "numeric":
        desc = non_null.astype(float).describe(percentiles=[0.25, 0.5, 0.75])
        base["stats"] = {
            "mean": _safe_value(desc.get("mean")),
            "median": _safe_value(desc.get("50%")),
            "std": _safe_value(desc.get("std")),
            "min": _safe_value(desc.get("min")),
            "q1": _safe_value(desc.get("25%")),
            "q3": _safe_value(desc.get("75%")),
            "max": _safe_value(desc.get("max")),
        }
    else:
        counts = series.astype("string").fillna("<missing>").value_counts(dropna=False).head(30)
        base["stats"] = {
            "top_values": [
                {"value": str(index), "count": int(value)} for index, value in counts.items()
            ]
        }

    return base
