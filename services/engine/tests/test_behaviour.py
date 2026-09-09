from engine.behaviour import machine as m


def test_close_moves_everything_to_research():
    for s in m.STATES:
        assert m.on_market_close(s).to == "RESEARCH"


def test_open_is_calm_unless_cooldown_pending():
    assert m.on_market_open("RESEARCH", cooldown_pending=False).to == "CALM"
    assert m.on_market_open("RESEARCH", cooldown_pending=True).to == "COOLDOWN"


def test_two_overrides_elevate_from_calm_only():
    assert m.on_override_attempt("CALM", 1).changed is False
    d = m.on_override_attempt("CALM", 2)
    assert d.to == "ELEVATED" and d.changed
    assert m.on_override_attempt("COOLDOWN", 5).to == "COOLDOWN"
    assert m.on_override_attempt("RESEARCH", 5).to == "RESEARCH"


def test_lexicon_hits_elevate():
    d, hits = m.on_journal_text("CALM", "I need to get it back, sizing up on the next one")
    assert d.to == "ELEVATED" and "get it back" in hits
    d2, hits2 = m.on_journal_text("CALM", "Took the fill at the open as planned; stop untouched.")
    assert d2.to == "CALM" and hits2 == []


def test_lexicon_file_is_non_empty_and_lowercase():
    lex = m.lexicon()
    assert len(lex) > 20 and all(p == p.lower() for p in lex)


def test_breach_and_brake_cooldown():
    assert m.on_rule_breach("CALM", "Stop widened").to == "COOLDOWN"
    assert m.on_daily_brake("ELEVATED").to == "COOLDOWN"
    assert m.on_daily_brake("RESEARCH").to == "RESEARCH"


def test_permissions():
    assert m.can_edit_parameters("RESEARCH") and not m.can_edit_parameters("CALM")
    assert m.can_open_positions("CALM") and m.can_open_positions("ELEVATED")
    assert not m.can_open_positions("COOLDOWN") and not m.can_open_positions("RESEARCH")
