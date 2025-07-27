# Datasets

This project relies on a few open datasets for evaluation and rule creation.
Each dataset is **not** included in this repository. Download them separately
and place them under `datasets/` when needed.

## PrivacyQA
- **Source:** <https://github.com/cisnlp/privacyQA>
- **License:** CC BY 4.0
- **Provenance:** Crowd-sourced questions linked to real privacy policies.
- **Citation:** Chandra et al., *PrivacyQA: A Privacy Policy Question Answering Dataset*, 2020.
- **Use:** Fine‑tuning and validating privacy related prompts.

```python
from datasets import load_dataset
privacyqa = load_dataset("privacyqa")
```

## HH-RLHF
- **Source:** <https://huggingface.co/datasets/Anthropic/hh-rlhf>
- **License:** Apache 2.0
- **Provenance:** Anthropic Helpful/Harmless conversations collected via RLHF.
- **Citation:** Bai et al., *Training a Helpful and Harmless Assistant*, 2022.
- **Use:** Building red‑team prompts and safety tests.

```python
from datasets import load_dataset
hh = load_dataset("Anthropic/hh-rlhf")
```

## OPP-115
- **Source:** <https://usableprivacy.org/data>
- **License:** CC BY-SA 3.0
- **Provenance:** 115 annotated online privacy policies.
- **Citation:** Wilson et al., *The OPP-115 Corpus of Privacy Policies*, 2016.
- **Use:** Deriving rules about notice and consent.

```python
from datasets import load_dataset
opp = load_dataset("opp115")
```
