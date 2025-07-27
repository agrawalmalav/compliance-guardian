# Compliance Guardian Agent

[![Coverage](https://img.shields.io/badge/coverage-80%25-green.svg)](docs/index.html)

A modular research project demonstrating how an automated agent can guard
large language model (LLM) pipelines using domain specific compliance rules.
The system was developed as part of an MSc thesis on trustworthy AI.

```
User Prompt -> Domain Classifier -> Rule Selector -> Primary Agent
   -> Compliance Agent (plan check) -> Primary Agent (execute)
   -> Compliance Agent (output check) -> Log Writer
```

The diagram above shows the high level data flow. A user prompt is first
classified into a domain. Rules for that domain are loaded and used to vet the
execution plan and final output. All decisions are logged for audit.

## Features

- Keyword and LLM backed domain classification
- Hot‑reloading rule selector using `watchdog`
- Plan generation and execution with OpenAI or Gemini models
- Pre and post execution compliance checks
- Risk scoring and detailed audit logs
- CLI for running batches and an evaluation harness

## Tech Stack

- Python 3.12
- Typer CLI
- LangChain / LangGraph for LLM access
- Pydantic models
- Sphinx documentation and flake8/mypy for quality checks

## Quickstart

```bash
pip install -r requirements.txt
python main.py run --prompt "Scrape article titles from example.com" --session-id demo
```

Audit logs appear under `logs/` and a governance report under `reports/`.

## Running Tests and Demo

Run static checks and the demo scenarios:

```bash
flake8
mypy compliance_guardian
pytest -q
python eval.py
```

See `notebooks/Demo.ipynb` for an interactive walkthrough.

Documentation is built with Sphinx:

```bash
cd docs
sphinx-build -b html . _build
```

The generated HTML will be available in `docs/_build`.

## Adding Rules or Domains

Rule files live in `compliance_guardian/config/rules/DOMAIN.json`. Each rule
follows the schema defined in `utils/models.py`. Add a new JSON file for a new
domain and the `RuleSelector` will pick it up automatically. Use
`python -m compliance_guardian.utils.legal_to_json` to convert legal clauses
into structured rules.

## External Datasets and Legal References

- **PrivacyQA** – <https://github.com/cisnlp/privacyQA> (CC BY 4.0)
  Used for privacy policy question answering experiments.
- **HH-RLHF** – <https://huggingface.co/datasets/Anthropic/hh-rlhf> (Apache 2.0)
  Helpful/Harmless conversations for tuning safety prompts.
- **OPP-115** – <https://usableprivacy.org/data> (CC BY-SA 3.0)
  Collection of annotated privacy policies.

The rule files include citations to GDPR, HIPAA, PCI DSS and other regulations
within the `legal_reference` field for traceability.

Full API documentation is available in the [docs](docs/index.rst) directory.
