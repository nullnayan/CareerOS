from typing import Protocol, Type, Any, Optional
from dataclasses import dataclass
from ..models import ResumeDoc, Dimension, Seniority, CheckResult, Anchor, Fix, Finding

from ..models import ResumeDoc, Dimension, Seniority, CheckResult, Anchor, Fix, Finding, JobTarget

Rubric = Any

class Check(Protocol):
    id: str
    dimension: Dimension
    requires_jd: bool
    applies_to: frozenset[Seniority]
    
    def run(self, doc: ResumeDoc, jd: Optional[JobTarget], rubric: Rubric) -> CheckResult:
        ...

# The universal registry of all active checks
CHECK_REGISTRY: dict[str, Check] = {}

ALL_SENIORITIES = frozenset(["student", "entry", "mid", "senior", "exec"])

def register(cls: Type[Check]) -> Type[Check]:
    """Decorator to register a check into the global scoring engine."""
    instance = cls()
    if instance.id in CHECK_REGISTRY:
        raise ValueError(f"Duplicate check ID registered: {instance.id}")
    CHECK_REGISTRY[instance.id] = instance
    return cls

# Helpers for checks
def build_result(check_id: str, score: float | None, findings: list[Finding], evidence: dict[str, Any]) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        score=score,
        findings=tuple(findings),
        evidence=evidence
    )
