# coding: utf-8
"""Internationalisation utilities for translating compliance explanations.

This module provides helper functions to translate user facing or audit
explanations into different languages. The translation process attempts to use
any available provider in the following order:

1. **Google Cloud Translation API** if ``google.cloud.translate_v2`` is
   installed and the ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable is
   configured.
2. **OpenAI ChatCompletion API** if ``openai`` is installed and
   ``OPENAI_API_KEY`` is set.
3. The community ``googletrans`` package as a lightweight fall back.

If none of the providers are available or an error occurs, the original text is
returned and the issue is logged. A ``translation_source`` string
describing the provider and version used is included with each successful
translation so that log entries can be audited.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import AuditLogEntry, SessionContext

# Set up local logger
LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Paths reused from ``log_writer`` so that translated explanations end up in
# the same audit log file.
_BASE_DIR = Path(__file__).resolve().parents[1]
_LOG_DIR = _BASE_DIR / "logs"
_LOG_FILE = _LOG_DIR / "audit_log.jsonl"
_LOG_SIZE_LIMIT = 5 * 1024 * 1024  # 5 MB

# Unique identifier so that all translation events for the same run can be
# correlated with other log entries written by :mod:`log_writer`.
_RUN_HASH = hashlib.sha256(
    str(datetime.utcnow().timestamp()).encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------


def _rotate_logs() -> None:
    """Rotate the multilingual audit log when it exceeds the size limit."""
    try:
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size >= _LOG_SIZE_LIMIT:
            index = 1
            while (_LOG_DIR / f"audit_log_{index}.jsonl").exists():
                index += 1
            dest = _LOG_DIR / f"audit_log_{index}.jsonl"
            _LOG_FILE.rename(dest)
            LOGGER.info("Rotated audit log to %s", dest)
    except Exception as exc:  # pragma: no cover - filesystem differences
        LOGGER.exception("Failed rotating logs: %s", exc)


# ---------------------------------------------------------------------------


def translate_explanation(text: str, target_lang: str = "fr") -> str:
    """Translate ``text`` to ``target_lang`` using any available provider.

    The function first attempts to use the Google Cloud Translation API, then
    OpenAI's ChatCompletion API, and finally the open source ``googletrans``
    library. If all attempts fail it returns ``text`` unchanged.

    Parameters
    ----------
    text:
        Explanation text (assumed English) to translate.
    target_lang:
        ISO 639-1 language code to translate into. Defaults to ``"fr"`` for
        French.

    Returns
    -------
    str
        Translated text or ``text`` if translation was unavailable.

    The logger records the provider used for each translation attempt so that
    auditors can verify which system produced a given string.
    """

    provider = "unavailable"
    translated = text

    # --- Google Cloud Translation API -------------------------------------
    try:
        from google.cloud import translate_v2 as gtranslate  # type: ignore

        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            client = gtranslate.Client()
            result = client.translate(text, target_language=target_lang)
            translated = result.get("translatedText", text)
            provider = f"google-translate-v2/{result.get('model', 'api')}"
        else:
            raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS not set")
    except Exception as exc:  # pragma: no cover - optional dependency
        LOGGER.debug("Google translation not used: %s", exc)

    # --- OpenAI ChatCompletion API ---------------------------------------
    if translated == text:
        try:
            import openai  # type: ignore

            if os.getenv("OPENAI_API_KEY"):
                prompt = (
                    "Translate the following explanation to "
                    f"{target_lang}:\n\n{text}"
                )
                client = openai.OpenAI()
                resp = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                translated = (
                    resp.choices[0].message.content or ""
                ).strip()
                provider = "openai/gpt-3.5-turbo"
            else:
                raise RuntimeError("OPENAI_API_KEY not set")
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.debug("OpenAI translation failed: %s", exc)

    # --- googletrans fallback --------------------------------------------
    if translated == text:
        try:
            from googletrans import Translator  # type: ignore

            translator = Translator()
            result = translator.translate(text, dest=target_lang)
            translated = result.text
            provider = f"googletrans/{getattr(result, 'src', 'auto')}"
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.debug("googletrans failed: %s", exc)

    if translated == text:
        LOGGER.warning(
            "Translation unavailable; returning original text for %s",
            target_lang,
        )
    else:
        LOGGER.info(
            "Translated explanation via %s to %s",
            provider,
            target_lang,
        )
    return translated


# ---------------------------------------------------------------------------


def log_multilingual_explanation(
    log_entry: AuditLogEntry,
    translated_text: str,
    *,
    target_lang: str = "fr",
    translation_source: str,
    session: Optional[SessionContext] = None,
) -> None:
    """Store ``log_entry`` with ``translated_text`` in the audit log.

    The function mirrors :func:`log_writer.log_decision` but includes
    additional fields: ``translated_explanation`` (the translated text),
    ``translation_lang`` and ``translation_source``. This allows
    downstream consumers to reconstruct how and when a particular
    translation was produced.
    """

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _rotate_logs()

        record = log_entry.to_dict()
        record["run_hash"] = _RUN_HASH
        record["session_context"] = session.to_dict() if session else None
        record["timestamp"] = log_entry.timestamp.isoformat()
        record["translated_explanation"] = translated_text
        record["translation_lang"] = target_lang
        record["translation_source"] = translation_source

        with _LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        LOGGER.info(
            "Logged multilingual explanation for rule %s in %s",
            log_entry.rule_id,
            target_lang,
        )
    except Exception as exc:  # pragma: no cover - filesystem or serialization
        LOGGER.exception("Failed to log multilingual explanation: %s", exc)


# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - demonstration
    SAMPLE = "Data will be retained for only as long as necessary."
    for lang in ["fr", "de", "hi", "zh"]:
        t = translate_explanation(SAMPLE, lang)
        print(f"{lang}: {t}")
