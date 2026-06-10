# Danaleo 3.0

Danaleo is a local interactive EDA workspace for tabular data files.

It runs a Python FastAPI backend and a React UI on localhost. You can upload multiple data files into separate dataset tabs, inspect columns, create dataframe sessions, apply operations, build plots, save plots with notes, view session history as a tree, and export the active analysis as a Jupyter notebook.

## Features

* Upload multiple tabular data files into independent dataset tabs
* Save and restore every open data file, session, and plot in one `.danaleo` workspace
* Visually merge two dataset session snapshots with inner, left, right, full outer, or cross joins
* Preview merge match diagnostics and validate one-to-one, one-to-many, or many-to-one relationships
* Optional sampling during upload
* Column overview and column-level statistics
* Overview-first dataset profile with quality flags, correlations, and row preview
* Dataframe sessions and branching
* Session tree with operation history
* Rename, activate, and delete sessions
* Filter rows using pandas-style queries
* Drop columns
* Automatically detect common CSV separators and text encodings
* Read JSON/JSON Lines, Excel/OpenDocument, Parquet, Feather, ORC, Stata, SAS, and HDF files
* Open compressed delimited-text and JSON files (`.gz`, `.bz2`, `.xz`, and single-file `.zip`)
* Drop missing values
* Drop exact duplicate rows
* Replace values with custom values, missing values, mean, median, or mode
* Impute missing values
* One-hot and ordinal encoding
* Min-max scaling and standardization
* Plot numeric and categorical columns
* Top-N plots for categorical and numeric columns
* Grouped plots
* Multi-column subplot-style plotting
* Scatter, hexbin, line relationship, correlation heatmap, and missing-values plots
* Shared chart title, grid, log-axis, sorting, orientation, marker, and opacity controls
* Save plots with export notes
* Include or skip saved plots across every dataset tab during notebook export
* Export EDA workflow to `.ipynb`
* Exported notebooks use concise pandas, NumPy, Matplotlib, and Seaborn code without requiring Danaleo
* Exported merged datasets recreate available join chains with direct `pd.merge(...)` code
* Local browser-based UI

## Requirements

* Python 3.10+
* Node.js/npm only if the frontend UI needs to be rebuilt from source

For normal Python usage, install the package with pip. For frontend development, Node.js/npm is required.

## Setup

After publishing a release to PyPI, install it with:

```bash
python3 -m pip install danaleo
danaleo
```

To install from a cloned repository:

```bash
git clone https://github.com/RP28/Danaleo-3.0.git
cd Danaleo-3.0
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Danaleo and Python dependencies:

```bash
python3 -m pip install -e .
```

For development and tests:

```bash
python3 -m pip install -e ".[dev]"
```

## Run

Start Danaleo with:

```bash
python3 -m danaleo
```

Or use the installed CLI command:

```bash
danaleo
```

Then open:

```text
http://127.0.0.1:8765
```

The browser should open automatically. If it does not, copy the printed URL into your browser.

## Useful startup commands

Run without opening the browser:

```bash
danaleo --no-browser
```

Run on another port:

```bash
danaleo --port 8766
```

Use a different host:

```bash
danaleo --host 0.0.0.0 --port 8765
```

Force rebuild the frontend before starting:

```bash
danaleo --build-ui
```

Only build the frontend and exit:

```bash
danaleo --build-ui-only
```

Build the frontend without running `npm install` or `npm ci`:

```bash
danaleo --build-ui-only --skip-npm-install
```

Start without automatically building the UI if static files are missing:

```bash
danaleo --no-build-ui
```

Skip Python dependency checks:

```bash
danaleo --no-check-env
```

## If the port is already in use

Use another port:

```bash
danaleo --port 8766
```

Or stop the old process on macOS/Linux:

```bash
kill -9 $(lsof -ti :8765)
```

## Frontend build

The React frontend lives in:

```text
frontend/
```

The production build is written into:

```text
src/danaleo/server/static/
```

To rebuild manually:

```bash
cd frontend
npm install
npm run build
cd ..
```

The startup script can also build the frontend automatically when the static UI is missing, as long as Node.js/npm is available.

Generated frontend build files such as the following are committed and included in the Python package:

```text
src/danaleo/server/static/index.html
src/danaleo/server/static/assets/index-*.js
src/danaleo/server/static/assets/index-*.css
```

Regenerate them after frontend changes with:

```bash
cd frontend
npm run build
```

Keeping these assets in the repository ensures `pip install` from a clean checkout includes a usable UI without requiring Node.js on the end user's machine.

## Development workflow

Install Python dev dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

Run the backend/local app:

```bash
danaleo --no-browser
```

Run the frontend dev server in another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server is useful when actively editing React components.

## Tests

Run all tests:

```bash
python3 -m pytest
```

Run with verbose output:

```bash
python3 -m pytest -vv
```

Save test output to a log file:

```bash
python3 -m pytest -vv 2>&1 | tee pytest.log
```

## Query examples

For normal column names:

```python
age >= 18 and income > 0
```

For column names with spaces:

```python
`Age Years` >= 18
```

For string values:

```python
city == "Sydney"
```

For missing-value checks, use pandas query syntax where applicable, or use the built-in drop-missing operation from the UI.

## Notebook export

Use the export option in the UI to download a Jupyter notebook.

The exported notebook attempts to recreate the EDA workflow, including:

* Tabular data-file loading
* Sampling
* Session creation
* Session operations
* Saved plots selected for export
* Plot notes and remarks

## Python entry point

Danaleo can also be started from Python:

```python
from danaleo.main import start

start()
```

Example with custom options:

```python
from danaleo.main import start

start(
    host="127.0.0.1",
    port=8766,
    open_browser=False,
    build_ui=True,
)
```

## Package notes

The Python package supports both command-line entry points:

```bash
danaleo
python3 -m danaleo
```

The wheel includes the built static frontend files under:

```text
src/danaleo/server/static/
```

Install release tooling and build the distributable wheel and source archive:

```bash
python3 -m pip install -e ".[dev]"
./scripts/build_package.sh
```

The script rebuilds the React UI, creates both distributions in `dist/`, and validates their metadata with Twine.

## Project structure

```text
Danaleo-3.0/
├── frontend/                    # React UI
├── src/
│   └── danaleo/
│       ├── core/                # EDA logic, sessions, plots, exporter
│       ├── server/              # FastAPI app and static UI serving
│       └── main.py              # CLI/startup entry point
├── tests/                       # pytest test suite
├── pyproject.toml               # Python packaging config
└── README.md
```
