"""Mock Vendor Invoice Portal: login, searchable invoice list, PDF download."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
import config
from utils import esc, layout
from portal.data import INVOICES
from portal.pdfgen import PDF_DIR, generate_all

TOKEN = "portal-session-ok"


@asynccontextmanager
async def lifespan(_):
    generate_all()
    yield


app = FastAPI(lifespan=lifespan)


def page(title, body, authed=True):
    nav = "<a href='/invoices'>Invoices</a><a href='/logout'>Sign out</a>" if authed else ""
    return HTMLResponse(layout(title, "Vendor Invoice Portal", nav, body))


def authed(req: Request) -> bool:
    return req.cookies.get("portal_session") == TOKEN


@app.get("/")
def root():
    return RedirectResponse("/invoices")


@app.get("/login", response_class=HTMLResponse)
def login_form():
    return page("Sign in", """<div class='card'><h2>Sign in</h2>
    <form method='post' action='/login'>
    <label>Username</label><input name='username' autocomplete='off'>
    <label>Password</label><input name='password' type='password'>
    <button type='submit'>Sign in</button></form></div>""", authed=False)


@app.post("/login")
def login(username: str = Form(""), password: str = Form("")):
    if username == config.PORTAL_USER and password == config.PORTAL_PASS:
        r = RedirectResponse("/invoices", status_code=303)
        r.set_cookie("portal_session", TOKEN)
        return r
    resp = page("Sign in", "<div class='card'><div class='error'>Invalid username or password.</div>"
                "<a href='/login'>Try again</a></div>", authed=False)
    resp.status_code = 401
    return resp


@app.get("/logout")
def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie("portal_session")
    return r


@app.get("/invoices", response_class=HTMLResponse)
def invoices(req: Request, q: str = ""):
    if not authed(req):
        return RedirectResponse("/login")
    ql = q.strip().lower()
    rows = [i for i in INVOICES if not ql or ql in i["vendor"].lower() or ql in i["invoice_number"].lower()]
    trs = "".join(
        f"<tr><td>{esc(i['vendor'])}</td><td>{esc(i['invoice_number'])}</td><td>{esc(i['date'])}</td>"
        f"<td><a href='/invoices/{esc(i['invoice_number'])}/pdf'>Download PDF</a></td></tr>" for i in rows)
    body = (f"<h2>Vendor invoices</h2><form class='inline' method='get' action='/invoices'>"
            f"<input name='q' value='{esc(q)}' placeholder='Search vendor or invoice number'>"
            f"<button type='submit'>Search</button></form>"
            f"<p class='muted'>{len(rows)} invoice(s)</p>"
            f"<table><tr><th>Vendor</th><th>Invoice #</th><th>Invoice date</th><th>Document</th></tr>{trs}</table>")
    return page("Invoices", body)


@app.get("/invoices/{number}/pdf")
def pdf(number: str, req: Request):
    if not authed(req):
        return RedirectResponse("/login")
    f = PDF_DIR / f"{number}.pdf"
    if not f.exists() or "/" in number or "\\" in number:
        return HTMLResponse("Invoice not found", status_code=404)
    return FileResponse(f, media_type="application/pdf", filename=f"{number}.pdf")
