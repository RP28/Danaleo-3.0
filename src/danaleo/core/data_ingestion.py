from __future__ import annotations

import bz2
import csv
import gzip
import json
import lzma
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import numpy as np
import pandas as pd


FORMAT_BY_SUFFIX = {
    ".csv": "delimited",
    ".tsv": "delimited",
    ".tab": "delimited",
    ".txt": "delimited",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".xlsx": "excel",
    ".xls": "excel",
    ".xlsm": "excel",
    ".xlsb": "excel",
    ".ods": "excel",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".feather": "feather",
    ".arrow": "feather",
    ".orc": "orc",
    ".dta": "stata",
    ".sas7bdat": "sas",
    ".xpt": "sas",
    ".h5": "hdf",
    ".hdf": "hdf",
    ".hdf5": "hdf",
}

for compression_suffix in (".gz", ".bz2", ".xz", ".zip"):
    for data_suffix, format_name in [
        (".csv", "delimited"),
        (".tsv", "delimited"),
        (".tab", "delimited"),
        (".txt", "delimited"),
        (".json", "json"),
        (".jsonl", "jsonl"),
        (".ndjson", "jsonl"),
    ]:
        FORMAT_BY_SUFFIX[f"{data_suffix}{compression_suffix}"] = format_name
for compression_suffix in (".gz", ".bz2", ".xz"):
    FORMAT_BY_SUFFIX[f".dta{compression_suffix}"] = "stata"
    FORMAT_BY_SUFFIX[f".sas7bdat{compression_suffix}"] = "sas"
    FORMAT_BY_SUFFIX[f".xpt{compression_suffix}"] = "sas"

SUPPORTED_DATA_EXTENSIONS = tuple(FORMAT_BY_SUFFIX)
COMMON_DELIMITERS = [",", ";", "\t", "|"]
SEP_DIRECTIVE = re.compile(r"^\s*sep=(.)\s*$", re.IGNORECASE)
JSON_RECORD_KEYS = ("data", "records", "items", "results", "rows", "values")


def _decompress_for_detection(path: str, raw: bytes) -> bytes:
    suffix = Path(path).suffix.lower()
    if suffix == ".gz":
        return gzip.decompress(raw)
    if suffix == ".bz2":
        return bz2.decompress(raw)
    if suffix == ".xz":
        return lzma.decompress(raw)
    if suffix == ".zip":
        with ZipFile(path) as archive:
            files = [name for name in archive.namelist() if not name.endswith("/")]
            if len(files) != 1:
                raise ValueError("Compressed data archives must contain exactly one file")
            return archive.read(files[0])
    return raw


def _decode_delimited_text(raw: bytes) -> tuple[str, str]:
    if not raw:
        raise ValueError("The data file is empty")

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"

    encodings = ["utf-8", "cp1252", "latin-1"]
    if b"\x00" in raw[:4096]:
        encodings = ["utf-16-le", "utf-16-be", *encodings]

    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" not in text:
            return text, encoding

    raise ValueError("Could not decode the data file using common text encodings")


def _read_source_bytes(path: str) -> bytes:
    return _decompress_for_detection(path, Path(path).read_bytes())


def _separator_directive(text: str) -> tuple[str | None, int]:
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        match = SEP_DIRECTIVE.match(line)
        return (match.group(1), index + 1) if match else (None, 0)
    return None, 0


def _delimiter_score(text: str, delimiter: str, skiprows: int) -> tuple[float, int] | None:
    reader = csv.reader(StringIO(text), delimiter=delimiter, strict=True)
    widths: list[int] = []
    try:
        for index, row in enumerate(reader):
            if index < skiprows or not row:
                continue
            widths.append(len(row))
            if len(widths) >= 80:
                break
    except csv.Error:
        return None

    if not widths:
        return None
    modal_width, modal_count = Counter(widths).most_common(1)[0]
    if modal_width < 2:
        return None
    consistency = modal_count / len(widths)
    if consistency < 0.8:
        return None
    return consistency, modal_width


def _detect_delimited_options(raw: bytes) -> dict[str, Any]:
    text, encoding = _decode_delimited_text(raw)
    directive_separator, skiprows = _separator_directive(text)

    if directive_separator:
        delimiter = directive_separator
    else:
        delimiters = list(COMMON_DELIMITERS)
        try:
            sniffed = csv.Sniffer().sniff(
                text[:65536],
                delimiters="".join(COMMON_DELIMITERS),
            ).delimiter
            delimiters.remove(sniffed)
            delimiters.insert(0, sniffed)
        except csv.Error:
            pass

        scored = [
            (score, -index, delimiter)
            for index, delimiter in enumerate(delimiters)
            if (score := _delimiter_score(text, delimiter, skiprows)) is not None
        ]
        if scored:
            delimiter = max(scored)[2]
        else:
            first_line = next((line for line in text.splitlines()[skiprows:] if line.strip()), "")
            delimiter = max(COMMON_DELIMITERS, key=first_line.count)
            if first_line.count(delimiter) == 0:
                delimiter = ","

    return {
        "delimiter": delimiter,
        "encoding": encoding,
        "skiprows": skiprows,
    }


def _read_delimited_file(
    path: str,
    parse_info: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = _read_source_bytes(path)
    options = dict(parse_info or _detect_delimited_options(raw))
    delimiter = str(options.get("delimiter") or ",")
    encoding = str(options.get("encoding") or "utf-8")
    skiprows = int(options.get("skiprows") or 0)

    try:
        df = pd.read_csv(path, sep=delimiter, encoding=encoding, skiprows=skiprows)
    except Exception as exc:
        raise ValueError(f"Could not parse delimited data file: {exc}") from exc

    return df, {
        "delimiter": delimiter,
        "encoding": encoding,
        "skiprows": skiprows,
    }


def _matching_suffix(filename: str) -> str | None:
    lower_name = filename.lower()
    return next(
        (suffix for suffix in sorted(FORMAT_BY_SUFFIX, key=len, reverse=True) if lower_name.endswith(suffix)),
        None,
    )


def _detected_source_format(path: str, filename: str) -> str:
    declared = source_format(filename)
    with open(path, "rb") as source:
        head = source.read(8)
        source.seek(0, 2)
        size = source.tell()
        source.seek(max(0, size - 8))
        tail = source.read(8)
    if head.startswith(b"PAR1") and tail.endswith(b"PAR1"):
        return "parquet"
    if head.startswith(b"ARROW1"):
        return "feather"
    if head.startswith(b"ORC"):
        return "orc"
    if head.startswith(b"\x89HDF"):
        return "hdf"
    if head.startswith(b"PK"):
        try:
            with ZipFile(path) as archive:
                names = set(archive.namelist())
            if "xl/workbook.xml" in names or "content.xml" in names:
                return "excel"
        except Exception:
            return declared
    if declared == "delimited":
        try:
            text, _ = _decode_delimited_text(_read_source_bytes(path))
            stripped = text.lstrip()
            if stripped.startswith(("{", "[")):
                try:
                    json.loads(stripped)
                    return "json"
                except json.JSONDecodeError:
                    records = [json.loads(line) for line in text.splitlines() if line.strip()]
                    if records:
                        return "jsonl"
        except Exception:
            pass
    return declared


def source_format(filename: str) -> str:
    suffix = _matching_suffix(filename)
    if suffix is None:
        supported = ", ".join(SUPPORTED_DATA_EXTENSIONS)
        raise ValueError(f"Unsupported data file type. Supported extensions: {supported}")
    return FORMAT_BY_SUFFIX[suffix]


def is_supported_data_filename(filename: str | None) -> bool:
    return bool(filename and _matching_suffix(filename))


def _hdf_keys(path: str) -> list[str]:
    with pd.HDFStore(path, mode="r") as store:
        keys = store.keys()
    if not keys:
        raise ValueError("The HDF file does not contain any tables")
    return [str(key) for key in keys]


def _unique_column_names(columns) -> list[str]:
    names: list[str] = []
    used: set[str] = set()
    for index, column in enumerate(columns):
        base = str(_decode_bytes(column)).strip() or f"Unnamed: {index}"
        name = base
        suffix = 1
        while name in used:
            name = f"{base}.{suffix}"
            suffix += 1
        names.append(name)
        used.add(name)
    return names


def _decode_bytes(value: Any) -> Any:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if not isinstance(value, (bytes, bytearray)):
        return value
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return bytes(value).decode(encoding)
        except UnicodeDecodeError:
            continue
    return bytes(value).hex()


def _safe_cell(value: Any) -> Any:
    value = _decode_bytes(value)
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=isinstance(value, dict))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool, date, datetime, pd.Timestamp, pd.Timedelta)):
        return value
    return str(value)


def _clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str] | None]:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("The selected data does not contain a table")
    df.columns = _unique_column_names(df.columns)
    default_index = df.index.name is None and df.index.equals(pd.RangeIndex(len(df)))
    index_names: list[str] | None = None
    if not default_index:
        used = {str(column) for column in df.columns}
        if isinstance(df.index, pd.MultiIndex):
            raw_names = [
                str(name).strip() if name is not None and str(name).strip() else f"index_{position}"
                for position, name in enumerate(df.index.names)
            ]
        else:
            raw_names = [str(df.index.name).strip() if df.index.name is not None else "index"]
        index_names = []
        for raw_name in raw_names:
            name = raw_name
            suffix = 1
            while name in used:
                name = f"{raw_name}.{suffix}"
                suffix += 1
            used.add(name)
            index_names.append(name)
        df.index.names = index_names
        df = df.reset_index()
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all").reset_index(drop=True)
    for column in df.columns:
        series = df[column]
        if series.dtype == "object":
            df[column] = series.map(_safe_cell, na_action="ignore")
    if len(df.columns) == 0:
        raise ValueError("The selected data table does not contain any columns")
    return df, index_names


def _finalize(
    df: pd.DataFrame,
    format_name: str,
    parse_info: dict[str, Any],
    expected_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    original_columns = list(df.columns)
    df, index_names = _clean_dataframe(df)
    columns = expected_columns if expected_columns and len(expected_columns) == len(df.columns) else list(df.columns)
    df.columns = columns
    finalized_parse_info = dict(parse_info)
    if expected_columns or columns != original_columns:
        finalized_parse_info["column_names"] = columns
    if index_names:
        finalized_parse_info["index_names"] = index_names
    return df, format_name, finalized_parse_info


def _json_to_dataframe(payload: Any) -> tuple[pd.DataFrame, str | None, str]:
    if isinstance(payload, list):
        if not payload:
            raise ValueError("The JSON array is empty")
        if not any(isinstance(item, (dict, list)) for item in payload):
            return pd.DataFrame({"value": payload}), None, "value_list"
        return pd.json_normalize(payload), None, "normalize"

    if isinstance(payload, dict):
        if (
            isinstance(payload.get("columns"), list)
            and isinstance(payload.get("data"), list)
            and all(isinstance(row, list) for row in payload["data"])
        ):
            frame = pd.DataFrame(
                payload["data"],
                columns=payload["columns"],
                index=payload.get("index"),
            )
            return frame, None, "split"

        for key in JSON_RECORD_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                if not value:
                    continue
                return pd.json_normalize(value), key, "normalize"

        if payload and all(isinstance(value, list) for value in payload.values()):
            lengths = {len(value) for value in payload.values()}
            if len(lengths) == 1:
                return pd.DataFrame(payload), None, "columns"

        list_candidates = [
            (key, value)
            for key, value in payload.items()
            if isinstance(value, list) and value
        ]
        if len(list_candidates) == 1:
            key, value = list_candidates[0]
            return pd.json_normalize(value), str(key), "normalize"

        if payload and all(isinstance(value, dict) for value in payload.values()):
            return (
                pd.DataFrame.from_dict(payload, orient="index").reset_index(names="index"),
                None,
                "dict_index",
            )
        return pd.json_normalize(payload), None, "normalize"

    raise ValueError("JSON must contain an object, an array of records, or JSON Lines")


def _read_json_file(
    path: str,
    format_name: str,
    options: dict[str, Any],
    restoring: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    text, encoding = _decode_delimited_text(_read_source_bytes(path))
    lines = bool(options.get("lines", format_name == "jsonl"))
    record_path = options.get("record_path")

    if lines:
        records = [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]
        return pd.json_normalize(records), {
            "lines": True,
            "encoding": encoding,
            "json_mode": "normalize",
        }

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if restoring:
            raise
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        return pd.json_normalize(records), {
            "lines": True,
            "encoding": encoding,
            "json_mode": "normalize",
        }

    if record_path is not None:
        if not isinstance(payload, dict) or record_path not in payload:
            raise ValueError(f"JSON record path not found: {record_path}")
        df = pd.json_normalize(payload[record_path])
        return df, {
            "lines": False,
            "encoding": encoding,
            "record_path": record_path,
            "json_mode": str(options.get("json_mode") or "normalize"),
        }

    df, detected_record_path, json_mode = _json_to_dataframe(payload)
    parse_info: dict[str, Any] = {
        "lines": False,
        "encoding": encoding,
        "json_mode": json_mode,
    }
    if detected_record_path is not None:
        parse_info["record_path"] = detected_record_path
    return df, parse_info


def _excel_header_score(frame: pd.DataFrame, row_index: int) -> tuple[int, int, int, int]:
    values = [value for value in frame.iloc[row_index].tolist() if pd.notna(value)]
    if not values:
        return (0, 0, 0, -row_index)
    names = [str(value).strip() for value in values]
    unique = len(set(names))
    text_values = sum(isinstance(value, str) for value in values)
    return (text_values, -row_index, unique, len(values))


def _read_excel_file(
    path: str,
    options: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    workbook = pd.ExcelFile(path)
    if not workbook.sheet_names:
        raise ValueError("The spreadsheet does not contain any sheets")

    if options.get("sheet_name") is not None:
        sheet_names = [options["sheet_name"]]
    else:
        sheet_names = workbook.sheet_names

    candidates: list[tuple[int, int, str, int, pd.DataFrame]] = []
    for sheet_name in sheet_names:
        try:
            raw = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=40)
        except Exception:
            if options.get("sheet_name") is not None:
                raise
            continue
        raw = raw.dropna(axis=1, how="all")
        non_empty_rows = [index for index in range(len(raw)) if raw.iloc[index].notna().any()]
        if not non_empty_rows:
            continue
        if options.get("header_row") is not None:
            header_row = int(options["header_row"])
        else:
            max_width = max(int(raw.iloc[index].notna().sum()) for index in non_empty_rows)
            minimum_width = min(max_width, max(2, (max_width + 1) // 2))
            plausible_rows = [
                index
                for index in non_empty_rows
                if int(raw.iloc[index].notna().sum()) >= minimum_width
            ]
            header_row = max(plausible_rows, key=lambda index: _excel_header_score(raw, index))
        try:
            frame = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
        except Exception:
            if options.get("sheet_name") is not None:
                raise
            continue
        frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
        if frame.empty or len(frame.columns) == 0:
            continue
        candidates.append((len(frame), len(frame.columns), str(sheet_name), header_row, frame))

    if not candidates:
        raise ValueError("The spreadsheet does not contain a non-empty table")
    _, _, sheet_name, header_row, df = max(candidates, key=lambda item: (item[0], item[1]))
    return df, {"sheet_name": sheet_name, "header_row": header_row}


def _read_hdf_file(path: str, options: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    if options.get("key"):
        key = str(options["key"])
        return pd.read_hdf(path, key=key), {"key": key}

    candidates: list[tuple[int, int, str, pd.DataFrame]] = []
    for key in _hdf_keys(path):
        try:
            value = pd.read_hdf(path, key=key)
        except Exception:
            continue
        if isinstance(value, pd.DataFrame):
            candidates.append((len(value), len(value.columns), key, value))
        elif isinstance(value, pd.Series):
            frame = value.to_frame()
            candidates.append((len(frame), len(frame.columns), key, frame))
    if not candidates:
        raise ValueError("The HDF file does not contain a readable table")
    _, _, key, df = max(candidates, key=lambda item: (item[0], item[1]))
    return df, {"key": key}


def read_data_file(
    path: str,
    filename: str,
    parse_info: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    format_name = _detected_source_format(path, filename)
    options = dict(parse_info or {})

    try:
        if format_name == "delimited":
            df, detected = _read_delimited_file(path, options or None)
            return _finalize(df, format_name, detected, options.get("column_names"))

        if format_name in {"json", "jsonl"}:
            df, detected = _read_json_file(path, format_name, options, parse_info is not None)
            return _finalize(df, format_name, detected, options.get("column_names"))

        if format_name == "excel":
            df, detected = _read_excel_file(path, options)
            return _finalize(df, format_name, detected, options.get("column_names"))

        if format_name == "parquet":
            return _finalize(pd.read_parquet(path), format_name, {}, options.get("column_names"))
        if format_name == "feather":
            return _finalize(pd.read_feather(path), format_name, {}, options.get("column_names"))
        if format_name == "orc":
            return _finalize(pd.read_orc(path), format_name, {}, options.get("column_names"))
        if format_name == "stata":
            return _finalize(pd.read_stata(path), format_name, {}, options.get("column_names"))
        if format_name == "sas":
            encoding = options.get("encoding")
            df = pd.read_sas(path, encoding=encoding)
            detected = {"encoding": encoding} if encoding else {}
            return _finalize(df, format_name, detected, options.get("column_names"))
        if format_name == "hdf":
            df, detected = _read_hdf_file(path, options)
            return _finalize(df, format_name, detected, options.get("column_names"))
    except ImportError as exc:
        raise ValueError(
            f"Reading {Path(filename).suffix} files requires its data-format dependency"
        ) from exc
    except Exception as exc:
        raise ValueError(f"Could not parse {Path(filename).suffix or 'data'} file: {exc}") from exc

    raise ValueError(f"Unsupported data format: {format_name}")


def notebook_read_expression(
    variable: str,
    filename: str,
    format_name: str,
    parse_info: dict[str, Any] | None,
) -> str:
    options = parse_info or {}
    if format_name == "delimited":
        arguments: list[str] = []
        if options.get("delimiter", ",") != ",":
            arguments.append(f"sep={options['delimiter']!r}")
        if options.get("encoding", "utf-8") != "utf-8":
            arguments.append(f"encoding={options['encoding']!r}")
        if options.get("skiprows"):
            arguments.append(f"skiprows={options['skiprows']!r}")
        extra = ", " + ", ".join(arguments) if arguments else ""
        return f"{variable} = pd.read_csv({filename!r}{extra})"
    if format_name in {"json", "jsonl"}:
        lines = bool(options.get("lines", format_name == "jsonl"))
        encoding = str(options.get("encoding") or "utf-8")
        if lines:
            return f"{variable} = pd.read_json({filename!r}, lines=True, encoding={encoding!r})"
        payload = _notebook_json_payload(filename, encoding)
        if options.get("record_path") is not None:
            payload += f"[{options['record_path']!r}]"
        if options.get("json_mode") == "dict_index":
            return f"{variable} = pd.DataFrame.from_dict({payload}, orient='index').reset_index(names='index')"
        if options.get("json_mode") == "value_list":
            return f"{variable} = pd.DataFrame({{'value': {payload}}})"
        if options.get("json_mode") == "columns":
            return f"{variable} = pd.DataFrame({payload})"
        if options.get("json_mode") == "split":
            return (
                f"{variable}_payload = {payload}\n"
                f"{variable} = pd.DataFrame({variable}_payload['data'], "
                f"columns={variable}_payload['columns'], index={variable}_payload.get('index'))"
            )
        return f"{variable} = pd.json_normalize({payload})"
    if format_name == "excel":
        return (
            f"{variable} = pd.read_excel({filename!r}, "
            f"sheet_name={options.get('sheet_name')!r}, header={options.get('header_row', 0)!r})"
        )
    if format_name == "parquet":
        return f"{variable} = pd.read_parquet({filename!r})"
    if format_name == "feather":
        return f"{variable} = pd.read_feather({filename!r})"
    if format_name == "orc":
        return f"{variable} = pd.read_orc({filename!r})"
    if format_name == "stata":
        return f"{variable} = pd.read_stata({filename!r})"
    if format_name == "sas":
        encoding = options.get("encoding")
        suffix = f", encoding={encoding!r}" if encoding else ""
        return f"{variable} = pd.read_sas({filename!r}{suffix})"
    if format_name == "hdf":
        return f"{variable} = pd.read_hdf({filename!r}, key={options.get('key')!r})"
    raise ValueError(f"Unsupported data format: {format_name}")


def _notebook_json_payload(filename: str, encoding: str) -> str:
    lower_name = filename.lower()
    if lower_name.endswith(".gz"):
        stream = f"__import__('gzip').open({filename!r}, 'rt', encoding={encoding!r})"
        return f"__import__('json').load({stream})"
    if lower_name.endswith(".bz2"):
        stream = f"__import__('bz2').open({filename!r}, 'rt', encoding={encoding!r})"
        return f"__import__('json').load({stream})"
    if lower_name.endswith(".xz"):
        stream = f"__import__('lzma').open({filename!r}, 'rt', encoding={encoding!r})"
        return f"__import__('json').load({stream})"
    if lower_name.endswith(".zip"):
        archive = f"__import__('zipfile').ZipFile({filename!r})"
        raw = f"{archive}.read({archive}.namelist()[0]).decode({encoding!r})"
        return f"__import__('json').loads({raw})"
    stream = f"open({filename!r}, encoding={encoding!r})"
    return f"__import__('json').load({stream})"
