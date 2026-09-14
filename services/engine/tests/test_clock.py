from datetime import datetime

from engine.services import clock
from tests.harness import install_db


def test_steps_only_through_session_moments():
    assert clock.step_one(datetime(2025, 6, 12, 10, 35)) == datetime(2025, 6, 12, 10, 36)
    assert clock.step_one(datetime(2025, 6, 12, 15, 30)) == datetime(2025, 6, 13, 9, 15)  # Thu -> Fri
    assert clock.step_one(datetime(2025, 6, 13, 15, 30)) == datetime(2025, 6, 16, 9, 15)  # Fri -> Mon


def test_stops_at_end_of_data_instead_of_looping():
    last_close = datetime(2025, 12, 31, 15, 30)
    assert clock.step_one(datetime(2025, 12, 31, 15, 29)) == last_close
    assert clock.step_one(last_close) is None
    assert clock.at_end(last_close) and not clock.at_end(datetime(2025, 12, 31, 15, 29))


def test_advance_pauses_at_end(monkeypatch):
    factory = install_db(monkeypatch)
    with factory() as session:
        row = clock.get(session)
        row.now = datetime(2025, 12, 31, 15, 28)
        row.running = True
        session.flush()
        assert clock.advance(session, 5) == datetime(2025, 12, 31, 15, 30)
        assert row.running is False
        assert clock.to_dict(row)["at_end"] is True
