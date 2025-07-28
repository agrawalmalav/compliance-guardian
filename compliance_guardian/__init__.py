"""Compliance Guardian package

This package automatically loads environment variables from a ``.env``
file if present. API keys such as ``OPENAI_API_KEY`` and ``GEMINI_API_KEY``
can therefore be placed in that file for local development.
"""

from pathlib import Path

try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv

    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
except Exception:  # pragma: no cover - missing dotenv
    pass
