from prompts import AGENT_INSTRUCTIONS


def test_named_websites_are_opened_directly() -> None:
    assert "If the user names a website, service, or domain" in AGENT_INSTRUCTIONS
    assert "Only use search_the_web when no website" in AGENT_INSTRUCTIONS
