# Danaleo

Danaleo is a local, browser-based workspace for exploring, cleaning, transforming, and visualizing tabular data.

Your data stays on your machine. Install Danaleo with pip, launch it, and work from the browser without writing setup code.

## Install

Danaleo requires Python 3.10 or newer.

```bash
python -m pip install danaleo
```

## Launch

```bash
danaleo
```

Danaleo opens automatically at:

```text
http://127.0.0.1:8765
```

You can also launch it with:

```bash
python -m danaleo
```

## What You Can Do

- Upload CSV, JSON, Excel, OpenDocument, Parquet, Feather, ORC, Stata, SAS, HDF, and compressed tabular files
- Explore column statistics, missing values, duplicates, correlations, and data previews
- Filter rows, replace values, impute missing data, and drop columns or duplicates
- Apply one-hot encoding, ordinal encoding, min-max scaling, and standardization
- Create branching analysis sessions without losing earlier work
- Merge dataset snapshots with common join types
- Build and save numeric, categorical, grouped, and relationship plots
- Save and restore complete Danaleo workspaces
- Export the analysis workflow as a readable Jupyter notebook

## Common Options

Run without opening a browser:

```bash
danaleo --no-browser
```

Use another port:

```bash
danaleo --port 8766
```

Allow access from another device on your network:

```bash
danaleo --host 0.0.0.0 --port 8765
```

View every available option:

```bash
danaleo --help
```

## Update

```bash
python -m pip install --upgrade danaleo
```

## Uninstall

```bash
python -m pip uninstall danaleo
```

## Install From Source

```bash
git clone https://github.com/RP28/Danaleo-3.0.git
cd Danaleo-3.0
python -m pip install -e .
danaleo
```

## Development

Install development dependencies and run the tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Build the wheel and source distribution:

```bash
./scripts/build_package.sh
```

The release artifacts are written to `dist/`.

## License

Danaleo is available under the MIT License.
