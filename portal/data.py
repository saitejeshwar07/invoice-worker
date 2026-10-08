"""Fake vendor invoices (deliberately NOT sorted by date, so 'latest' needs reasoning)."""
INVOICES = [
    {"vendor": "AWS", "invoice_number": "AWS-1022", "date": "05/09/2026", "due": "20/09/2026", "amount": 121350, "desc": "Cloud infrastructure - August 2026"},
    {"vendor": "Microsoft", "invoice_number": "MS-2092", "date": "04/09/2026", "due": "19/09/2026", "amount": 42000, "desc": "Microsoft 365 licences - September"},
    {"vendor": "Google Cloud", "invoice_number": "GCP-3012", "date": "02/10/2026", "due": "17/10/2026", "amount": 75000, "desc": "Google Cloud Platform usage - September"},
    {"vendor": "AWS", "invoice_number": "AWS-1023", "date": "08/10/2026", "due": "20/10/2026", "amount": 124500, "desc": "Cloud infrastructure - September 2026"},
    {"vendor": "Datadog", "invoice_number": "DD-7001", "date": "28/08/2026", "due": "30/09/2026", "amount": 18600, "desc": "Observability platform - August"},
    {"vendor": "Microsoft", "invoice_number": "MS-2093", "date": "07/10/2026", "due": "25/10/2026", "amount": 8500000, "desc": "Enterprise agreement annual true-up"},
    {"vendor": "Google Cloud", "invoice_number": "GCP-3011", "date": "02/09/2026", "due": "17/09/2026", "amount": 72000, "desc": "Google Cloud Platform usage - August"},
    {"vendor": "AWS", "invoice_number": "AWS-1021", "date": "01/08/2026", "due": "15/08/2026", "amount": 118200, "desc": "Cloud infrastructure - July 2026"},
    {"vendor": "Zoom", "invoice_number": "ZM-501", "date": "03/10/2026", "due": "18/10/2026", "amount": 9400, "desc": "Zoom Workplace - Q4"},
    {"vendor": "Microsoft", "invoice_number": "MS-2091", "date": "03/08/2026", "due": "18/08/2026", "amount": 42000, "desc": "Microsoft 365 licences - August"},
    {"vendor": "Datadog", "invoice_number": "DD-7002", "date": "29/09/2026", "due": "30/10/2026", "amount": 19250, "desc": "Observability platform - September"},
    {"vendor": "Google Cloud", "invoice_number": "GCP-3010", "date": "01/08/2026", "due": "16/08/2026", "amount": 69800, "desc": "Google Cloud Platform usage - July"},
]
