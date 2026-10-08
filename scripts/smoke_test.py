"""Environment smoke test (no LLM key / browser needed): python scripts/smoke_test.py"""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from pypdf import PdfReader
import config
config.FLAKY_FINANCE = True
from portal.app import app as portal_app
from finance.app import app as finance_app


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        sys.exit(1)


with TestClient(portal_app, follow_redirects=False) as p:
    check("portal redirects to login when anonymous", p.get("/invoices").status_code in (302, 307))
    check("bad login rejected", p.post("/login", data={"username": "x", "password": "y"}).status_code == 401)
    r = p.post("/login", data={"username": config.PORTAL_USER, "password": config.PORTAL_PASS})
    check("login ok", r.status_code == 303)
    p.cookies.set("portal_session", r.cookies.get("portal_session"))
    check("invoice list renders 12 rows", p.get("/invoices").text.count("Download PDF") == 12)
    check("search filters", p.get("/invoices?q=aws").text.count("Download PDF") == 3)
    pdf = p.get("/invoices/AWS-1023/pdf")
    text = "".join(pg.extract_text() for pg in PdfReader(io.BytesIO(pdf.content)).pages)
    check("pdf has amount + due date", "INR 1,24,500" in text and "20/10/2026" in text)

with TestClient(finance_app, follow_redirects=False) as f:
    form = {"vendor": "AWS", "invoice_number": "AWS-1023", "amount": "124500", "due_date": "20/10/2026"}
    check("bad amount -> 422", f.post("/invoices", data={**form, "amount": "1,24,500"}).status_code == 422)
    check("bad date -> 422", f.post("/invoices", data={**form, "due_date": "2026-10-20"}).status_code == 422)
    check("first submit -> 503 (flaky)", f.post("/invoices", data=form).status_code == 503)
    r = f.post("/invoices", data=form)
    check("retry -> saved", r.status_code == 303)
    check("record visible in search", "AWS-1023" in f.get("/search?q=AWS-1023").text)
    check("duplicate -> 409", f.post("/invoices", data=form).status_code == 409)
    check("seeded dup (GCP-3012) -> 409", f.post("/invoices", data={**form, "invoice_number": "GCP-3012"}).status_code == 409)
    f.post("/admin/reset")
    check("reset removes new record", "AWS-1023" not in f.get("/").text)
print("\nAll environment checks passed.")
