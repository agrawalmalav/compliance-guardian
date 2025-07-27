"""Compliance Guardian typed models for GDPR, ISO, and EU regulatory workflows.

This module defines Pydantic models used throughout the Compliance Guardian
Agent to ensure structured data handling when performing compliance auditing for
large language model (LLM) pipelines. The models cover rule definitions, audit
logging, planning summaries, and session context tracking. These structures
facilitate rigorous reproducibility that aligns with EU regulations.

Example:
    >>> from compliance_guardian.utils.models import Rule, RuleType, SeverityLevel, ComplianceDomain
    >>> rule = Rule(
    ...     rule_id="R001",
    ...     description="Redact personal data from outputs",
    ...     type=RuleType.SECURITY,
    ...     severity=SeverityLevel.HIGH,
    ...     domain=ComplianceDomain.GDPR,
    ...     pattern=r"\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b",
    ...     keywords=["email"],
    ... )
    >>> rule_dict = rule.to_dict()
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError


class RuleType(str, Enum):
    """Enumeration of rule categories."""

    CONTENT = "content"
    SECURITY = "security"
    PRIVACY = "privacy"
    PROCEDURAL = "procedural"


class SeverityLevel(str, Enum):
    """Enumeration of rule severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplianceDomain(str, Enum):
    """Enumeration of compliance domains."""

    GDPR = "gdpr"
    ISO27001 = "iso27001"
    EU = "eu"
    OTHER = "other"


class Rule(BaseModel):
    """Definition of a single compliance rule.

    Attributes:
        rule_id: Unique identifier for this rule.
        description: Human-readable rule description.
        type: Category of the rule.
        severity: Impact severity if violated.
        domain: Compliance domain to which this rule belongs.
        pattern: Optional regex pattern used for detection.
        keywords: Keywords associated with the rule.
        llm_instruction: Instruction for an LLM to comply with this rule.
        clause_mapping: Mapping of clause identifiers to text references.
        legal_reference: Optional legal citation linked to the rule.
        example_violation: Example text that violates the rule.
    """

    rule_id: str = Field(..., description="Unique identifier for this rule.")
    description: str = Field(..., description="Human-readable rule description.")
    type: RuleType = Field(..., description="Category of the rule.")
    severity: SeverityLevel = Field(..., description="Impact severity if violated.")
    domain: ComplianceDomain = Field(
        ..., description="Compliance domain to which this rule belongs."
    )
    pattern: Optional[str] = Field(
        None, description="Regex pattern used to detect rule violations."
    )
    keywords: List[str] = Field(
        default_factory=list, description="Keywords associated with the rule."
    )
    llm_instruction: Optional[str] = Field(
        None, description="Instruction for an LLM to comply with this rule."
    )
    clause_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of clause identifiers to text references.",
    )
    legal_reference: Optional[str] = Field(
        None, description="Legal citation linked to the rule."
    )
    example_violation: Optional[str] = Field(
        None, description="Example text that violates the rule."
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        """Instantiate a :class:`Rule` from a dictionary.

        Args:
            data: Dictionary containing rule information.

        Returns:
            Rule: Parsed rule object.

        Raises:
            ValueError: If validation fails.
        """

        try:
            return cls(**data)
        except ValidationError as exc:
            raise ValueError(f"Invalid Rule data: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this rule to a dictionary."""

        try:
            return self.dict()
        except Exception as exc:  # pragma: no cover - extremely unlikely
            raise ValueError(f"Unable to serialize Rule: {exc}") from exc


class AuditLogEntry(BaseModel):
    """Entry recording a compliance audit event.

    Attributes:
        timestamp: When the event occurred.
        rule_id: Identifier of the rule triggered.
        severity: Severity level of the event.
        action: Description of the action taken.
        input_text: Input text that led to the event.
        justification: Explanation for the chosen action.
        suggested_fix: Proposed fix for the violation.
        clause_id: Clause identifier referenced.
        risk_score: Numerical risk score.
        session_id: Identifier for the session associated.
        agent_stack: List of agents involved.
        rulebase_version: Version of the rulebase in use.
        execution_time: Time taken to execute in seconds.
    """

    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the event occurred."
    )
    rule_id: str = Field(..., description="Identifier of the triggered rule.")
    severity: SeverityLevel = Field(..., description="Severity level of the event.")
    action: str = Field(..., description="Description of the action taken.")
    input_text: str = Field(..., description="Input text that led to the event.")
    justification: str = Field(..., description="Explanation for the chosen action.")
    suggested_fix: Optional[str] = Field(
        None, description="Proposed fix for the violation."
    )
    clause_id: Optional[str] = Field(None, description="Clause identifier referenced.")
    risk_score: Optional[float] = Field(None, description="Numerical risk score.")
    session_id: str = Field(..., description="Identifier for the associated session.")
    agent_stack: List[str] = Field(
        default_factory=list, description="List of agents involved."
    )
    rulebase_version: Optional[str] = Field(
        None, description="Version of the rulebase in use."
    )
    execution_time: Optional[float] = Field(
        None, description="Time taken to execute in seconds."
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLogEntry":
        """Instantiate :class:`AuditLogEntry` from a dictionary.

        Args:
            data: Dictionary containing event information.

        Returns:
            AuditLogEntry: Parsed log entry.

        Raises:
            ValueError: If validation fails.
        """

        try:
            return cls(**data)
        except ValidationError as exc:
            raise ValueError(f"Invalid AuditLogEntry data: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this log entry to a dictionary."""

        try:
            return self.dict()
        except Exception as exc:  # pragma: no cover - extremely unlikely
            raise ValueError(f"Unable to serialize AuditLogEntry: {exc}") from exc


class PlanSummary(BaseModel):
    """Summary of an action plan for compliance.

    Attributes:
        action_plan: High-level plan of action.
        goal: Compliance or user goal.
        domain: Compliance domain for the plan.
        sub_actions: Sub-actions to perform.
        original_prompt: Original prompt that initiated the plan.
    """

    action_plan: str = Field(..., description="High-level plan of action.")
    goal: str = Field(..., description="Compliance or user goal.")
    domain: ComplianceDomain = Field(..., description="Compliance domain for the plan.")
    sub_actions: List[str] = Field(
        default_factory=list, description="Sub-actions to perform."
    )
    original_prompt: str = Field(
        ..., description="Original prompt that initiated the plan."
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanSummary":
        """Instantiate :class:`PlanSummary` from a dictionary."""
        try:
            return cls(**data)
        except ValidationError as exc:
            raise ValueError(f"Invalid PlanSummary data: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this plan summary to a dictionary."""
        try:
            return self.dict()
        except Exception as exc:  # pragma: no cover - extremely unlikely
            raise ValueError(f"Unable to serialize PlanSummary: {exc}") from exc


class SessionContext(BaseModel):
    """Context information for an ongoing session.

    Attributes:
        session_id: Unique identifier for the session.
        domain: Compliance domain governing the session.
        user_id: Identifier of the user.
        active_rules: List of active rule identifiers.
        risk_threshold: Threshold for acceptable risk.
        agent_versions: Versions of agents used during the session.
        intermediate_outputs: Outputs produced mid-execution.
    """

    session_id: str = Field(..., description="Unique identifier for the session.")
    domain: ComplianceDomain = Field(
        ..., description="Compliance domain governing the session."
    )
    user_id: str = Field(
        ..., description="Identifier of the user initiating the session."
    )
    active_rules: List[str] = Field(
        default_factory=list, description="List of active rule identifiers."
    )
    risk_threshold: float = Field(..., description="Threshold for acceptable risk.")
    agent_versions: Dict[str, str] = Field(
        default_factory=dict, description="Versions of agents used during the session."
    )
    intermediate_outputs: Dict[str, Any] = Field(
        default_factory=dict, description="Outputs produced mid-execution."
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        """Instantiate :class:`SessionContext` from a dictionary."""
        try:
            return cls(**data)
        except ValidationError as exc:
            raise ValueError(f"Invalid SessionContext data: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this session context to a dictionary."""
        try:
            return self.dict()
        except Exception as exc:  # pragma: no cover - extremely unlikely
            raise ValueError(f"Unable to serialize SessionContext: {exc}") from exc
