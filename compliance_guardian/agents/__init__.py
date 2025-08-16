"""Agent components for the Compliance Guardian pipeline.

This package exposes the individual agent modules directly at the package
level so callers can write imports such as ``from compliance_guardian.agents
import joint_extractor``.  The modules are loaded lazily to avoid importing
heavy dependencies unless they are actually needed.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "compliance_agent",
    "domain_classifier",
    "joint_extractor",
    "primary_agent",
    "rule_selector",
    "output_validator",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - simple import wrapper
    """Dynamically load agent submodules on first access.

    This keeps imports lightweight while still supporting direct access via
    ``from compliance_guardian.agents import <module>``.  ``__all__`` defines
    the set of supported names; anything else raises ``AttributeError``.
    """

    if name in __all__:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

