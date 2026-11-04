from typing import Callable, Any
from ..models import ResumeDoc, Finding, JobTarget

# (predicate, points, reason, charged_elsewhere)
LEDGER = [
  (lambda d, j: d.layout.is_scanned,        18, "Scanned/image PDF",                False),
  (lambda d, j: d.layout.page_count >= 3,   12, "Three or more pages",              False),
  (lambda d, j: d.layout.page_count > 1 and d.profile.seniority in ["student", "entry"], 6, "Exceeds page budget for seniority", False),
  (lambda d, j: d.layout.has_columns,        8, "Multi-column layout",              False),
  (lambda d, j: getattr(d, 'gap_months', lambda: 0)() > 18, 5, "Extended unexplained gap", False),
]

LEDGER_CAP = 30

class PenaltyLedger:
    def __init__(self):
        self.applied: list[Finding] = []
        
    def evaluate(self, doc: ResumeDoc, jd: JobTarget | None) -> list[Finding]:
        self.applied = []
        total_charged = 0.0
        
        for predicate, points, reason, charged_elsewhere in LEDGER:
            if not charged_elsewhere and predicate(doc, jd):
                # Ensure we don't exceed the LEDGER_CAP
                actual_charge = min(points, LEDGER_CAP - total_charged)
                if actual_charge > 0:
                    total_charged += actual_charge
                    self.applied.append(
                        Finding(
                            check_id="ledger." + reason.lower().replace(" ", "_").replace("/", "_"),
                            severity="high" if actual_charge >= 10 else "medium",
                            title=reason,
                            detail=reason,
                            anchor=None,
                            fix=None,
                            points=float(actual_charge)
                        )
                    )
                    
                if total_charged >= LEDGER_CAP:
                    break
                    
        return self.applied
