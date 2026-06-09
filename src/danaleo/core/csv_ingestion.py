from __future__ import annotations

import csv
import re
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd


COMMON_DELIMITERS = [",", ";", "\t", "|"]
SEP_DIRECTIVE = re.compile(r"^\s*sep=(.)\s*$", re.IGNORECASE)


def _decode_csv(raw: bytes) -> tuple[str, str]:
    if not raw:
        raise ValueError("The CSV file is empty")

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

    raise ValueError("Could not decode the CSV file using common text encodings")


def _directive(text: str) -> tuple[str | None, int]:
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


def detect_csv_options(raw: bytes) -> dict[str, Any]:
    text, encoding = _decode_csv(raw)
    directive_separator, skiprows = _directive(text)

    if directive_separator:
        delimiter = directive_separator
    else:
        delimiters = list(COMMON_DELIMITERS)
        try:
            sniffed = csv.Sniffer().sniff(text[:65536], delimiters="".join(COMMON_DELIMITERS)).delimiter
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


def read_csv_detected(csv_path: str, parse_info: dict[str, Any] | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = Path(csv_path).read_bytes()
    options = dict(parse_info or detect_csv_options(raw))
    delimiter = str(options.get("delimiter") or ",")
    encoding = str(options.get("encoding") or "utf-8")
    skiprows = int(options.get("skiprows") or 0)

    try:
        df = pd.read_csv(
            csv_path,
            sep=delimiter,
            encoding=encoding,
            skiprows=skiprows,
        )
    except Exception as exc:
        raise ValueError(f"Could not parse CSV: {exc}") from exc

    return df, {
        "delimiter": delimiter,
        "encoding": encoding,
        "skiprows": skiprows,
    }
