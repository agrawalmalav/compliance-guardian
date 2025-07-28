import json
from pathlib import Path


def test_eval_dataset_json_valid():
    path = Path('compliance_guardian/datasets/test_scenarios.json')
    with path.open(encoding='utf-8') as f:
        json.load(f)

