# Company context: ABC Technologies Pvt Ltd (Accounts Payable team)

## Systems you can use
- **Vendor Invoice Portal** - {{PORTAL_URL}}/login . Username `{{PORTAL_USER}}`, password `{{PORTAL_PASS}}`.
  Lists vendor invoices (vendor, invoice number, invoice date) with a PDF each. The list is NOT sorted by date.
  The PDF is the source of truth for amount and due date.
- **Finance System** (system of record) - {{FINANCE_URL}}/ . No login. Dashboard, search, and an "Add Invoice" form.

## Procedures
- "Process an invoice" = find the vendor's latest invoice (most recent *invoice date*), read its PDF, record vendor,
  invoice number, total amount and due date in the Finance System, and confirm it is stored correctly.
- Never create duplicate records. If the Finance System already holds the invoice, compare the existing record with the
  PDF and report whether it matches instead of re-entering it.
- Amounts are in INR. Use the total amount due (including GST).

## Policy
- Submissions with an amount above INR {{THRESHOLD}} need human approval (the runtime will pause and ask automatically).
- If the request is ambiguous or missing required information (e.g. no vendor named), ask the user before acting.
