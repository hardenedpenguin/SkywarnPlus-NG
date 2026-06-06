"""Application state defaults."""

from skywarnplus_ng.core.state import ApplicationState


def test_default_state_has_nws_error_keys(tmp_path):
    sm = ApplicationState(tmp_path / "state.json")
    d = sm._get_default_state()
    assert d.get("nws_last_error_at") is None
    assert d.get("nws_last_error_message") is None
    assert d.get("nhc_last_error_at") is None
    assert d.get("nhc_last_error_message") is None
