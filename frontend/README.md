<!--
Copyright (c) BankingPlatform, Inc. and affiliates.

This source code is licensed under the BSD license found in the
LICENSE file in the root directory of this source tree.
-->

# banking_tools Web UI

A small, optional web frontend for the `banking_tools` CLI. It lets you run the
CLI commands from a browser and see their output, which is handy for testing and
demos.

It is intentionally **non-invasive**: the backend just shells out to
`python -m banking_tools.commands ...`, so it never changes how the underlying
tool behaves. Nothing outside this `frontend/` directory is modified.

## Architecture

- **Backend** — `server.py`, a thin [FastAPI](https://fastapi.tiangolo.com/)
  app that wraps each CLI command as a JSON endpoint and serves the static UI.
- **Frontend** — `static/index.html`, `static/styles.css`, `static/app.js`:
  a single-page, vanilla HTML/CSS/JS UI (no framework, no build step).

```
frontend/
├── server.py            # FastAPI backend wrapping the CLI
├── requirements.txt     # fastapi, uvicorn
├── static/
│   ├── index.html       # UI markup
│   ├── styles.css       # styling
│   └── app.js           # UI logic (calls the API)
└── README.md
```

## Running it

From the repository root:

```sh
# 1. Make sure banking_tools itself is installed (editable install is fine)
pip install -e .

# 2. Install the UI dependencies
pip install -r frontend/requirements.txt

# 3. Start the server
uvicorn frontend.server:app --host 0.0.0.0 --port 8000
```

If you use `uv`, the equivalent is:

```sh
uv sync --group dev
uv pip install -r frontend/requirements.txt
uv run uvicorn frontend.server:app --host 0.0.0.0 --port 8000
```

Then open <http://localhost:8000> in your browser.

## Using the UI

1. Pick a command from the left-hand list.
2. (Optional) type CLI arguments in the **Arguments** box, exactly as you would
   on the command line, e.g. `tests/data/images --skip_process_errors`.
3. Click **Run** to execute, or **Show --help** to see the command's options.

The output panel shows the exact invocation, combined stdout/stderr, and the
process exit code.

## API

| Method | Path                 | Description                              |
| ------ | -------------------- | ---------------------------------------- |
| GET    | `/api/commands`      | List available commands + descriptions.  |
| GET    | `/api/version`       | Run `--version`.                         |
| GET    | `/api/help/{command}`| Run `<command> --help`.                  |
| POST   | `/api/run`           | Run `<command>` with `args` (JSON body). |

## Extending it (e.g. for C++/Java modules)

The backend simply runs a subprocess, so adding support for other executables
(a compiled C++ binary, a Java jar, etc.) is just a matter of adding an entry to
the `COMMANDS` map and pointing the invocation at the relevant program.
