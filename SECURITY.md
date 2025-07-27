# Security Overview

This document outlines the threat model, log handling and other
security practices for the **Compliance Guardian Agent** project.
It is written for MSc/industry audiences.

## Threat Model
- **Data handled**: user prompts, compliance plans, policy rules,
  audit decisions and generated outputs. The system does not store
  real personal data outside of demo mode. All processing occurs in
  memory or temporary files under `logs/` and `reports/`.
- **Risks**: exposure of sensitive prompts or model outputs,
  tampering with audit logs, misuse of API credentials or models,
  and unanticipated LLM behaviours.
- **Protections**:
  - Logs are rotated and stored with restricted permissions (see below).
  - API keys are kept in environment variables and never committed to
    the repository.
  - Rule versions and agent versions are embedded in each audit entry
    to support reproducibility.
  - Access to the system should be limited to authorised researchers
    or developers.

## Log File Security
- Audit logs are appended to `logs/audit_log.jsonl` using the
  utilities in `compliance_guardian.utils.log_writer`.
- When the file exceeds 5&nbsp;MB it is renamed to
  `audit_log_<N>.jsonl` and a fresh log is created.
- Logs and reports are kept under `logs/` and `reports/` with
  file permissions restricted to project maintainers.
- Only maintainers and auditors performing compliance reviews should
  access these files. Logs may contain prompts or explanations that
  reveal sensitive business context.

## Handling Personal Data
- The system is designed to run **without** processing real personal
  data. Example prompts in the evaluation dataset only contain
  synthetic or pseudonymous information.
- In the rare case that a demo requires real data, users must enable
  a dedicated "demo" flag and ensure all outputs are promptly
  redacted or pseudonymised before storage.
- When logs are exported for research, names, emails or account
  numbers should be replaced with placeholders (e.g. `USER123`).

## Secrets and API Keys
- OpenAI or Gemini model keys **must** be supplied via environment
  variables such as `OPENAI_API_KEY` or
  `GOOGLE_APPLICATION_CREDENTIALS`.
- Do **not** hard-code credentials or add them to configuration files.
  Local `.env` files may be used but must never be committed to Git.

## Known Limitations
- Large language models may still produce inaccurate or unsafe text.
  Rule coverage is limited to the example domains in
  `compliance_guardian/config/rules/`.
- Real-time monitoring of model outputs is best effort and may miss
  nuanced violations.
- The project does not implement end‑to‑end encryption for log files;
  if strict confidentiality is required, store logs on encrypted disk.

## Responsible Disclosure
If you discover a security vulnerability, please email
`security@example.com` with:

1. Description of the issue
2. Steps to reproduce
3. Potential impact

We will respond within 5 business days and coordinate remediation.

## Further Reading
- [GDPR text](https://gdpr-info.eu/)
  – authoritative source on EU data protection requirements.
- [ISO/IEC&nbsp;27001](https://www.iso.org/standard/54534.html)
  – international standard for information security management.
