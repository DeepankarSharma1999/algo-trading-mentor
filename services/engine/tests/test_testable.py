import json

import pytest

from engine import config
from engine.schema.testable import check_testable

CASES = json.loads((config.SCHEMA_DIR / "fixtures" / "testable.cases.json").read_text())


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_shared_fixtures(case):
    spec = {**CASES["base"], **case["patch"]}
    r = check_testable(spec)
    assert r["testable"] == case["testable"]
    assert r["missing_ids"] == case["missing_ids"]


def test_ambiguity_message_names_the_flag():
    r = check_testable({**CASES["base"], "ambiguity_flags": ["stop reads two ways"]})
    assert "stop reads two ways" in r["missing"][0]
