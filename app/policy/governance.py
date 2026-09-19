"""Policy governance: a version is not publishable unless the set passes.

Spec section 4.5: "Regression set of 40 cases ... A version cannot be
published unless all 40 pass." This module is the enforcement point; today
the only publish path is `app.store.seed`, which downgrades the version to
`draft` when the report is not clean.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .policy import compile_policy
from .regression_set import REGRESSION_SET, check, run_all


class PolicyNotPublishable(Exception):
    """Raised when a policy version is published with failing cases."""

    def __init__(self, version: int, failures: dict[str, list[str]]):
        self.version = version
        self.failures = failures
        detail = "; ".join(
            f"{case_id}: {', '.join(problems)}"
            for case_id, problems in list(failures.items())[:5]
        )
        super().__init__(
            f"policy v{version} failed {len(failures)}/{len(REGRESSION_SET)} "
            f"regression cases ({detail})"
        )


@dataclass
class RegressionReport:
    version: int
    total: int
    failures: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        passed = self.total - len(self.failures)
        return f"{passed}/{self.total} regression cases pass"


def regression_report(version: int, cases=None) -> RegressionReport:
    """Run the regression set against the compiled policy for *version*."""
    policy = compile_policy(version)
    results = run_all(policy) if cases is None else {
        case.id: check(case, policy) for case in cases
    }
    return RegressionReport(
        version=version,
        total=len(results),
        failures={k: v for k, v in results.items() if v},
    )


def assert_publishable(version: int, cases=None) -> RegressionReport:
    """Return a clean report, or raise PolicyNotPublishable."""
    report = regression_report(version, cases=cases)
    if not report.ok:
        raise PolicyNotPublishable(version, report.failures)
    return report
