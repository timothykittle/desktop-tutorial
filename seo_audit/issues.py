"""Shared issue/result model used by every checker."""

from dataclasses import dataclass, field

CRITICAL = "CRITICAL"
WARNING = "WARNING"
NOTICE = "NOTICE"
PASSED = "PASSED"

SEVERITY_WEIGHT = {CRITICAL: 10, WARNING: 4, NOTICE: 1}


@dataclass
class Issue:
    severity: str          # CRITICAL / WARNING / NOTICE / PASSED
    category: str          # e.g. "Title Tags", "Backlinks"
    message: str           # what is wrong (or right)
    url: str = ""          # page it applies to ("" = site-wide)
    fix: str = ""          # how to fix it, ready to act on

    def as_dict(self):
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "url": self.url,
            "fix": self.fix,
        }


@dataclass
class SectionResult:
    """Result of one audit section (on-page, technical, off-page...)."""
    name: str
    issues: list = field(default_factory=list)
    data: dict = field(default_factory=dict)   # extra structured data for the report

    def add(self, severity, category, message, url="", fix=""):
        self.issues.append(Issue(severity, category, message, url, fix))

    @property
    def score(self) -> int:
        """0-100 score: start at 100, subtract weighted penalties."""
        penalty = sum(SEVERITY_WEIGHT.get(i.severity, 0) for i in self.issues
                      if i.severity != PASSED)
        return max(0, 100 - penalty)

    def counts(self):
        out = {CRITICAL: 0, WARNING: 0, NOTICE: 0, PASSED: 0}
        for issue in self.issues:
            out[issue.severity] = out.get(issue.severity, 0) + 1
        return out
