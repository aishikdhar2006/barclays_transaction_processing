// Copyright (c) BankingPlatform, Inc. and affiliates.
//
// This source code is licensed under the BSD license found in the
// LICENSE file in the root directory of this source tree.

const els = {
  version: document.getElementById("version"),
  commandList: document.getElementById("command-list"),
  selectedCommand: document.getElementById("selected-command"),
  selectedDescription: document.getElementById("selected-description"),
  args: document.getElementById("args"),
  runBtn: document.getElementById("run-btn"),
  helpBtn: document.getElementById("help-btn"),
  clearBtn: document.getElementById("clear-btn"),
  statusBadge: document.getElementById("status-badge"),
  invocation: document.getElementById("invocation"),
  output: document.getElementById("output"),
};

let selected = null;

async function loadVersion() {
  try {
    const res = await fetch("/api/version");
    const data = await res.json();
    els.version.textContent = (data.stdout || data.stderr || "").trim();
  } catch (err) {
    els.version.textContent = "version unavailable";
  }
}

async function loadCommands() {
  const res = await fetch("/api/commands");
  const data = await res.json();
  els.commandList.innerHTML = "";
  data.commands.forEach((cmd) => {
    const li = document.createElement("li");
    li.className = "command-item";
    li.dataset.name = cmd.name;
    li.innerHTML = `<span class="name">${cmd.name}</span><span class="sub">${cmd.description}</span>`;
    li.addEventListener("click", () => selectCommand(cmd, li));
    els.commandList.appendChild(li);
  });
}

function selectCommand(cmd, li) {
  selected = cmd;
  document
    .querySelectorAll(".command-item")
    .forEach((el) => el.classList.remove("active"));
  li.classList.add("active");
  els.selectedCommand.textContent = cmd.name;
  els.selectedDescription.textContent = cmd.description;
  els.runBtn.disabled = false;
  els.helpBtn.disabled = false;
}

function setStatus(kind, text) {
  els.statusBadge.className = "badge" + (kind ? " " + kind : "");
  els.statusBadge.textContent = text || "";
}

function renderResult(data) {
  els.invocation.textContent = data.invocation || "";
  const parts = [];
  if (data.stdout) parts.push(data.stdout.replace(/\n$/, ""));
  if (data.stderr) parts.push(data.stderr.replace(/\n$/, ""));
  els.output.textContent = parts.join("\n") || "(no output)";
  if (data.ok) {
    setStatus("ok", "exit " + data.returncode);
  } else {
    setStatus("fail", "exit " + data.returncode);
  }
}

async function runCommand() {
  if (!selected) return;
  setStatus("running", "running…");
  els.output.textContent = "Running…";
  els.runBtn.disabled = true;
  els.helpBtn.disabled = true;
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: selected.name, args: els.args.value }),
    });
    renderResult(await res.json());
  } catch (err) {
    setStatus("fail", "error");
    els.output.textContent = "Request failed: " + err;
  } finally {
    els.runBtn.disabled = false;
    els.helpBtn.disabled = false;
  }
}

async function showHelp() {
  if (!selected) return;
  setStatus("running", "loading…");
  els.output.textContent = "Loading help…";
  try {
    const res = await fetch("/api/help/" + encodeURIComponent(selected.name));
    renderResult(await res.json());
  } catch (err) {
    setStatus("fail", "error");
    els.output.textContent = "Request failed: " + err;
  }
}

function clearOutput() {
  els.output.textContent = "Output will appear here.";
  els.invocation.textContent = "";
  setStatus("", "");
}

els.runBtn.addEventListener("click", runCommand);
els.helpBtn.addEventListener("click", showHelp);
els.clearBtn.addEventListener("click", clearOutput);
els.args.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !els.runBtn.disabled) runCommand();
});

loadVersion();
loadCommands();
