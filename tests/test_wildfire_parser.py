"""Tests for wildfire parser."""

from skywarnplus_ng.wildfire.parser import (
    geometry_centroid,
    is_prescribed_fire,
    parse_wildfire_collection,
)


SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "1",
            "properties": {
                "poly_IncidentName": "Sample Fire",
                "poly_GISAcres": 1200.5,
                "attr_PercentContained": 15,
                "poly_IrwinID": "2024-CA-SAMPLE-001",
                "attr_IncidentTypeKind": "WF",
                "poly_FeatureCategory": "Wildfire",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-118.5, 34.0],
                        [-118.4, 34.0],
                        [-118.4, 34.1],
                        [-118.5, 34.1],
                        [-118.5, 34.0],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "id": "2",
            "properties": {
                "poly_IncidentName": "Rx Burn",
                "poly_GISAcres": 5000,
                "poly_IrwinID": "2024-CA-RX-001",
                "attr_IncidentTypeKind": "RX",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-118.45, 34.05],
            },
        },
    ],
}


def test_geometry_centroid_polygon():
    centroid = geometry_centroid(SAMPLE_GEOJSON["features"][0]["geometry"])
    assert centroid is not None
    lat, lon = centroid
    assert 34.0 < lat < 34.1
    assert -118.5 < lon < -118.4


def test_is_prescribed_fire():
    assert is_prescribed_fire(incident_type_kind="RX", feature_category="")
    assert is_prescribed_fire(incident_type_kind="", feature_category="Prescribed Fire")
    assert not is_prescribed_fire(incident_type_kind="WF", feature_category="Wildfire")


def test_parse_wildfire_collection():
    incidents = parse_wildfire_collection(SAMPLE_GEOJSON, origin_lat=34.05, origin_lon=-118.25)
    assert len(incidents) == 2
    assert incidents[0].name == "Sample Fire"
    assert "Wildfire alert" in incidents[0].tts_text
    assert incidents[0].percent_contained == 15
