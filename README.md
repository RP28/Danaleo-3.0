# Danaleo 3.0

A local-hosted interactive EDA package for CSV files.

The package runs a Python FastAPI server for dataframe operations and a React UI for the workspace. The first phase supports one CSV upload at a time, multiple dataframe sessions, global session operations, local plot filters, saved plots, a session tree, and notebook export.

## What is included

- Upload one CSV file and then hide the upload UI.
- Optional random sampling at upload time for very large files.
- Column list with dtype, missing percentage, and unique count.
- Column stats for numeric and categorical columns.
- Global operations inside the active session:
  - filter rows using `pandas.DataFrame.query`
  - drop a column
  - replace values in a selected column
- Session creation, activation, renaming, and deletion directly inside the session tree node UI. The `+` button still creates a child session immediately; use the pencil icon or double-click the name to rename it.
- A session tree with session and operation nodes using React Flow curved edges.
- Plot builder:
  - numeric: histogram, KDE, box plot, violin plot
  - categorical: top-N bar chart, top-N pie chart
- Local plot query that does not mutate the session dataframe.
- Saved plot cards that remain visible when switching sessions.
- Include/exclude saved plots in the exported notebook.
- Per-plot remarks exported as Markdown cells.
- Notebook export that recreates session copies, operations, and selected plots.

## Project layout

```text
danaleo-3.0/
├── pyproject.toml
├── README.md
├── scripts/
│   └── bootstrap_mac.sh
├── src/danaleo/
│   ├── cli.py
│   ├── core/
│   │   ├── exporter.py
│   │   ├── operations.py
│   │   ├── plots.py
│   │   ├── session_store.py
│   │   └── stats.py
│   └── server/
│       ├── app.py
│       ├── models.py
│       └── static/
└── frontend/
    ├── package.json
    ├── index.html
    └── src/
```

## Mac setup

From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
danaleo
```

After the first setup, you normally only need:

```bash
source .venv/bin/activate
danaleo
```

Open the printed URL if your browser does not open automatically.

## Tests

After installing the Python dev dependencies, run the backend and regression tests with:

```bash
python -m pytest
```

The test suite covers CSV upload state, sampling, session create/activate/rename/delete, branch deletion, dataframe operations, column stats, plot previews, saved plots, notebook export, API routes, and a frontend regression check for the tree rename submit/tick button.

Rebuild the packaged frontend after UI changes with:

```bash
cd frontend
npm install
npm run build
```

## Development mode

Run the backend:

```bash
source .venv/bin/activate
danaleo --no-browser
```

Run the frontend dev server in another terminal:

```bash
cd frontend
npm run dev
```

In development, the React app calls `http://127.0.0.1:8765` for API requests.

## Query examples

For a column with spaces, wrap the column name in backticks:

```python
`Age Years` >= 18
```

For a normal column name:

```python
age >= 18 and income > 0
```
