from compliance_guardian.agents import joint_extractor


def test_joint_extractor_rules():
    prompt = "Please scrape data but do not store emails."
    domains, rules = joint_extractor.extract(prompt)
    assert "scraping" in domains
    assert rules and rules[0].category == "user"
