"""Web and phone interface: chat with Jarvis in a browser, with streaming replies, approvals and voice,
plus a dashboard of CI health, alerts and session stats at /dashboard.

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
from .dashboard import Dashboard

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


def make_handler(session: WebSession, token: str, dashboard: Dashboard) -> type[BaseHTTPRequestHandler]:
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
            pages = {"/": PAGE, "/dashboard": DASHBOARD_PAGE}
            if path not in pages and path != "/api/dashboard":
                self._json(404, {"error": "not found"})
                return
            if not self._authorised():
                self._json(401, {"error": "Open the URL with the token Jarvis printed at start-up."})
                return
            if path == "/api/dashboard":
                self._json(200, dashboard.snapshot(busy=session.lock.locked()))
                return
            body = pages[path].encode()
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
            elif path == "/api/dashboard/refresh":
                ok = dashboard.refresh()
                self._json(200 if ok else 409, {"ok": ok} if ok else {"error": "No repositories are being watched. Start Jarvis with --web --watch."})
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


def serve(session: WebSession, host: str = "127.0.0.1", port: int = 8765, token: str | None = None,
          dashboard: Dashboard | None = None) -> tuple[ThreadingHTTPServer, str]:
    token = token or secrets.token_urlsafe(24)
    dashboard = dashboard or Dashboard(session.jarvis, auto_approve=session.auto_approve)
    server = ThreadingHTTPServer((host, port), make_handler(session, token, dashboard))
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
          --you:#e8f1fb; --code:#f0f2f5; --warn:#b4530f; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f1216; --panel:#171b21; --text:#e7eaee; --muted:#98a2ae; --accent:#5aa9ff; --line:#2a3039;
            --you:#16273a; --code:#1f252d; --warn:#f0a35e; } }
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
  .navlink { color:var(--accent); text-decoration:none; font-size:15px; }
  #mic.on { background:var(--warn); border-color:var(--warn); color:#fff; }
</style>
</head>
<body>
<header>
  <h1>Jarvis</h1>
  <label><input type="checkbox" id="speak"> Speak replies</label>
  <a id="dash" class="navlink" href="#">Dashboard</a>
  <button id="reset" type="button">New chat</button>
</header>
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
document.getElementById("dash").href = "/dashboard?token=" + encodeURIComponent(token);
// The dashboard's "Fix with Jarvis" opens the chat with the request filled in (in the fragment, never sent to
// the server); you read it and press Send.
const asked = new URLSearchParams(location.hash.slice(1)).get("ask");
if (asked) { document.getElementById("input").value = asked; history.replaceState(null, "", location.pathname + location.search); }
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


DASHBOARD_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Jarvis Dashboard</title>
<style>
  :root { --bg:#f6f7f9; --panel:#ffffff; --text:#14171c; --muted:#5d6673; --accent:#0b6bcb; --line:#dde1e7;
          --ok:#1a7f4b; --bad:#c2321f; --warn:#b4530f; --chip:#eef1f5; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f1216; --panel:#171b21; --text:#e7eaee; --muted:#98a2ae; --accent:#5aa9ff; --line:#2a3039;
            --ok:#4cc38a; --bad:#ff6b5a; --warn:#f0a35e; --chip:#222831; } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  header { position:sticky; top:0; z-index:1; display:flex; align-items:center; gap:12px; padding:12px 16px;
           border-bottom:1px solid var(--line); background:var(--panel); }
  header h1 { font-size:18px; margin:0; flex:1; letter-spacing:.02em; }
  a { color:var(--accent); text-decoration:none; }
  button { font:inherit; border-radius:10px; border:1px solid var(--line); background:var(--panel); color:var(--text); padding:6px 12px; cursor:pointer; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  button:disabled { opacity:.5; cursor:default; }
  main { max-width:1100px; margin:0 auto; padding:16px; display:grid; gap:16px; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; }
  .kpi, section { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }
  .kpi .label { color:var(--muted); font-size:13px; }
  .kpi .value { font-size:28px; font-weight:600; font-variant-numeric:tabular-nums; }
  .kpi .sub { color:var(--muted); font-size:12px; }
  .bad { color:var(--bad); } .ok { color:var(--ok); }
  h2 { font-size:15px; margin:0 0 10px; display:flex; align-items:center; gap:8px; }
  h2 .meta { margin-left:auto; color:var(--muted); font-weight:400; font-size:13px; }
  .cols { display:grid; grid-template-columns:2fr 1fr; gap:16px; align-items:start; }
  @media (max-width: 820px) { .cols { grid-template-columns:1fr; } }
  .repos { display:grid; gap:10px; }
  .repo { border:1px solid var(--line); border-radius:12px; padding:10px 12px; }
  .repo.failing { border-color:var(--bad); }
  .repo-head { display:flex; gap:8px; align-items:center; font-weight:600; overflow-wrap:anywhere; }
  .repo-head .count { margin-left:auto; font-weight:400; font-size:13px; color:var(--muted); white-space:nowrap; }
  .wf { display:flex; align-items:center; gap:8px; padding:6px 0; border-top:1px solid var(--line); flex-wrap:wrap; }
  .wf:first-of-type { border-top:0; }
  .dot { width:10px; height:10px; border-radius:50%; flex:none; background:var(--ok); }
  .dot.failing { background:var(--bad); }
  .wf .name { flex:1; min-width:120px; overflow-wrap:anywhere; }
  .chip { background:var(--chip); border-radius:999px; padding:1px 8px; font-size:12px; color:var(--muted); font-family:ui-monospace, monospace; }
  .muted { color:var(--muted); }
  ul.list { list-style:none; margin:0; padding:0; display:grid; gap:8px; }
  ul.list li { font-size:14px; overflow-wrap:anywhere; }
  ul.list .when { color:var(--muted); font-size:12px; display:block; }
  dl { display:grid; grid-template-columns:auto 1fr; gap:6px 12px; margin:0; font-size:14px; }
  dt { color:var(--muted); } dd { margin:0; overflow-wrap:anywhere; }
  .empty { color:var(--muted); font-size:14px; }
  .errors li { color:var(--warn); }
  .stack { display:grid; gap:16px; }
  .pill { font-size:12px; padding:2px 8px; border-radius:999px; border:1px solid var(--line); color:var(--muted); }
  .pill.busy { color:var(--warn); border-color:var(--warn); }
</style>
</head>
<body>
<header>
  <h1>Jarvis · Dashboard</h1>
  <span id="state" class="pill">…</span>
  <button id="refresh" type="button">Check now</button>
  <a id="chat" href="#">Chat</a>
</header>
<main>
  <div class="kpis" id="kpis"></div>
  <div class="cols">
    <section>
      <h2>CI on default branches <span class="meta" id="checked"></span></h2>
      <div id="repos" class="repos"></div>
      <ul id="errors" class="list errors"></ul>
    </section>
    <div class="stack">
      <section><h2>Alerts</h2><ul id="alerts" class="list"></ul></section>
      <section><h2>Session</h2><dl id="session"></dl></section>
      <section><h2>Memory <span class="meta" id="memcount"></span></h2><ul id="memory" class="list"></ul></section>
    </div>
  </div>
</main>
<script>
const token = new URLSearchParams(location.search).get("token") || "";
const headers = {"X-Jarvis-Token": token};
document.getElementById("chat").href = "/?token=" + encodeURIComponent(token);
const $ = id => document.getElementById(id);
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
function link(url, text) {   // only GitHub-style https links become clickable
  if (typeof url === "string" && url.startsWith("https://")) { const a = el("a", "", text); a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; return a; }
  return el("span", "muted", text);
}
const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e4 ? Math.round(n / 1e3) + "k" : n.toLocaleString();
function ago(t, now) {
  if (!t) return "never"; const s = Math.max(0, Math.round(now - t));
  return s < 60 ? s + "s ago" : s < 3600 ? Math.floor(s / 60) + " min ago" : Math.floor(s / 3600) + " h ago";
}
function kpi(label, value, sub, cls) {
  const box = el("div", "kpi"); box.append(el("div", "label", label), el("div", "value " + (cls || ""), value));
  if (sub) box.append(el("div", "sub", sub)); return box;
}
function fixLink(prompt) {
  const b = el("button", "primary", "Fix with Jarvis");
  b.onclick = () => { location.href = "/?token=" + encodeURIComponent(token) + "#ask=" + encodeURIComponent(prompt); };
  return b;
}

function render(d) {
  const ci = d.ci, s = d.session, u = s.usage || {};
  const state = $("state"); state.textContent = s.busy ? "Working" : "Idle"; state.className = "pill" + (s.busy ? " busy" : "");
  const tokens = (u.input_tokens || 0) + (u.output_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0);
  const k = $("kpis"); k.textContent = "";
  if (ci.enabled) {
    k.append(kpi("Failing workflows", String(ci.totals.failing), ci.totals.failing ? "needs attention" : "all green", ci.totals.failing ? "bad" : "ok"),
             kpi("Passing workflows", String(ci.totals.passing), "of " + ci.totals.workflows),
             kpi("Repositories", String(ci.totals.repos), "watched"));
  } else {
    k.append(kpi("CI watch", "Off", "start with --web --watch"));
  }
  k.append(kpi("Tokens this session", fmt(tokens), plural(u.requests || 0, "request") + " · " + plural(s.turns, "turn")));

  const repos = $("repos"); repos.textContent = "";
  $("refresh").disabled = !ci.enabled || ci.checking;
  if (!ci.enabled) {
    repos.append(el("p", "empty", "Not watching any repositories. Start Jarvis with “jarvis --web --watch” (your account) or “jarvis --web --watch owner owner/repo”."));
    $("checked").textContent = "";
  } else {
    $("checked").textContent = ci.checking ? "checking…" : "checked " + ago(ci.last_checked, d.now) + " · every " + Math.round(ci.interval_s / 60) + " min";
    if (!ci.repos.length) repos.append(el("p", "empty", ci.last_checked ? "No completed workflow runs found on the watched default branches." : "First check in progress…"));
    for (const r of ci.repos) {
      const card = el("div", "repo" + (r.failing ? " failing" : ""));
      const head = el("div", "repo-head"); head.append(link("https://github.com/" + r.repo, r.repo),
        el("span", "count " + (r.failing ? "bad" : "ok"), r.failing ? r.failing + " failing" : "healthy"));
      card.append(head);
      for (const w of r.workflows) {
        const row = el("div", "wf");
        row.append(el("span", "dot " + w.status), el("span", "name", w.workflow), el("span", "chip", w.commit), link(w.url, w.status === "failing" ? "logs" : "run"));
        if (w.fix_prompt) row.append(fixLink(w.fix_prompt));
        card.append(row);
      }
      repos.append(card);
    }
  }
  const errors = $("errors"); errors.textContent = "";
  for (const e of (ci.errors || [])) errors.append(el("li", "", e));

  const alerts = $("alerts"); alerts.textContent = "";
  if (!ci.enabled || !ci.alerts.length) alerts.append(el("li", "empty", ci.enabled ? "No alerts yet. Builds that break or recover show up here." : "Alerts appear when CI watch is on."));
  else for (const a of ci.alerts) {
    const li = el("li"); li.append(el("span", "when", ago(a.time, d.now)), el("strong", a.kind === "failing" ? "bad" : "ok", a.kind === "failing" ? "Broke " : "Recovered "),
      document.createTextNode(a.repo + " · " + a.workflow + " "), el("span", "chip", a.commit));
    alerts.append(li);
  }

  const sess = $("session"); sess.textContent = "";
  const rows = [["Model", s.model], ["Effort", s.effort], ["Mode", s.autonomous ? "Autonomous" : s.auto_approve ? "Auto-approve" : "Asks before changes"],
                ["Tools", s.tools + (s.mcp ? " (MCP: " + s.mcp + ")" : "")], ["Up since", ago(s.started_at, d.now)],
                ["Tokens", fmt(u.input_tokens || 0) + " in · " + fmt(u.output_tokens || 0) + " out · " + fmt(u.cache_read_input_tokens || 0) + " cached"]];
  for (const [a, b] of rows) sess.append(el("dt", "", a), el("dd", "", String(b)));

  const mem = $("memory"); mem.textContent = "";
  $("memcount").textContent = s.memory.enabled ? plural(s.memory.count, "note") : "off";
  if (!s.memory.recent.length) mem.append(el("li", "empty", s.memory.enabled ? "Nothing remembered yet." : "Memory is off (--no-memory)."));
  for (const n of s.memory.recent) mem.append(el("li", "", n));
}

let timer = null;
async function load() {
  clearTimeout(timer);
  try {
    const res = await fetch("/api/dashboard", {headers});
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    const data = await res.json(); render(data);
    timer = setTimeout(load, data.ci.checking ? 2000 : 15000);
  } catch (err) {
    $("state").textContent = "Offline"; $("state").className = "pill busy";
    timer = setTimeout(load, 15000);
  }
}
$("refresh").onclick = async () => {
  $("refresh").disabled = true;
  await fetch("/api/dashboard/refresh", {method: "POST", headers: {...headers, "Content-Type": "application/json"}, body: "{}"});
  setTimeout(load, 800);
};
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
load();
</script>
</body>
</html>
"""
