"""Web and phone interface: chat with Jarvis in a browser, with streaming replies, approvals and voice.

Voice uses the browser's own speech recognition and speech synthesis (Web Speech API), so a phone
works as a microphone and speaker with nothing installed. Every request needs the secret token
printed at start-up; the server listens on localhost unless told otherwise.
"""

from __future__ import annotations

import hmac
import json
import queue
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import anthropic

from .agent import Jarvis

APPROVAL_TIMEOUT_S = 300
MAX_BODY = 64_000


class WebSession:
    """Runs one Jarvis turn at a time and turns its callbacks into a stream of JSON events."""

    def __init__(self, jarvis: Jarvis, auto_approve: bool = False) -> None:
        self.jarvis = jarvis
        self.auto_approve = auto_approve
        self.lock = threading.Lock()
        self.events: queue.Queue[dict[str, Any] | None] | None = None
        self.pending: dict[str, tuple[threading.Event, list[bool]]] = {}
        jarvis.ctx.approve = self.approve_tool
        jarvis.ctx.confirm_private = self.confirm_private
        jarvis.on_delta = lambda text: self._emit({"type": "delta", "text": text})
        jarvis.on_text = lambda text: self._emit({"type": "block_end"})
        jarvis.on_tool = lambda line: self._emit({"type": "tool", "line": line})

    def _emit(self, event: dict[str, Any]) -> None:
        if self.events is not None:
            self.events.put(event)

    def _ask(self, question: str) -> bool:
        if self.events is None:
            return False
        approval_id = uuid.uuid4().hex
        done, answer = threading.Event(), [False]
        self.pending[approval_id] = (done, answer)
        self._emit({"type": "approval", "id": approval_id, "question": question})
        done.wait(APPROVAL_TIMEOUT_S)  # unanswered approvals are declined
        self.pending.pop(approval_id, None)
        return answer[0]

    def approve_tool(self, question: str) -> bool:
        return True if self.auto_approve else self._ask(question)

    def confirm_private(self, question: str) -> bool:
        return self._ask(question)  # screenshots always ask, even with auto-approve

    def answer(self, approval_id: str, approved: bool) -> bool:
        entry = self.pending.get(approval_id)
        if entry is None:
            return False
        entry[1][0] = approved
        entry[0].set()
        return True

    def start_turn(self, message: str) -> queue.Queue[dict[str, Any] | None] | None:
        """Start a turn on a worker thread. Returns its event queue, or None if a turn is running."""
        if not self.lock.acquire(blocking=False):
            return None
        events: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.events = events

        def work() -> None:
            checkpoint = len(self.jarvis.messages)
            try:
                reply = self.jarvis.ask(message)
                events.put({"type": "done", "reply": reply})
            except anthropic.APIError as err:
                del self.jarvis.messages[checkpoint:]
                events.put({"type": "error", "message": f"Claude API error: {getattr(err, 'message', err)}"})
            except Exception as err:  # noqa: BLE001 - report anything to the browser rather than hang
                del self.jarvis.messages[checkpoint:]
                events.put({"type": "error", "message": f"{type(err).__name__}: {err}"})
            finally:
                events.put(None)
                self.events = None
                self.lock.release()

        threading.Thread(target=work, name="jarvis-web-turn", daemon=True).start()
        return events


def make_handler(session: WebSession, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Jarvis"

        def log_message(self, *args: object) -> None:  # keep the terminal quiet
            return None

        def _authorised(self) -> bool:
            supplied = self.headers.get("X-Jarvis-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
            return hmac.compare_digest(supplied.encode(), token.encode())

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("request too large")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            return data

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in ("/", "/api/team"):
                self._json(404, {"error": "not found"})
                return
            if not self._authorised():
                self._json(401, {"error": "Open the URL with the token Jarvis printed at start-up."})
                return
            if path == "/api/team":
                team = session.jarvis.team
                self._json(200, team.snapshot() if team else {"enabled": False})
                return
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")  # the token is in the URL
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorised():
                self._json(401, {"error": "unauthorised"})
                return
            try:
                data = self._body()
            except (ValueError, json.JSONDecodeError) as err:
                self._json(400, {"error": str(err)})
                return
            path = urlparse(self.path).path
            if path == "/api/approve":
                ok = session.answer(str(data.get("id", "")), bool(data.get("approved")))
                self._json(200 if ok else 404, {"ok": ok})
            elif path == "/api/reset":
                if session.lock.locked():
                    self._json(409, {"error": "Jarvis is busy."})
                else:
                    session.jarvis.reset()
                    self._json(200, {"ok": True})
            elif path == "/api/chat":
                message = str(data.get("message", "")).strip()
                if not message:
                    self._json(400, {"error": "empty message"})
                    return
                events = session.start_turn(message)
                if events is None:
                    self._json(409, {"error": "Jarvis is still working on the last request."})
                    return
                self._stream(events)
            else:
                self._json(404, {"error": "not found"})

        def _stream(self, events: queue.Queue[dict[str, Any] | None]) -> None:
            """Newline-delimited JSON events until the turn ends; the browser reads them as they arrive."""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                event = events.get()
                if event is None:
                    break
                try:
                    self.wfile.write(json.dumps(event).encode() + b"\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    continue  # the browser left; let the turn finish so the conversation stays valid
            self.close_connection = True

    return Handler


def serve(session: WebSession, host: str = "127.0.0.1", port: int = 8765, token: str | None = None) -> tuple[ThreadingHTTPServer, str]:
    token = token or secrets.token_urlsafe(24)
    server = ThreadingHTTPServer((host, port), make_handler(session, token))
    server.daemon_threads = True
    return server, token


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Jarvis</title>
<style>
  :root { --bg:#f6f7f9; --panel:#ffffff; --text:#14171c; --muted:#5d6673; --accent:#0b6bcb; --line:#dde1e7;
          --you:#e8f1fb; --code:#f0f2f5; --warn:#b4530f; --ok:#1f7a3a; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f1216; --panel:#171b21; --text:#e7eaee; --muted:#98a2ae; --accent:#5aa9ff; --line:#2a3039;
            --you:#16273a; --code:#1f252d; --warn:#f0a35e; --ok:#5fc27e; } }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
         display:flex; flex-direction:column; height:100dvh; }
  header { display:flex; align-items:center; gap:12px; padding:12px 16px; border-bottom:1px solid var(--line); background:var(--panel); }
  header h1 { font-size:18px; margin:0; flex:1; letter-spacing:.02em; }
  header label { font-size:14px; color:var(--muted); display:flex; gap:6px; align-items:center; }
  button { font:inherit; border-radius:10px; border:1px solid var(--line); background:var(--panel); color:var(--text); padding:8px 14px; cursor:pointer; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  button:disabled { opacity:.5; cursor:default; }
  #log { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:12px; }
  .msg { max-width:min(760px, 100%); padding:10px 14px; border-radius:14px; background:var(--panel); border:1px solid var(--line);
         white-space:pre-wrap; overflow-wrap:anywhere; }
  .you { align-self:flex-end; background:var(--you); }
  .tool { font-size:13px; color:var(--muted); padding:0 4px; }
  .error { color:var(--warn); }
  pre { background:var(--code); padding:10px; border-radius:8px; overflow-x:auto; white-space:pre; margin:6px 0; font-size:14px; }
  .approval { border-color:var(--warn); }
  .approval div { margin-top:8px; display:flex; gap:8px; }
  form { display:flex; gap:8px; padding:12px 16px calc(12px + env(safe-area-inset-bottom)); border-top:1px solid var(--line); background:var(--panel); }
  textarea { flex:1; resize:none; font:inherit; padding:10px; border-radius:10px; border:1px solid var(--line); background:var(--bg); color:var(--text); min-height:44px; max-height:160px; }
  #mic.on { background:var(--warn); border-color:var(--warn); color:#fff; }
  #crew { border-bottom:1px solid var(--line); background:var(--panel); padding:8px 16px 10px; }
  #crew[hidden] { display:none; }
  #crew summary { cursor:pointer; font-size:14px; color:var(--muted); display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  #crew summary b { color:var(--text); }
  .badge { font-size:12px; padding:2px 8px; border-radius:999px; border:1px solid var(--line); }
  .badge.passed, .badge.clean { color:var(--ok); border-color:var(--ok); }
  .badge.failed, .badge.unverified { color:var(--warn); border-color:var(--warn); }
  .meter { flex:1; min-width:120px; max-width:240px; height:6px; border-radius:3px; background:var(--code); overflow:hidden; }
  .meter i { display:block; height:100%; background:var(--accent); }
  .meter.hot i { background:var(--warn); }
  .agents { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:8px; margin-top:8px; }
  .agent { border:1px solid var(--line); border-radius:10px; padding:8px 10px; font-size:13px; min-width:0; }
  .agent .top { display:flex; align-items:center; gap:6px; font-weight:600; font-size:14px; }
  .agent .meta, .agent .last { color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--muted); flex:none; }
  .s-working .dot { background:var(--accent); animation:pulse 1s ease-in-out infinite; }
  .s-done .dot, .s-chief .dot { background:var(--ok); }
  .s-error .dot { background:var(--warn); }
  .s-error .last { color:var(--warn); }
  @keyframes pulse { 50% { opacity:.3; } }
  @media (prefers-reduced-motion: reduce) { .s-working .dot { animation:none; } }
</style>
</head>
<body>
<header>
  <h1>Jarvis</h1>
  <label><input type="checkbox" id="speak"> Speak replies</label>
  <button id="reset" type="button">New chat</button>
</header>
<details id="crew" hidden open>
  <summary><b>Crew</b> <span class="badge" id="gate"></span> <span id="busy"></span>
    <span class="meter" id="meter" hidden><i></i></span> <span id="budget"></span></summary>
  <div class="agents" id="agents"></div>
</details>
<main id="log" aria-live="polite"></main>
<form id="form">
  <button id="mic" type="button" aria-label="Talk" title="Talk">🎙</button>
  <textarea id="input" rows="1" placeholder="Ask Jarvis anything…" autofocus></textarea>
  <button class="primary" id="send" type="submit">Send</button>
</form>
<script>
const token = new URLSearchParams(location.search).get("token") || "";
const log = document.getElementById("log"), input = document.getElementById("input");
const send = document.getElementById("send"), mic = document.getElementById("mic"), speakBox = document.getElementById("speak");
const api = (path, body) => fetch(path, {method: "POST", headers: {"Content-Type": "application/json", "X-Jarvis-Token": token}, body: JSON.stringify(body || {})});

function add(cls, text) { const el = document.createElement("div"); el.className = cls; el.textContent = text || ""; log.appendChild(el); log.scrollTop = log.scrollHeight; return el; }
function render(el, text) {           // code blocks as <pre>, everything else as plain text (never innerHTML)
  el.textContent = "";
  text.split(/```[^\n]*\n?/).forEach((part, i) => {
    if (i % 2) { const pre = document.createElement("pre"); pre.textContent = part.replace(/\n$/, ""); el.appendChild(pre); }
    else if (part) el.appendChild(document.createTextNode(part));
  });
}

// Speak sentence by sentence as the reply streams in; code blocks stay on screen.
let spoken = "", fence = false;
function speakNew(full, final) {
  if (!speakBox.checked || !("speechSynthesis" in window)) return;
  let rest = full.slice(spoken.length);
  const re = final ? /[\s\S]+/ : /[\s\S]*?(?:[.!?:](?=\s)|\n)/;
  let m;
  while ((m = rest.match(re)) && m[0]) {
    let chunk = m[0]; spoken += chunk; rest = rest.slice(chunk.length);
    const pieces = chunk.split("```");
    let say = "";
    pieces.forEach((p, i) => { if (i > 0) { fence = !fence; if (fence) say += " The code is on screen. "; } if (!fence) say += p; });
    say = say.replace(/[*_#`>|]/g, " ").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").trim();
    if (say) speechSynthesis.speak(new SpeechSynthesisUtterance(say));
    if (final) break;
  }
}

async function chat(text) {
  add("msg you", text); input.value = ""; send.disabled = true; speechSynthesis && speechSynthesis.cancel();
  spoken = ""; fence = false;
  let bubble = null, full = "";
  try {
    const res = await fetch("/api/chat", {method: "POST", headers: {"Content-Type": "application/json", "X-Jarvis-Token": token}, body: JSON.stringify({message: text})});
    if (!res.ok) { add("msg error", (await res.json()).error || res.statusText); return; }
    const reader = res.body.getReader(), decoder = new TextDecoder(); let buffer = "";
    while (true) {
      const {value, done} = await reader.read(); if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const event = JSON.parse(buffer.slice(0, nl)); buffer = buffer.slice(nl + 1);
        if (event.type === "delta") { if (!bubble) { bubble = add("msg"); full = ""; spoken = ""; fence = false; } full += event.text; render(bubble, full); speakNew(full, false); log.scrollTop = log.scrollHeight; }
        else if (event.type === "block_end") { if (bubble) speakNew(full, true); bubble = null; }
        else if (event.type === "tool") add("tool", "⚙ " + event.line);
        else if (event.type === "approval") askApproval(event);
        else if (event.type === "error") add("msg error", event.message);
      }
    }
  } catch (err) { add("msg error", "Connection lost: " + err); }
  finally { send.disabled = false; input.focus(); }
}

function askApproval(event) {
  const box = add("msg approval", event.question), row = document.createElement("div");
  for (const [label, ok] of [["Allow", true], ["Decline", false]]) {
    const b = document.createElement("button"); b.textContent = label; if (ok) b.className = "primary";
    b.onclick = async () => { row.remove(); box.appendChild(document.createTextNode(ok ? "  ✓ allowed" : "  ✗ declined")); await api("/api/approve", {id: event.id, approved: ok}); };
    row.appendChild(b);
  }
  box.appendChild(row);
}

// Crew panel: shown in team mode, refreshed every 2 seconds.
const crew = document.getElementById("crew"), agentsBox = document.getElementById("agents");
const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(n);
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
async function refreshCrew() {
  try {
    const res = await fetch("/api/team", {headers: {"X-Jarvis-Token": token}});
    if (!res.ok) return;
    const team = await res.json();
    if (!team.enabled) { crew.hidden = true; return false; }
    crew.hidden = false;
    const gate = document.getElementById("gate");
    gate.textContent = "Quality gate: " + team.gate; gate.className = "badge " + team.gate;
    const working = team.agents.filter(a => a.status === "working").map(a => a.name);
    document.getElementById("busy").textContent = working.length ? "Working: " + working.join(", ") : "";
    const meter = document.getElementById("meter"), budget = document.getElementById("budget");
    if (team.budget) {
      const share = Math.min(1, team.budget.used / team.budget.limit);
      meter.hidden = false; meter.firstElementChild.style.width = (share * 100) + "%"; meter.classList.toggle("hot", share >= 0.8);
      budget.textContent = fmt(team.budget.used) + " / " + fmt(team.budget.limit) + " tokens";
    } else { meter.hidden = true; budget.textContent = ""; }
    agentsBox.textContent = "";
    for (const a of team.agents) {
      const card = el("div", "agent s-" + a.status);
      card.title = a.title + " · " + a.model + (a.last ? "\n" + a.last : "");
      const top = el("div", "top"); top.append(el("span", "dot"), el("span", "", a.name)); card.appendChild(top);
      const tasks = a.tasks === null ? "chief" : a.tasks + (a.tasks === 1 ? " task" : " tasks");
      card.appendChild(el("div", "meta", tasks + " · " + fmt(a.input + a.output) + " tok"));
      const last = a.status === "chief" ? "Leads the crew" : a.status === "idle" ? a.mode : (a.last || a.status);
      card.appendChild(el("div", "last", last));
      agentsBox.appendChild(card);
    }
    return true;
  } catch (err) { return; }
}
if (innerWidth < 600) crew.open = false;  // phones: the summary line is enough until tapped
refreshCrew().then(on => { if (on !== false) setInterval(refreshCrew, 2000); });

document.getElementById("form").onsubmit = e => { e.preventDefault(); const t = input.value.trim(); if (t) chat(t); };
input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); document.getElementById("form").requestSubmit(); } });
document.getElementById("reset").onclick = async () => { const r = await api("/api/reset"); if (r.ok) log.textContent = ""; else add("msg error", (await r.json()).error); };

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!Recognition) { mic.disabled = true; mic.title = "This browser has no speech recognition"; }
else {
  const rec = new Recognition(); rec.interimResults = true; rec.lang = navigator.language || "en-US";
  let listening = false;
  rec.onresult = e => { input.value = Array.from(e.results).map(r => r[0].transcript).join(""); };
  rec.onend = () => { listening = false; mic.classList.remove("on"); const t = input.value.trim(); if (t && !send.disabled) { speakBox.checked = true; chat(t); } };
  mic.onclick = () => { if (listening) { rec.stop(); return; } speechSynthesis && speechSynthesis.cancel(); input.value = ""; listening = true; mic.classList.add("on"); rec.start(); };
}
</script>
</body>
</html>
"""
