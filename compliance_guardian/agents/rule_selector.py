"""Utility to load and manage domain-specific compliance rules."""


from __future__ import annotations
__version__ = "0.2.1"


import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer as WatchdogObserver
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from watchdog.observers import Observer
else:  # pragma: no cover
    Observer = WatchdogObserver
import typer

from compliance_guardian.utils.models import Rule, RuleSummary


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class RuleLoadError(Exception):
    """Custom error raised when rule loading fails."""


class _RuleFileHandler(FileSystemEventHandler):
    """Internal handler to reload rules on file modification."""

    def __init__(self, selector: "RuleSelector") -> None:
        self.selector = selector
        super().__init__()

    def on_modified(self, event) -> None:  # pragma: no cover
        """Handle file modification events."""
        path = Path(event.src_path)
        if path.suffix == ".json" and path.parent == self.selector.rules_dir:
            domain = path.stem
            LOGGER.info("Detected change in %s; reloading rules", path)
            try:
                self.selector.reload(domain)
            except Exception as exc:  # pragma: no cover - log unexpected
                LOGGER.error("Failed to reload %s: %s", domain, exc)


class RuleSelector:
    """Loader and cache for compliance rule sets.

    This class loads rules from ``config/rules/{domain}.json`` and keeps an in
    memory cache. Files are watched using ``watchdog`` and are hot reloaded
    when changed.
    """

    def __init__(
        self,
        rules_dir: Optional[Path] = None,
        summary_dir: Optional[Path] = None,
    ) -> None:
        default_dir = Path(__file__).resolve().parents[1] / "config" / "rules"
        self.rules_dir = rules_dir or default_dir
        default_summary = self.rules_dir.parent / "rules_summary"
        self.summary_dir = summary_dir or default_summary
        self._cache: Dict[str, List[Rule]] = {}
        self._summary_cache: Dict[str, List[RuleSummary]] = {}
        self._versions: Dict[str, str] = {}
        self._observer: Optional[Any] = None
        self._start_watcher()

    # ------------------------------------------------------------
    def _start_watcher(self) -> None:
        """Start watchdog observer to auto reload rules."""
        if self._observer:
            return
        handler = _RuleFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(
            handler,
            str(self.rules_dir),
            recursive=False,
        )
        self._observer.start()
        LOGGER.info("Started watchdog observer on %s", self.rules_dir)

    # ------------------------------------------------------------
    def _strip_comments(self, data: str) -> str:
        """Remove comment lines starting with '#', '//' or C-style blocks."""
        lines = []
        in_block = False
        for line in data.splitlines():
            stripped = line.strip()
            if stripped.startswith("/*"):
                in_block = True
                continue
            if in_block:
                if stripped.endswith("*/"):
                    in_block = False
                continue
            if stripped.startswith("//") or stripped.startswith("#"):
                continue
            lines.append(line)
        return "\n".join(lines)

    # ------------------------------------------------------------
    def _load_file(self, domain: str) -> List[Rule]:
        """Load rules for ``domain`` from JSON file.

        Args:
            domain: Domain name matching a file in the rules directory.

        Returns:
            List of valid :class:`Rule` objects.

        Raises:
            RuleLoadError: If the file cannot be parsed.
        """
        path = self.rules_dir / f"{domain}.json"
        if not path.exists():
            raise RuleLoadError(f"Rule file not found: {path}")

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(self._strip_comments(raw))
        except Exception as exc:
            raise RuleLoadError(f"Failed to parse {path}: {exc}") from exc

        file_version = "0.0.0"
        if isinstance(data, dict):
            file_version = str(data.get("version", "0.0.0"))
            entries = data.get("rules", [])
        elif isinstance(data, list):
            entries = data
        else:
            raise RuleLoadError(
                f"Rule file {path} must contain a list or object")

        rules: List[Rule] = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                LOGGER.error(
                    "Invalid rule entry at index %s: not an object",
                    idx,
                )
                continue
            if "domain" not in entry:
                entry["domain"] = domain
            if "category" not in entry:
                entry["category"] = "generic" if domain == "generic" else "domain"
            try:
                rule = Rule.from_dict(entry)
                rules.append(rule)
            except ValueError as exc:
                LOGGER.error(
                    "Skipping rule %s due to validation error: %s",
                    idx,
                    exc,
                )
        self._versions[domain] = file_version
        LOGGER.info(
            "Loaded %d rules for domain %s (version %s)",
            len(rules),
            domain,
            file_version,
        )
        return rules

    # ------------------------------------------------------------
    def _load_summary_file(self, domain: str) -> List[RuleSummary]:
        """Load lightweight rule summaries for ``domain``."""

        path = self.summary_dir / f"{domain}.json"
        if not path.exists():
            raise RuleLoadError(f"Rule summary file not found: {path}")

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(self._strip_comments(raw))
        except Exception as exc:
            raise RuleLoadError(f"Failed to parse {path}: {exc}") from exc

        if isinstance(data, dict):
            entries = data.get("rules", [])
        elif isinstance(data, list):
            entries = data
        else:
            raise RuleLoadError(
                f"Rule summary file {path} must contain a list or object"
            )

        summaries: List[RuleSummary] = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                LOGGER.error(
                    "Invalid rule summary at index %s: not an object", idx
                )
                continue
            try:
                summaries.append(RuleSummary(**entry))
            except Exception as exc:
                LOGGER.error(
                    "Skipping rule summary %s due to validation error: %s",
                    idx,
                    exc,
                )
        return summaries

    # ------------------------------------------------------------
    def load(self, domain: str) -> List[Rule]:
        """Return rules for a domain, loading them if necessary."""
        if domain not in self._cache:
            self._cache[domain] = self._load_file(domain)
        return self._cache[domain]

    # ------------------------------------------------------------
    def load_prompt_rules(self, domain: str) -> List[RuleSummary]:
        """Return lightweight rules for LLM context."""

        if domain not in self._summary_cache:
            self._summary_cache[domain] = self._load_summary_file(domain)
        return self._summary_cache[domain]

    # ------------------------------------------------------------
    def get_version(self, domain: str) -> str:
        """Return the version string for ``domain`` rules."""
        return self._versions.get(domain, "0.0.0")

    # ------------------------------------------------------------
    def reload(self, domain: str) -> None:
        """Force reload of rules for a domain."""
        self._cache[domain] = self._load_file(domain)
        LOGGER.info("Reloaded rules for domain %s", domain)

    # ------------------------------------------------------------
    def get_rule(self, domain: str, rule_id: str) -> Optional[Rule]:
        """Return full rule details for ``rule_id`` in ``domain``."""

        for rule in self.load(domain):
            if rule.rule_id == rule_id:
                return rule
        return None

    # ------------------------------------------------------------
    def search(self, domain: str, term: str) -> List[Rule]:
        """Search loaded rules containing ``term`` in description."""
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        results: List[Rule] = []
        for rule in self.load(domain):
            if pattern.search(rule.description):
                results.append(rule)

        LOGGER.info(
            "Found %d rules matching '%s' in domain %s",
            len(results),
            term,
            domain,
        )
        return results

    # ------------------------------------------------------------
    def aggregate(
        self, domains: List[str], user_rules: Optional[List[Rule]] = None
    ) -> Tuple[List[Rule], str]:
        """Return combined rules for ``domains`` plus generics and users."""

        all_rules: List[Rule] = []
        versions: List[str] = []
        try:
            generics = self.load("generic")
            all_rules.extend(generics)
            versions.append(self.get_version("generic"))
        except RuleLoadError:
            LOGGER.info("No generic rule file found")
        for dom in domains:
            try:
                dom_rules = self.load(dom)
                all_rules.extend(dom_rules)
                versions.append(self.get_version(dom))
            except RuleLoadError:
                LOGGER.warning("No rules for domain %s", dom)
        if user_rules:
            for r in user_rules:
                r.category = "user"
                all_rules.append(r)
        rulebase_version = "|".join(versions) or "0.0.0"
        return all_rules, rulebase_version

    # ------------------------------------------------------------
    def validate(self, domain: str) -> List[str]:
        """Validate rules for a domain and return error messages."""
        path = self.rules_dir / f"{domain}.json"
        errors: List[str] = []
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(self._strip_comments(raw))
        except Exception as exc:
            errors.append(f"Failed to parse {path}: {exc}")
            return errors
        if isinstance(data, dict):
            entries = data.get("rules", [])
        elif isinstance(data, list):
            entries = data
        else:
            errors.append(f"File {path} must contain a list or object")
            return errors
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f"Entry {idx} is not an object")
                continue
            if "domain" not in entry:
                entry["domain"] = domain
            if "category" not in entry:
                entry["category"] = "generic" if domain == "generic" else "domain"
            try:
                Rule.from_dict(entry)
            except ValueError as exc:
                errors.append(f"Entry {idx} validation error: {exc}")
        return errors


app = typer.Typer(help="CLI for inspecting compliance rules")


def _build_selector() -> RuleSelector:
    """Create a new ``RuleSelector`` instance."""
    return RuleSelector()


@app.command()
def print_rules(domain: str) -> None:
    """Print all rules for a domain."""
    selector = _build_selector()
    for rule in selector.load(domain):
        typer.echo(rule.json())


@app.command()
def search(domain: str, term: str) -> None:
    """Search rule descriptions for a term."""
    selector = _build_selector()
    for rule in selector.search(domain, term):
        typer.echo(rule.json())


@app.command()
def validate(domain: str) -> None:
    """Validate rule file and display any errors."""
    selector = _build_selector()
    errors = selector.validate(domain)
    if errors:
        for err in errors:
            typer.echo(f"Error: {err}")
        raise typer.Exit(code=1)
    typer.echo("All rules valid")


if __name__ == "__main__":
    selector = _build_selector()
    for d in ("scraping", "finance", "medical"):
        print(f"\nDomain: {d}")
        for r in selector.load(d):
            print(r.json())
