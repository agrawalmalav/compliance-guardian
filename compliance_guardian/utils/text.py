import re

_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$", re.IGNORECASE)


def _strip_code_fence(text: str) -> str:
    """Return ``text`` without surrounding Markdown code fences."""
    text = text.strip()
    match = _CODE_FENCE_RE.match(text)
    if match:
        return match.group(1).strip()
    return text
