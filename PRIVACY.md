# Privacy Overview

This document describes how the **Compliance Guardian Agent**
collects, stores and deletes data. It is intended for researchers
and industry practitioners evaluating the system.

## Data Collected
- **Prompts and plans** submitted by users are logged for audit
  purposes. These logs include the classified domain, rule IDs,
  compliance actions and justifications.
- **Generated outputs** and risk scores are recorded when the
  compliance agents check the plan or final answer.
- **User feedback** submitted via the web demo is stored in
  `reports/user_study.md` along with a timestamp, rating and
  optional comment.

## Handling Feedback and Pseudonymisation
- Feedback entries may contain user identifiers or free‑text
  comments. Before sharing logs externally, replace any personal
  names or emails with pseudonyms (e.g. `USER_A`).
- The provided `user_study.record_user_feedback` function can be
  extended to hash user IDs or drop raw prompts entirely when
  privacy requirements are strict.

## Retention and Deletion
- Audit logs under `logs/` are rotated when they reach 5&nbsp;MB. Old
  log files should be reviewed and deleted after **90&nbsp;days** unless
  required for ongoing research.
- Governance reports and user study files in `reports/` should be
  kept no longer than **six months**.
- To request deletion of specific logs or feedback entries, contact
  the project maintainers via `privacy@example.com` with the
  relevant timestamp or scenario identifier.

## Dataset Provenance
The project relies on external datasets that are **not** included in
this repository. See `datasets/README.md` for details, including
sources and licences:
- PrivacyQA – CC&nbsp;BY&nbsp;4.0, crowd‑sourced privacy questions【F:datasets/README.md†L8-L16】
- HH‑RLHF – Apache&nbsp;2.0, helpful/harmless conversations【F:datasets/README.md†L18-L27】
- OPP‑115 – CC&nbsp;BY‑SA&nbsp;3.0, annotated privacy policies【F:datasets/README.md†L29-L38】
These datasets are used only for evaluation and rule creation.

## User Rights
- Participants may opt out of feedback collection at any time by not
  submitting the form or by requesting deletion of their record.
- Users may request access to stored logs or reports relating to
  their prompts by emailing `privacy@example.com`.

## Deployment Limitations
This project is a research prototype. It does not offer automated
GDPR compliance guarantees and should not be deployed in production
without a full privacy impact assessment. LLM outputs may
inadvertently reveal training data or leak PII.

## Regulatory References
The system is designed with reference to the EU General Data
Protection Regulation and ISO/IEC&nbsp;27001 security management
principles. See the links in `SECURITY.md` for the authoritative
sources.
