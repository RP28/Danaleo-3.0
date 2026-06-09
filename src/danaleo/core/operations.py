from __future__ import annotations

from typing import Any

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype


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


def _replacement_targets(params: dict[str, Any]) -> Any:
    if params.get("multiple", False):
        return [parse_scalar(value) for value in str(params.get("old_value", "")).split(",")]
    return parse_scalar(str(params.get("old_value", "")))


def _replacement_mask(series: pd.Series, targets: Any) -> pd.Series:
    values = targets if isinstance(targets, list) else [targets]
    non_missing = [value for value in values if not pd.isna(value)]
    mask = series.isin(non_missing)
    if any(pd.isna(value) for value in values):
        mask = mask | series.isna()
    return mask


def _statistical_replacement(series: pd.Series, targets: Any, method: str) -> Any:
    remaining = series.mask(_replacement_mask(series, targets)).dropna()
    if remaining.empty:
        raise ValueError(f"{method.title()} replacement requires at least one remaining value")
    if method in {"mean", "median"}:
        if not is_numeric_dtype(series) or is_bool_dtype(series):
            raise ValueError(f"{method.title()} replacement requires a numeric column")
        return getattr(remaining, method)()
    modes = remaining.mode(dropna=True)
    if modes.empty:
        raise ValueError("Mode replacement requires at least one remaining value")
    return modes.iloc[0]


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
        replacement_method = str(params.get("replacement_method", "constant")).strip()
        allowed_methods = {"constant", "nan", "mean", "median", "mode"}
        if replacement_method not in allowed_methods:
            raise ValueError(f"Unsupported replacement method: {replacement_method}")

        old_value = _replacement_targets(params)
        new_df = df.copy()
        if replacement_method == "constant" and multiple:
            new_values = [parse_scalar(x) for x in str(params.get("new_value", "")).split(",")]
            if len(old_value) != len(new_values):
                raise ValueError("Old values and new values must have the same comma-separated count")
            new_df[column] = new_df[column].replace(old_value, new_values)
        else:
            if replacement_method == "constant":
                new_value = parse_scalar(str(params.get("new_value", "")))
            elif replacement_method == "nan":
                new_value = pd.NA
            else:
                new_value = _statistical_replacement(df[column], old_value, replacement_method)
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

    if operation_type == "transform_column":
        column = str(params.get("column", ""))
        if column not in df.columns:
            raise ValueError(f"Column not found: {column}")

        method = str(params.get("method", "")).strip()
        allowed_methods = {"one_hot", "ordinal", "min_max", "standardize"}
        if method not in allowed_methods:
            raise ValueError(f"Unsupported transformation method: {method}")

        series = df[column]
        new_df = df.copy()
        if method == "one_hot":
            if series.dropna().empty:
                raise ValueError("One-hot encoding requires at least one non-missing value")
            encoded = pd.get_dummies(series, prefix=column, prefix_sep="_", dtype=int)
            collisions = [name for name in encoded.columns if name in df.columns and name != column]
            if collisions:
                raise ValueError(f"One-hot encoded columns already exist: {', '.join(collisions)}")
            return pd.concat([new_df.drop(columns=[column]), encoded], axis=1)

        if method == "ordinal":
            if series.dropna().empty:
                raise ValueError("Ordinal encoding requires at least one non-missing value")
            raw_order = str(params.get("order", "")).strip()
            if raw_order:
                order = [parse_scalar(value) for value in raw_order.split(",")]
                if len(set(order)) != len(order):
                    raise ValueError("Ordinal category order cannot contain duplicates")
            else:
                order = sorted(series.dropna().unique().tolist(), key=lambda value: (type(value).__name__, str(value)))
            unknown = series.dropna()[~series.dropna().isin(order)].unique().tolist()
            if unknown:
                raise ValueError("Ordinal category order must include every non-missing value")
            new_df[column] = series.map({value: index for index, value in enumerate(order)}).astype("Int64")
            return new_df

        if not is_numeric_dtype(series) or is_bool_dtype(series):
            raise ValueError(f"{method.replace('_', ' ').title()} transformation requires a numeric column")
        if method == "min_max":
            value_range = series.max() - series.min()
            if pd.isna(value_range) or value_range == 0:
                raise ValueError("Min max transformation requires at least two distinct numeric values")
            new_df[column] = (series - series.min()) / value_range
        else:
            std = series.std(ddof=0)
            if pd.isna(std) or std == 0:
                raise ValueError("Standardization requires at least two distinct numeric values")
            new_df[column] = (series - series.mean()) / std
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
    if operation_type == "transform_column":
        method = str(params.get("method", "")).replace("_", " ").title()
        return f"Transform {params.get('column', '')}: {method}"
    return operation_type.replace("_", " ").title()
