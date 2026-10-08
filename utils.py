"""Shared helpers: INR formatting, amount parsing, tiny HTML layout for the mock apps."""
import html
import re


def inr(n) -> str:
    """124500 -> '1,24,500' (Indian digit grouping)."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def money(a) -> str:
    a = float(a)
    return "₹" + (inr(a) if a.is_integer() else f"{a:,.2f}")


def parse_amount(v):
    """Lenient parse used by the approval policy: '₹85,00,000' -> 8500000.0."""
    if v is None:
        return None
    s = re.sub(r"(?i)[₹,\s]|rs\.?|inr", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


esc = html.escape

BASE_CSS = """
*{box-sizing:border-box}body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f8;color:#1b2430}
header{background:#1b2430;color:#fff;padding:14px 28px;display:flex;gap:24px;align-items:center}
header b{font-size:18px}header a{color:#9fc5ff;text-decoration:none}
main{max-width:980px;margin:28px auto;padding:0 20px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;margin-top:16px}
th,td{padding:10px 14px;text-align:left;border-bottom:1px solid #e6e9ed;font-size:14px}th{background:#eef1f5}
input{padding:9px 10px;border:1px solid #c5ccd6;border-radius:6px;font-size:14px;margin:4px 0 12px;width:100%}
.inline input{width:260px;margin:0 6px 0 0}
button,.btn{background:#2f6fed;color:#fff;border:0;padding:9px 16px;border-radius:6px;font-size:14px;cursor:pointer;text-decoration:none;display:inline-block}
.card{background:#fff;padding:22px;border-radius:8px;max-width:460px}label{font-size:13px;font-weight:600}
.error{background:#fdecea;color:#a12622;padding:12px 14px;border-radius:6px;margin:14px 0}
.success{background:#e7f6ec;color:#17692f;padding:12px 14px;border-radius:6px;margin:14px 0}
.muted{color:#69758a;font-size:13px}dl{display:grid;grid-template-columns:160px 1fr;gap:8px}dt{font-weight:600}
"""


def layout(title: str, brand: str, nav: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title>"
            f"<style>{BASE_CSS}</style></head><body><header><b>{esc(brand)}</b>{nav}</header>"
            f"<main>{body}</main></body></html>")
