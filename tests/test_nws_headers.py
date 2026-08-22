"""NWS client HTTP header hygiene."""

import asyncio

from skywarnplus_ng.api.nws_client import NWSClient
from skywarnplus_ng.core.config import NWSApiConfig


def test_nws_client_sets_accept_and_user_agent() -> None:
    client = NWSClient(
        NWSApiConfig(
            base_url="https://api.weather.gov",
            user_agent="SkywarnPlus-NG/test (+https://example.test)",
            timeout=5,
        )
    )
    try:
        assert client.client.headers["User-Agent"] == "SkywarnPlus-NG/test (+https://example.test)"
        assert client.client.headers["Accept"] == "application/geo+json"
    finally:
        asyncio.run(client.close())


def test_nws_client_sync_http_client_headers() -> None:
    client = NWSClient(NWSApiConfig(user_agent="old", timeout=5))
    try:
        client.config.user_agent = "new (+https://example.test)"
        client.sync_http_client_headers()
        assert client.client.headers["User-Agent"] == "new (+https://example.test)"
        assert client.client.headers["Accept"] == "application/geo+json"
    finally:
        asyncio.run(client.close())
