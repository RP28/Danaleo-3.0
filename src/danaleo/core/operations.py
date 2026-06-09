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
    return operation_type.replace("_", " ").title()
