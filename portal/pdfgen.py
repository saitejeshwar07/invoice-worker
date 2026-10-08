"""Generate realistic invoice PDFs with reportlab."""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from utils import inr
from portal.data import INVOICES

PDF_DIR = Path(__file__).parent / "pdfs"


def make_pdf(inv: dict, path: Path):
    total = inv["amount"]
    sub = round(total / 1.18)
    gst = total - sub
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, h - 70, f"{inv['vendor']} INDIA")
    c.setFont("Helvetica", 11)
    c.drawString(50, h - 90, "TAX INVOICE")
    y = h - 140
    rows = [
        ("Vendor", inv["vendor"]),
        ("Invoice Number", inv["invoice_number"]),
        ("Invoice Date", inv["date"]),
        ("Due Date", inv["due"]),
        ("Bill To", "ABC Technologies Pvt Ltd, Bengaluru"),
        ("Description", inv["desc"]),
    ]
    for k, v in rows:
        c.setFont("Helvetica-Bold", 11); c.drawString(50, y, f"{k}:")
        c.setFont("Helvetica", 11); c.drawString(170, y, v)
        y -= 22
    y -= 14
    for k, v in [("Subtotal", f"INR {inr(sub)}"), ("GST (18%)", f"INR {inr(gst)}")]:
        c.setFont("Helvetica", 11); c.drawString(50, y, k); c.drawRightString(w - 50, y, v); y -= 20
    c.line(50, y + 8, w - 50, y + 8)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y - 12, "Total Amount Due")
    c.drawRightString(w - 50, y - 12, f"INR {inr(total)}")
    c.setFont("Helvetica", 9)
    c.drawString(50, 60, "Payment terms: bank transfer by due date. This is a computer generated mock invoice.")
    c.save()


def generate_all():
    PDF_DIR.mkdir(exist_ok=True)
    for inv in INVOICES:
        make_pdf(inv, PDF_DIR / f"{inv['invoice_number']}.pdf")
