"""Mock internal Finance System (system of record) with deliberate failure modes:
   - 422 on badly formatted amount/date
   - 409 on duplicate invoice number
   - 503 on the first submit of every new invoice (FLAKY_FINANCE=1) -> exercises retry
"""
import re
import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import config
from utils import esc, layout, money

DB = Path(__file__).parent / "finance.db"
LOCK = threading.Lock()
ATTEMPTS: set = set()
SEED = [
    ("Google Cloud", "GCP-3011", 72000, "17/09/2026"), ("Google Cloud", "GCP-3012", 75000, "17/10/2026"),
    ("Microsoft", "MS-2091", 42000, "18/08/2026"), ("Microsoft", "MS-2092", 42000, "19/09/2026"),
    ("AWS", "AWS-1021", 118200, "15/08/2026"), ("AWS", "AWS-1022", 121350, "20/09/2026"),
    ("Datadog", "DD-7001", 18600, "30/09/2026"),
]


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def reset_db():
    ATTEMPTS.clear()
    with LOCK, conn() as c:
        c.execute("DROP TABLE IF EXISTS invoices")
        c.execute("""CREATE TABLE invoices(id INTEGER PRIMARY KEY AUTOINCREMENT, vendor TEXT, invoice_number TEXT UNIQUE,
                     amount REAL, due_date TEXT, status TEXT, created_at TEXT)""")
        for v, n, a, d in SEED:
            c.execute("INSERT INTO invoices(vendor,invoice_number,amount,due_date,status,created_at) VALUES(?,?,?,?,?,?)",
                      (v, n, a, d, "Processed", "2026-10-01 10:00"))


@asynccontextmanager
async def lifespan(_):
    reset_db()
    yield


app = FastAPI(lifespan=lifespan)
NAV = "<a href='/'>Dashboard</a><a href='/invoices/new'>Add Invoice</a>"


def page(title, body, status=200):
    return HTMLResponse(layout(title, "ABC Finance System", NAV, body), status_code=status)


def table(rows):
    trs = "".join(
        f"<tr><td>{esc(r['vendor'])}</td><td><a href='/invoices/{r['id']}'>{esc(r['invoice_number'])}</a></td>"
        f"<td>{money(r['amount'])}</td><td>{esc(r['due_date'])}</td><td>{esc(r['status'])}</td></tr>" for r in rows)
    return (f"<table id='invoice-table'><tr><th>Vendor</th><th>Invoice</th><th>Amount</th><th>Due date</th>"
            f"<th>Status</th></tr>{trs}</table>")


SEARCH = ("<form class='inline' method='get' action='/search'><input name='q' placeholder='Search vendor or invoice number'>"
          "<button type='submit'>Search</button></form>")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with conn() as c:
        rows = c.execute("SELECT * FROM invoices ORDER BY id DESC").fetchall()
    total = sum(r["amount"] for r in rows)
    return page("Dashboard", f"<h2>Invoice records</h2><p class='muted'>{len(rows)} records · total {money(total)}</p>"
                f"{SEARCH}<p><a class='btn' href='/invoices/new'>Add Invoice</a></p>{table(rows)}")


@app.get("/search", response_class=HTMLResponse)
def search(q: str = ""):
    like = f"%{q.strip()}%"
    with conn() as c:
        rows = c.execute("SELECT * FROM invoices WHERE vendor LIKE ? OR invoice_number LIKE ? ORDER BY id DESC",
                         (like, like)).fetchall()
    msg = "" if rows else "<p class='muted'>No matching invoices.</p>"
    return page("Search", f"<h2>Search results for '{esc(q)}'</h2>{SEARCH}{msg}{table(rows) if rows else ''}")


@app.get("/invoices/new", response_class=HTMLResponse)
def new_form():
    return page("Add Invoice", """<div class='card'><h2>Add Invoice</h2><form method='post' action='/invoices'>
      <label>Vendor</label><input name='vendor'>
      <label>Invoice Number</label><input name='invoice_number'>
      <label>Amount (INR)</label><input name='amount'>
      <label>Due Date (DD/MM/YYYY)</label><input name='due_date'>
      <button type='submit'>Save Invoice</button></form></div>""")


def err(msg, status):
    return page("Error", f"<div class='card'><div class='error' id='error'>{esc(msg)}</div>"
                f"<a href='/invoices/new'>Back to form</a> · <a href='/'>Dashboard</a></div>", status)


@app.post("/invoices")
def create(vendor: str = Form(""), invoice_number: str = Form(""), amount: str = Form(""), due_date: str = Form("")):
    vendor, invoice_number, amount, due_date = (x.strip() for x in (vendor, invoice_number, amount, due_date))
    if not (vendor and invoice_number and amount and due_date):
        return err("All fields are required.", 422)
    if not re.fullmatch(r"\d+(\.\d{1,2})?", amount):
        return err("Amount must be a plain number (digits only, no commas or currency symbols).", 422)
    try:
        datetime.strptime(due_date, "%d/%m/%Y")
    except ValueError:
        return err("Due date must be in DD/MM/YYYY format.", 422)
    with conn() as c:
        if c.execute("SELECT 1 FROM invoices WHERE lower(invoice_number)=lower(?)", (invoice_number,)).fetchone():
            return err(f"Invoice already exists: {invoice_number}", 409)
    key = invoice_number.lower()
    if config.FLAKY_FINANCE and key not in ATTEMPTS:
        ATTEMPTS.add(key)
        return err("Service temporarily unavailable (503). Please retry.", 503)
    with LOCK, conn() as c:
        cur = c.execute("INSERT INTO invoices(vendor,invoice_number,amount,due_date,status,created_at) VALUES(?,?,?,?,?,?)",
                        (vendor, invoice_number, float(amount), due_date, "Recorded", datetime.now().strftime("%Y-%m-%d %H:%M")))
        new_id = cur.lastrowid
    return RedirectResponse(f"/invoices/{new_id}?saved=1", status_code=303)


@app.get("/invoices/{inv_id}", response_class=HTMLResponse)
def detail(inv_id: int, saved: int = 0):
    with conn() as c:
        r = c.execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
    if not r:
        return err("Invoice not found.", 404)
    banner = "<div class='success'>Invoice saved.</div>" if saved else ""
    return page("Invoice", f"<h2>Invoice {esc(r['invoice_number'])}</h2>{banner}<dl>"
                f"<dt>Vendor</dt><dd>{esc(r['vendor'])}</dd><dt>Invoice Number</dt><dd>{esc(r['invoice_number'])}</dd>"
                f"<dt>Amount</dt><dd>{money(r['amount'])}</dd><dt>Due Date</dt><dd>{esc(r['due_date'])}</dd>"
                f"<dt>Status</dt><dd>{esc(r['status'])}</dd><dt>Recorded at</dt><dd>{esc(r['created_at'])}</dd></dl>")


@app.post("/admin/reset")
def admin_reset():
    reset_db()
    return {"ok": True}
