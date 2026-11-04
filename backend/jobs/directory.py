"""Employer boards with public board-page evidence; live health is separate.

Candidates in registry.EMPLOYERS without verified mappings stay candidates.
Adding a directory entry does not connect it or modify workspace preferences.
"""
COMPANY_BOARDS = [
    ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "canonical", "Canonical"),
    ("greenhouse", "point72", "Point72"),
    ("lever", "ion", "ION Group"),
    ("ashby", "Ashby", "Ashby"),
    ("workable", "digitals", "Digitals AI Inc"),
    ("greenhouse", "razorpaysoftwareprivatelimited", "Razorpay Software Private Limited"),
    ("lever", "meesho", "Meesho"),
    ("greenhouse", "gravitonresearchcapital", "Graviton Research Capital LLP"),
    ("ashby", "aistudio", "AiStudio"),
    ("smartrecruiters", "Freshworks", "Freshworks"),
    ("greenhouse", "twilio", "Twilio"),
    ("lever", "cred", "CRED"),
    ("smartrecruiters", "ServiceNow", "ServiceNow"),
    ("greenhouse", "microsoftcorporation", "Microsoft AI"),
]

# Primary board pages reviewed on 2 November; these new mappings have not been
# fetched by CareerOS against the personal workspace and are opt-in suggestions.
NEW_MAPPINGS = {("greenhouse", "twilio"), ("lever", "cred"),
                ("smartrecruiters", "ServiceNow"), ("greenhouse", "microsoftcorporation")}


def company_directory():
    bases = {"greenhouse": "https://job-boards.greenhouse.io/", "lever": "https://jobs.lever.co/",
             "ashby": "https://jobs.ashbyhq.com/", "workable": "https://apply.workable.com/",
             "smartrecruiters": "https://careers.smartrecruiters.com/"}
    return [{"provider": provider, "board": board, "company": company, "url": bases[provider] + board,
             "verified_for_setup": (provider, board) != ("lever", "meesho") and (provider, board) not in NEW_MAPPINGS,
             "mapping_evidence": bases[provider] + board,
             "mapping_reviewed_at": "2026-11-02" if (provider, board) in NEW_MAPPINGS else "2026-11-01",
             "mapping_scope": "Microsoft AI only, not all Microsoft careers" if board == "microsoftcorporation" else "employer board",
             "live_collector_health": "never_checked" if (provider, board) in NEW_MAPPINGS else "see configured source"}
            for provider, board, company in COMPANY_BOARDS]
