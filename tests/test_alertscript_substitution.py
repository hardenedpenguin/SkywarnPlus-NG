"""AlertScript placeholder substitution and DTMF validation."""

import shlex
from datetime import UTC

from skywarnplus_ng.core.models import (
    AlertCategory,
    AlertCertainty,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
    WeatherAlert,
)
from skywarnplus_ng.utils.alertscript import AlertScriptManager


def _sample_alert(**kw):
    from datetime import datetime

    now = datetime.now(UTC)
    base = dict(
        id="id-1",
        event="Tornado Warning",
        description="d",
        headline=None,
        instruction=None,
        severity=AlertSeverity.SEVERE,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.ACTUAL,
        category=AlertCategory.MET,
        sent=now,
        effective=now,
        onset=now,
        expires=now,
        area_desc="A; B",
        geocode=[],
        county_codes=["TXC039"],
        sender="s",
        sender_name="n",
    )
    base.update(kw)
    return WeatherAlert(**base)


def test_bash_substitution_quotes_injection():
    malicious = _sample_alert(event="foo; rm -rf /; echo ")
    cmd = "/bin/echo {alert_event}"
    out = AlertScriptManager._substitute_placeholders(cmd, malicious, shell_quoting=True)
    assert out == "/bin/echo " + shlex.quote(malicious.event)


def test_dtmf_substitution_allows_digits():
    a = _sample_alert()
    out = AlertScriptManager._substitute_placeholders("841", a, shell_quoting=False)
    assert AlertScriptManager._dtmf_command_is_safe(out)


def test_dtmf_rejects_injection_after_raw_substitution():
    malicious = _sample_alert(event="841;id")
    out = AlertScriptManager._substitute_placeholders(
        "{alert_event}", malicious, shell_quoting=False
    )
    assert not AlertScriptManager._dtmf_command_is_safe(out)
