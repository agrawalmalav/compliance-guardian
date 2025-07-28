"""Risk scoring utilities for compliance actions."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from .models import ComplianceDomain, PlanSummary, Rule, SeverityLevel

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEFAULT_SCORES = {
    SeverityLevel.CRITICAL: 100,
    SeverityLevel.HIGH: 100,
    SeverityLevel.MEDIUM: 50,
    SeverityLevel.LOW: 10,
}


# ---------------------------------------------------------------------------


def score_risk(
    rule: Rule,
    plan: PlanSummary,
    matrix: Optional[Dict[str, Dict[str, int]]] = None,
) -> int:
    """Return a numerical risk score for ``rule`` within ``plan`` context.

    Parameters
    ----------
    rule:
        Compliance rule being evaluated.
    plan:
        Execution plan potentially impacted by ``rule``.
    matrix:
        Optional override matrix mapping ``domain`` -> ``rule_id`` -> score.

    Returns
    -------
    int
        Risk score between 0 and 100 where higher indicates more risk.
    """

    domain = (
        plan.domain.value
        if isinstance(plan.domain, ComplianceDomain)
        else str(plan.domain)
    )
    if matrix and domain in matrix and rule.rule_id in matrix[domain]:
        score = matrix[domain][rule.rule_id]
        LOGGER.info(
            "Risk override: domain=%s rule=%s score=%s",
            domain,
            rule.rule_id,
            score,
        )
        return score

    score = DEFAULT_SCORES.get(rule.severity, 10)
    LOGGER.info(
        "Calculated risk %s for rule %s (severity=%s, domain=%s)",
        score,
        rule.rule_id,
        rule.severity,
        domain,
    )
    return score
