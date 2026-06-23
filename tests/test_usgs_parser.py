"""Tests for USGS earthquake parser."""

from skywarnplus_ng.usgs.parser import parse_earthquake_collection, parse_earthquake_feature


SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "us7000abc1",
            "properties": {
                "mag": 4.2,
                "place": "5 km NE of Testville, CA",
                "time": 1716000000000,
                "status": "reviewed",
                "tsunami": 0,
            },
            "geometry": {"type": "Point", "coordinates": [-118.0, 34.0, 10.5]},
        },
        {
            "type": "Feature",
            "id": "us7000abc2",
            "properties": {
                "mag": 2.1,
                "place": "10 km S of Faraway",
                "time": 1716001000000,
                "status": "automatic",
                "tsunami": 0,
            },
            "geometry": {"type": "Point", "coordinates": [-120.0, 36.0, 5.0]},
        },
    ],
}


def test_parse_earthquake_collection_filters_invalid():
    events = parse_earthquake_collection(SAMPLE_GEOJSON, origin_lat=34.05, origin_lon=-118.25)
    assert len(events) == 2
    assert events[0].event_id == "us7000abc1"
    assert events[0].magnitude == 4.2
    assert events[0].distance_miles >= 0
    assert "Earthquake magnitude" in events[0].tts_text


def test_parse_earthquake_feature_tsunami_note():
    feature = SAMPLE_GEOJSON["features"][0].copy()
    feature["properties"] = dict(feature["properties"], tsunami=1)
    event = parse_earthquake_feature(feature, origin_lat=34.05, origin_lon=-118.25)
    assert event is not None
    assert "Tsunami information" in event.tts_text
