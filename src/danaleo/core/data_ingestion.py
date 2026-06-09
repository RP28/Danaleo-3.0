from __future__ import annotations

import bz2
import csv
import gzip
import lzma
import re
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

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

SUPPORTED_DATA_EXTENSIONS = tuple(FORMAT_BY_SUFFIX)
COMMON_DELIMITERS = [",", ";", "\t", "|"]
SEP_DIRECTIVE = re.compile(r"^\s*sep=(.)\s*$", re.IGNORECASE)


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
    raw = _decompress_for_detection(path, Path(path).read_bytes())
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


def source_format(filename: str) -> str:
    suffix = _matching_suffix(filename)
    if suffix is None:
        supported = ", ".join(SUPPORTED_DATA_EXTENSIONS)
        raise ValueError(f"Unsupported data file type. Supported extensions: {supported}")
    return FORMAT_BY_SUFFIX[suffix]


def is_supported_data_filename(filename: str | None) -> bool:
    return bool(filename and _matching_suffix(filename))


def _first_excel_sheet(path: str) -> str:
    workbook = pd.ExcelFile(path)
    if not workbook.sheet_names:
        raise ValueError("The spreadsheet does not contain any sheets")
    return str(workbook.sheet_names[0])


def _first_hdf_key(path: str) -> str:
    with pd.HDFStore(path, mode="r") as store:
        keys = store.keys()
    if not keys:
        raise ValueError("The HDF file does not contain any tables")
    return str(keys[0])


def _unique_column_names(columns) -> list[str]:
    names: list[str] = []
    used: set[str] = set()
    for index, column in enumerate(columns):
        base = str(column).strip() or f"Unnamed: {index}"
        name = base
        suffix = 1
        while name in used:
            name = f"{base}.{suffix}"
            suffix += 1
        names.append(name)
        used.add(name)
    return names


def _finalize(
    df: pd.DataFrame,
    format_name: str,
    parse_info: dict[str, Any],
    expected_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    original_columns = list(df.columns)
    columns = expected_columns if expected_columns and len(expected_columns) == len(df.columns) else _unique_column_names(df.columns)
    df.columns = columns
    finalized_parse_info = dict(parse_info)
    if expected_columns or columns != original_columns:
        finalized_parse_info["column_names"] = columns
    return df, format_name, finalized_parse_info


def read_data_file(
    path: str,
    filename: str,
    parse_info: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    format_name = source_format(filename)
    options = dict(parse_info or {})

    try:
        if format_name == "delimited":
            df, detected = _read_delimited_file(path, options or None)
            return _finalize(df, format_name, detected, options.get("column_names"))

        if format_name in {"json", "jsonl"}:
            lines = bool(options.get("lines", format_name == "jsonl"))
            try:
                df = pd.read_json(path, lines=lines)
            except ValueError:
                if parse_info or format_name == "jsonl":
                    raise
                lines = True
                df = pd.read_json(path, lines=True)
            return _finalize(df, format_name, {"lines": lines}, options.get("column_names"))

        if format_name == "excel":
            sheet_name = options.get("sheet_name")
            if sheet_name is None:
                sheet_name = _first_excel_sheet(path)
            df = pd.read_excel(path, sheet_name=sheet_name)
            return _finalize(df, format_name, {"sheet_name": sheet_name}, options.get("column_names"))

        if format_name == "parquet":
            return _finalize(pd.read_parquet(path), format_name, {}, options.get("column_names"))
        if format_name == "feather":
            return _finalize(pd.read_feather(path), format_name, {}, options.get("column_names"))
        if format_name == "orc":
            return _finalize(pd.read_orc(path), format_name, {}, options.get("column_names"))
        if format_name == "stata":
            return _finalize(pd.read_stata(path), format_name, {}, options.get("column_names"))
        if format_name == "sas":
            return _finalize(pd.read_sas(path), format_name, {}, options.get("column_names"))
        if format_name == "hdf":
            key = str(options.get("key") or _first_hdf_key(path))
            return _finalize(
                pd.read_hdf(path, key=key),
                format_name,
                {"key": key},
                options.get("column_names"),
            )
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
        return f"{variable} = pd.read_json({filename!r}, lines={lines!r})"
    if format_name == "excel":
        return f"{variable} = pd.read_excel({filename!r}, sheet_name={options.get('sheet_name')!r})"
    if format_name == "parquet":
        return f"{variable} = pd.read_parquet({filename!r})"
    if format_name == "feather":
        return f"{variable} = pd.read_feather({filename!r})"
    if format_name == "orc":
        return f"{variable} = pd.read_orc({filename!r})"
    if format_name == "stata":
        return f"{variable} = pd.read_stata({filename!r})"
    if format_name == "sas":
        return f"{variable} = pd.read_sas({filename!r})"
    if format_name == "hdf":
        return f"{variable} = pd.read_hdf({filename!r}, key={options.get('key')!r})"
    raise ValueError(f"Unsupported data format: {format_name}")
