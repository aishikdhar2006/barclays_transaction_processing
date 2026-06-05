# Copyright (c) BankingPlatform, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

"""A small FastAPI server that exposes the banking_tools CLI commands over a web UI.

This is intentionally thin and non-invasive: it shells out to the existing CLI
(`python -m banking_tools.commands ...`) instead of importing internals, so it
never changes the behaviour of the underlying tool. The static single-page UI in
`frontend/static/` talks to the small JSON API defined below.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
REPO_ROOT = HERE.parent

# Commands exposed in the UI, with a short human description for each.
COMMANDS: dict[str, str] = {
    "process": "Validate and process transactions (no settlement).",
    "settle": "Settle previously processed transactions.",
    "process_and_settle": "Process and settle transactions in one step.",
    "batch_process": "Process batch transaction files (SWIFT / ISO 20022 / ACH).",
    "batch_process_and_settle": "Batch process and settle in one step.",
    "sample_transactions": "Sample transactions from a source file.",
    "authenticate": "Authenticate with the banking settlement gateway.",
    "archive": "Archive processed transactions for long-term storage.",
}

# Characters allowed in a single CLI argument.  This rejects shell
# metacharacters (;|&$` etc.) while still accepting paths, flags, numbers,
# and quoted values that shlex.split already unquoted.
_SAFE_ARG_PATTERN: re.Pattern[str] = re.compile(r"^[\w./@:=,+\-\\~]+$")

# How long a single command is allowed to run before we give up, in seconds.
RUN_TIMEOUT_SECONDS = 300

app = FastAPI(title="banking_tools UI", version="1.0.0")


class RunRequest(BaseModel):
    command: str
    args: str = ""


def _sanitize_args(raw: str) -> list[str]:
    """Parse *raw* into a list of CLI tokens and reject unsafe characters.

    We use ``shlex.split`` for correct quoting, then validate each token
    against ``_SAFE_ARG_PATTERN`` to block shell metacharacters.  This keeps
    the subprocess call safe even though the argv ultimately comes from
    user-supplied input.
    """
    parts = shlex.split(raw)
    for part in parts:
        if not _SAFE_ARG_PATTERN.match(part):
            raise ValueError(f"Argument contains disallowed characters: {part!r}")
    return parts


class RunResponse(BaseModel):
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    invocation: str


def _base_argv() -> list[str]:
    return [sys.executable, "-m", "banking_tools.commands"]


def _run_cli(extra_args: list[str]) -> RunResponse:
    # The executable (sys.executable) and module are hard-coded; only the
    # whitelisted command name and sanitised arguments are appended.  We
    # always use shell=False (the default) so no shell expansion occurs.
    argv = _base_argv() + extra_args
    invocation = " ".join(shlex.quote(part) for part in argv)
    try:
        result = subprocess.run(  # noqa: S603
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return RunResponse(
            ok=False,
            returncode=-1,
            stdout="",
            stderr=f"Command timed out after {RUN_TIMEOUT_SECONDS} seconds.",
            invocation=invocation,
        )
    return RunResponse(
        ok=result.returncode == 0,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        invocation=invocation,
    )


@app.get("/api/commands")
def list_commands() -> dict[str, list[dict[str, str]]]:
    return {
        "commands": [
            {"name": name, "description": desc} for name, desc in COMMANDS.items()
        ]
    }


@app.get("/api/version")
def version() -> RunResponse:
    return _run_cli(["--version"])


@app.get("/api/help/{command}")
def command_help(command: str) -> RunResponse:
    if command not in COMMANDS:
        return RunResponse(
            ok=False,
            returncode=2,
            stdout="",
            stderr=f"Unknown command: {command}",
            invocation="",
        )
    return _run_cli([command, "--help"])


@app.post("/api/run")
def run_command(req: RunRequest) -> RunResponse:
    if req.command not in COMMANDS:
        return RunResponse(
            ok=False,
            returncode=2,
            stdout="",
            stderr=f"Unknown command: {req.command}",
            invocation="",
        )
    try:
        extra_args = _sanitize_args(req.args)
    except ValueError as exc:
        return RunResponse(
            ok=False,
            returncode=2,
            stdout="",
            stderr=f"Could not parse arguments: {exc}",
            invocation="",
        )
    return _run_cli([req.command] + extra_args)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static")
