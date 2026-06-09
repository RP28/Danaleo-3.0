from __future__ import annotations

from typing import Any

import pandas as pd


def parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if raw.lower() in {"none", "null", "nan"}:
        return pd.NA
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def apply_operation(df: pd.DataFrame, operation_type: str, params: dict[str, Any]) -> pd.DataFrame:
    if operation_type == "filter_rows":
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("Filter query cannot be empty")
        result = df.query(query).copy()
        if result.empty:
            raise ValueError("Filter returned no rows. Refine the query before applying globally.")
        return result

    if operation_type == "drop_column":
        column = str(params.get("column", ""))
        if column not in df.columns:
            raise ValueError(f"Column not found: {column}")
        return df.drop(columns=[column]).copy()

    if operation_type == "replace_values":
        column = str(params.get("column", ""))
        if column not in df.columns:
            raise ValueError(f"Column not found: {column}")
        multiple = bool(params.get("multiple", False))
        new_df = df.copy()
        if multiple:
            old_values = [parse_scalar(x) for x in str(params.get("old_value", "")).split(",")]
            new_values = [parse_scalar(x) for x in str(params.get("new_value", "")).split(",")]
            if len(old_values) != len(new_values):
                raise ValueError("Old values and new values must have the same comma-separated count")
            new_df[column] = new_df[column].replace(old_values, new_values)
        else:
            old_value = parse_scalar(str(params.get("old_value", "")))
            new_value = parse_scalar(str(params.get("new_value", "")))
            new_df[column] = new_df[column].replace(old_value, new_value)
        return new_df

    if operation_type == "drop_missing":
        column = str(params.get("column", ""))
        if column not in df.columns:
            raise ValueError(f"Column not found: {column}")
        result = df.dropna(subset=[column]).copy()
        if result.empty:
            raise ValueError("Dropping missing values would remove all rows")
        return result

    if operation_type == "drop_duplicates":
        return df.drop_duplicates().copy()

    if operation_type == "impute_missing":
        column = str(params.get("column", ""))
        if column not in df.columns:
            raise ValueError(f"Column not found: {column}")

        method = str(params.get("method", "")).strip()
        allowed_methods = {
            "mean",
            "median",
            "mode",
            "constant",
            "forward_fill",
            "backward_fill",
            "interpolate",
        }
        if method not in allowed_methods:
            raise ValueError(f"Unsupported imputation method: {method}")

        series = df[column]
        missing_before = int(series.isna().sum())
        if missing_before == 0:
            raise ValueError(f"Column has no missing values: {column}")

        if method in {"mean", "median", "interpolate"} and not pd.api.types.is_numeric_dtype(series):
            raise ValueError(f"{method.replace('_', ' ').title()} imputation requires a numeric column")

        if method == "mean":
            filled = series.fillna(series.mean())
        elif method == "median":
            filled = series.fillna(series.median())
        elif method == "mode":
            modes = series.mode(dropna=True)
            if modes.empty:
                raise ValueError("Mode imputation requires at least one non-missing value")
            filled = series.fillna(modes.iloc[0])
        elif method == "constant":
            if "value" not in params:
                raise ValueError("Constant imputation requires a replacement value")
            filled = series.fillna(parse_scalar(str(params["value"])))
        elif method == "forward_fill":
            filled = series.ffill()
        elif method == "backward_fill":
            filled = series.bfill()
        else:
            filled = series.interpolate(method="linear")

        if int(filled.isna().sum()) >= missing_before:
            raise ValueError(f"{method.replace('_', ' ').title()} imputation could not fill any values")

        new_df = df.copy()
        new_df[column] = filled
        return new_df

    raise ValueError(f"Unsupported operation: {operation_type}")


def operation_label(operation_type: str, params: dict[str, Any]) -> str:
    if operation_type == "filter_rows":
        return f"Filter: {params.get('query', '')}"
    if operation_type == "drop_column":
        return f"Drop column: {params.get('column', '')}"
    if operation_type == "replace_values":
        return f"Replace in {params.get('column', '')}"
    if operation_type == "drop_missing":
        return f"Drop missing: {params.get('column', '')}"
    if operation_type == "drop_duplicates":
        return "Drop duplicate rows"
    if operation_type == "impute_missing":
        method = str(params.get("method", "")).replace("_", " ").title()
        return f"Impute {params.get('column', '')}: {method}"
    return operation_type.replace("_", " ").title()
