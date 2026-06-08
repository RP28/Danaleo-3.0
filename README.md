# Danaleo 3.0

A local interactive EDA workspace for CSV files.

Danaleo runs a Python FastAPI backend and a React UI on localhost. It supports CSV upload, column statistics, dataframe sessions, filters, column operations, plots, saved plots, a session tree, and notebook export.

## Requirements

* Python 3.10+
* Node.js/npm only if the UI needs to be rebuilt

## Setup

Clone the repo:

```bash
git clone https://github.com/RP28/Danaleo-3.0.git
cd Danaleo-3.0
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Danaleo and all Python dependencies:

```bash
python3 -m pip install -e .
```

## Run

Start Danaleo with:

```bash
python3 -m danaleo.main
```

Or use the installed CLI command:

```bash
danaleo
```

Then open:

```text
http://127.0.0.1:8765
```

If the browser does not open automatically, copy the printed URL into your browser.

## If the port is already in use

Run on another port:

```bash
danaleo --port 8766
```

Or stop the old process:

```bash
kill -9 $(lsof -ti :8765)
```

## Rebuild the UI

Normally, users should not need to do this.

Only run this after changing frontend code or if the static UI is missing:

```bash
cd frontend
npm install
npm run build
cd ..
```

The UI build is written into:

```text
src/danaleo/server/static/
```

## Development

Run backend only:

```bash
danaleo --no-browser
```

For frontend development, run the React dev server in another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Tests

Install dev dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

Run tests:

```bash
python3 -m pytest
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
