"""Generic computer-use tools (browser + files). Nothing here knows about invoices."""
import json
import re
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import Error as PWError, sync_playwright
import config
from utils import inr, parse_amount


class ToolError(Exception):
    pass


class Blocked(ToolError):
    """Action refused by policy / human."""


TOOLS = {
    "browser_goto": ("Navigate the browser to an absolute URL.", {"url": "string"}),
    "browser_read_page": ("Return the current page: url, title, visible text, links, form inputs, buttons.", {}),
    "browser_click": ("Click an element. selector = CSS or Playwright selector, e.g. 'text=Sign in', "
                      "'button:has-text(\"Save\")', 'a:has-text(\"Add Invoice\")'.", {"selector": "string"}),
    "browser_fill": ("Type a value into an input (replaces existing text).", {"selector": "string", "value": "string"}),
    "download_file": ("Download a file using the browser's logged-in session. Returns local path.",
                      {"url": "string", "filename": "string"}),
    "read_pdf": ("Extract text from a downloaded PDF.", {"path": "string"}),
    "remember": ("Store a fact in working memory (kept across steps).", {"key": "string", "value": "string"}),
    "ask_human": ("Ask the user a question / for clarification. Blocks until they answer.", {"question": "string"}),
    "update_plan": ("Replace your plan when reality differs from it.", {"plan": "list[string]", "reason": "string"}),
    "finish": ("End the task. status: success | failed | blocked. An independent verifier checks 'success' claims.",
               {"status": "string", "summary": "string", "evidence": "list[string]"}),
}


def tool_docs(names=None) -> str:
    lines = []
    for n, (d, a) in TOOLS.items():
        if names is None or n in names:
            lines.append(f"- {n}({json.dumps(a)}): {d}")
    return "\n".join(lines)


READ_JS = """() => {
 const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
 return {url: location.href, title: document.title,
  text: document.body.innerText.slice(0, 3500),
  links: [...document.querySelectorAll('a[href]')].filter(vis).slice(0, 60).map(a => ({text: a.innerText.trim().slice(0, 50), href: a.href})),
  inputs: [...document.querySelectorAll('input,select,textarea')].filter(vis).map(i => ({name: i.name, id: i.id, type: i.type, placeholder: i.placeholder || '', value: i.type === 'password' ? '' : i.value})),
  buttons: [...document.querySelectorAll('button,input[type=submit]')].filter(vis).map(b => ({text: (b.innerText || b.value || '').trim(), type: b.type}))};
}"""

CLICK_JS = """el => { const f = el.closest('form'); const fields = {};
 if (f) new FormData(f).forEach((v, k) => { if (typeof v === 'string') fields[k] = v; });
 return {isSubmit: !!f && el.type === 'submit', method: f ? f.method : '', fields}; }"""


class Policy:
    """Runtime-enforced guardrail (not left to the LLM): large-amount form submits need human approval."""

    def __init__(self, bus, threshold: float):
        self.bus, self.threshold, self.approved = bus, threshold, set()

    def check_submit(self, fields: dict, url: str):
        for k, v in fields.items():
            if not re.search(r"amount|total", k, re.I):
                continue
            amt = parse_amount(v)
            if amt is None or amt <= self.threshold or amt in self.approved:
                continue
            ans = self.bus.ask(f"Approval required: about to submit a form at {url} with {k} = ₹{inr(amt)}, "
                               f"above the ₹{inr(self.threshold)} policy limit. Approve?", kind="approval")
            ok = ans.strip().upper().startswith("APPROVE")
            self.bus.emit("policy", approved=ok, amount=amt, note=f"Human {'approved' if ok else 'rejected'} submission of ₹{inr(amt)}")
            if not ok:
                raise Blocked(f"BLOCKED: a human did not approve submitting amount ₹{inr(amt)} ({ans!r}). Do not submit it. "
                              "Finish with status 'blocked' unless the human gave other instructions.")
            self.approved.add(amt)


class BrowserSession:
    def __init__(self, run_dir: Path, bus, headless: bool = True):
        self.run_dir, self.bus = run_dir, bus
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=True)
        self.context.set_default_timeout(8000)

    def toolbox(self, name: str, policy: Policy | None, readonly: bool = False) -> "Toolbox":
        return Toolbox(self, self.context.new_page(), name, policy, readonly)

    def close(self):
        for fn in (self.context.close, self.browser.close, self._pw.stop):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass


class Toolbox:
    def __init__(self, session: BrowserSession, page, name: str, policy, readonly: bool):
        self.s, self.page, self.name, self.policy, self.readonly = session, page, name, policy, readonly
        self.shots = session.run_dir / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.downloads = session.run_dir / "downloads"
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.last_status = None
        page.on("response", self._on_response)

    def _on_response(self, r):
        try:
            if r.request.resource_type == "document" and r.frame == self.page.main_frame:
                self.last_status = r.status
        except PWError:
            pass

    # ---- helpers
    def _brief(self) -> str:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=3000)
            text = self.page.evaluate("document.body.innerText").strip().replace("\n", " | ")
            return (f"HTTP status: {self.last_status}\nURL: {self.page.url}\nTitle: {self.page.title()}\n"
                    f"Page text: {text[:400]}")
        except PWError:
            return f"URL: {self.page.url}"

    def screenshot(self, step: int, tool: str):
        self.n += 1
        fn = f"{self.name}_{self.n:02d}.png"
        try:
            self.page.screenshot(path=str(self.shots / fn))
        except PWError:
            return
        self.s.bus.emit("screenshot", step=step, tool=tool, actor=self.name,
                        url=f"/runs/{self.s.run_dir.name}/shots/{fn}", page_url=self.page.url)

    # ---- tool dispatch
    def execute(self, tool: str, args: dict) -> str:
        fn = getattr(self, f"t_{tool}", None)
        if not fn:
            raise ToolError(f"Unknown or unavailable tool '{tool}'.")
        try:
            return fn(**args)
        except TypeError as e:
            raise ToolError(f"Bad arguments for {tool}: {e}. Expected {TOOLS.get(tool, ('', {}))[1]}")
        except PWError as e:
            raise ToolError(str(e).strip().splitlines()[0][:300])

    def t_browser_goto(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded")
        return self._brief()

    def t_browser_read_page(self):
        return json.dumps(self.page.evaluate(READ_JS), ensure_ascii=False)

    def t_browser_click(self, selector: str):
        loc = self.page.locator(selector).first
        loc.wait_for(state="visible", timeout=5000)
        info = loc.evaluate(CLICK_JS)
        if info["isSubmit"]:
            if self.readonly and info["method"].lower() == "post":
                raise Blocked("Read-only verifier may not submit POST forms.")
            if self.policy:
                self.policy.check_submit(info["fields"], self.page.url)
        loc.click(timeout=5000)
        return "Clicked.\n" + self._brief()

    def t_browser_fill(self, selector: str, value: str):
        self.page.locator(selector).first.fill(str(value), timeout=5000)
        return f"Filled {selector}."

    def t_download_file(self, url: str, filename: str):
        if self.readonly:
            raise Blocked("Read-only verifier may not download files.")
        r = self.s.context.request.get(urljoin(self.page.url if self.page.url.startswith("http") else url, url))
        if not r.ok or "text/html" in r.headers.get("content-type", ""):
            raise ToolError(f"Download failed: HTTP {r.status} content-type={r.headers.get('content-type')} "
                            "(not logged in? wrong URL?)")
        path = self.downloads / Path(filename).name
        path.write_bytes(r.body())
        return f"Saved {len(r.body())} bytes to {path}"

    def t_read_pdf(self, path: str):
        from pypdf import PdfReader
        p = Path(path)
        if self.s.run_dir.resolve() not in p.resolve().parents:
            raise ToolError("Path must be inside this run's downloads directory.")
        if not p.exists():
            raise ToolError(f"No such file: {path}")
        text = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages).strip()
        if not text:
            raise ToolError("PDF has no extractable text (scanned?).")
        return text[:4000]
