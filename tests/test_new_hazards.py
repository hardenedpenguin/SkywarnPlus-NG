"""Tests for tsunami, space weather, and volcano hazard parsers."""

from __future__ import annotations

from skywarnplus_ng.spaceweather.parser import parse_swpc_alert_row, parse_swpc_alerts
from skywarnplus_ng.tsunami.parser import (
    is_tsunami_feature,
    level_rank,
    parse_tsunami_feature,
    parse_tsunami_features,
    tsunami_level_from_event,
)
from skywarnplus_ng.volcano.parser import (
    color_rank,
    extract_pseudo_coords,
    parse_pseudo_navy_coord,
    parse_volcano_notice,
)


def test_tsunami_level_from_event() -> None:
    assert tsunami_level_from_event("Tsunami Warning") == "warning"
    assert tsunami_level_from_event("Tsunami Advisory") == "advisory"
    assert tsunami_level_from_event("Tsunami Watch") == "watch"
    assert level_rank("warning") >= level_rank("advisory")


def test_parse_tsunami_feature_filters_non_tsunami() -> None:
    feature = {
        "properties": {
            "id": "urn:oid:1.2.3",
            "event": "Severe Thunderstorm Warning",
            "headline": "Severe Thunderstorm Warning issued",
            "sent": "2026-05-18T12:00:00+00:00",
        }
    }
    assert is_tsunami_feature(feature) is False
    assert parse_tsunami_feature(feature) is None


def test_parse_tsunami_features_min_level() -> None:
    features = [
        {
            "properties": {
                "id": "watch-1",
                "event": "Tsunami Watch",
                "headline": "Tsunami Watch for coastal areas",
                "sent": "2026-05-18T10:00:00+00:00",
            }
        },
        {
            "properties": {
                "id": "warning-1",
                "event": "Tsunami Warning",
                "headline": "Tsunami Warning for coastal areas",
                "sent": "2026-05-18T11:00:00+00:00",
            }
        },
    ]
    warning_only = parse_tsunami_features(features, min_level="warning")
    assert len(warning_only) == 1
    assert warning_only[0].alert_id == "warning-1"

    all_levels = parse_tsunami_features(features, min_level="watch")
    assert len(all_levels) == 2


def test_parse_swpc_alert_row() -> None:
    row = [
        "WATA30",
        "2026-05-18",
        "07:15:00",
        "Geomagnetic Storm Watch",
        " NOAA Scale G2 (Moderate) storm watch in effect for 18-19 May.",
    ]
    alert = parse_swpc_alert_row(row)
    assert alert is not None
    assert alert.message_type == "watch"
    assert alert.geomagnetic_scale == 2
    assert "Geomagnetic Storm Watch" in alert.tts_text


def test_parse_swpc_alerts_dedupes() -> None:
    row = ["ALTTP2", "2026-05-18", "08:00:00", "Radio Blackout Alert", "R1 event."]
    alerts = parse_swpc_alerts([row, row])
    assert len(alerts) == 1


def test_parse_swpc_alert_dict_current_feed_shape() -> None:
    item = {
        "product_id": "A30F",
        "issue_datetime": "2026-07-02 09:35:50.760",
        "message": (
            "Space Weather Message Code: WATA30\r\n"
            "Serial Number: 278\r\n"
            "Issue Time: 2026 Jul 02 0935 UTC\r\n\r\n"
            "WATCH: Geomagnetic Storm Category G2 Predicted"
        ),
    }
    alert = parse_swpc_alerts([item])[0]
    assert alert.message_type == "watch"
    assert alert.geomagnetic_scale == 2
    assert alert.title.startswith("WATCH:")
    assert "G2" in alert.tts_text


def test_parse_swpc_alert_dict_warning_product_id() -> None:
    item = {
        "product_id": "K05W",
        "issue_datetime": "2026-07-01 05:54:08.210",
        "message": (
            "Space Weather Message Code: WARK05\r\n"
            "EXTENDED WARNING: Geomagnetic K-index of 5 expected"
        ),
    }
    alert = parse_swpc_alerts([item])[0]
    assert alert.message_type == "warning"


def test_parse_pseudo_navy_coord() -> None:
    lat = parse_pseudo_navy_coord("N", "1925")
    assert abs(lat - (19 + 25 / 60)) < 0.01
    lon = parse_pseudo_navy_coord("W", "15517")
    assert abs(lon + (155 + 17 / 60)) < 0.01
    decimal_lat = parse_pseudo_navy_coord("N", "19.42")
    assert abs(decimal_lat - 19.42) < 0.01


def test_parse_volcano_notice_uses_catalog_coords_when_psn_missing() -> None:
    item = {
        "vnum": "332010",
        "vName": "Kilauea",
        "colorCode": "ORANGE",
        "obs": "HVO",
        "noticeType": "VONA",
        "noticeIssued": "2026-05-18T10:00:00+00:00",
        "noticeHtml": "<pre>No PSN line here</pre>",
        "lat": 19.42,
        "lon": -155.29,
    }
    notice = parse_volcano_notice(item, origin_lat=21.3, origin_lon=-157.8)
    assert notice is not None
    assert notice.distance_miles is not None


def test_extract_pseudo_coords_from_notice() -> None:
    html = "<pre>Some notice\nPSN: N1925 W15517\n</pre>"
    coords = extract_pseudo_coords(html)
    assert coords is not None
    assert coords[0] > 19.4
    assert coords[1] < -155.2


def test_parse_volcano_notice_with_distance() -> None:
    item = {
        "vnum": "332010",
        "vName": "Kilauea",
        "colorCode": "ORANGE",
        "obs": "HVO",
        "noticeType": "VONA",
        "noticeIssued": "2026-05-18T10:00:00+00:00",
        "noticeHtml": "<pre>PSN: N1925 W15517</pre>",
    }
    notice = parse_volcano_notice(item, origin_lat=21.3, origin_lon=-157.8)
    assert notice is not None
    assert notice.distance_miles is not None
    assert color_rank(notice.color_code) == color_rank("orange")
