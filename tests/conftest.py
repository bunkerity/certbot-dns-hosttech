"""Keep tests away from the real Hosttech API."""

import pytest
import requests


@pytest.fixture(autouse=True)
def local_http_only(monkeypatch):
    original = requests.sessions.Session.request

    def request(self, method, url, **kwargs):
        assert url.startswith("http://127.0.0.1:"), f"Unexpected network access: {url}"
        return original(self, method, url, **kwargs)

    monkeypatch.setattr(requests.sessions.Session, "request", request)
