"""Exercise the discovered plugin through Certbot's public perform/cleanup interface."""

import argparse
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import josepy
import pytest
import requests
from acme import challenges, messages
from certbot import achallenges, errors
from certbot._internal.display import obj as display_obj
from certbot._internal.plugins import disco
from cryptography.hazmat.primitives.asymmetric import rsa

from certbot_dns_hosttech._internal import dns_hosttech


@pytest.fixture
def fake_api(monkeypatch):
    state = SimpleNamespace(
        records={7: {"type": "TXT", "name": "_acme-challenge", "text": "pre-existing", "ttl": 3600}}, next_id=10, events=[], fail_delete=None
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, status, data=None):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if status != 204:
                self.wfile.write(json.dumps({"data": data}).encode())

        def do_GET(self):
            assert self.headers["Authorization"] == "Bearer dummy-local-token"
            assert self.path == "/api/user/v1/zones?limit=100&offset=0"
            self.send_json(200, [{"id": 1, "name": "example.com"}])

        def do_POST(self):
            assert self.headers["Authorization"] == "Bearer dummy-local-token"
            assert self.path == "/api/user/v1/zones/1/records"
            record = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert record["type"] == "TXT"
            assert record["name"] == "_acme-challenge"
            assert record["ttl"] == 600
            record_id = state.next_id
            state.next_id += 1
            state.records[record_id] = record
            state.events.append(("create", record_id, record))
            self.send_json(201, {"id": record_id, **record})

        def do_DELETE(self):
            assert self.headers["Authorization"] == "Bearer dummy-local-token"
            record_id = int(self.path.rsplit("/", 1)[1])
            assert self.path == f"/api/user/v1/zones/1/records/{record_id}"
            if record_id == state.fail_delete:
                self.send_json(429)
                return
            existed = state.records.pop(record_id, None)
            state.events.append(("delete", record_id))
            self.send_json(204 if existed else 404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(dns_hosttech, "API_URL", f"http://127.0.0.1:{server.server_port}/api/user/v1")
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def interface_auth(tmp_path, monkeypatch):
    path = tmp_path / "hosttech.ini"
    path.write_text("dns_hosttech_api_token = dummy-local-token\n")
    path.chmod(0o600)
    config = argparse.Namespace(dns_hosttech_credentials=str(path), dns_hosttech_propagation_seconds=0)
    monkeypatch.setattr(display_obj._SERVICE, "display", display_obj.NoninteractiveDisplay(io.StringIO()))
    return disco.PluginsRegistry.find_all()["dns-hosttech"].init(config)


@pytest.fixture
def apex_and_wildcard():
    account_key = josepy.JWKRSA(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))
    # ACME authorizations carry the base identifier for wildcard certificates too.
    return [
        achallenges.KeyAuthorizationAnnotatedChallenge(
            challb=messages.ChallengeBody(chall=challenges.DNS01(token=token), status=messages.STATUS_PENDING),
            identifier=messages.Identifier(typ=messages.IDENTIFIER_FQDN, value=requested_name.removeprefix("*.")),
            account_key=account_key,
        )
        for requested_name, token in [("example.com", b"apex-unique-acme-token-0001"), ("*.example.com", b"wildcard-unique-acme-token-0002")]
    ]


def test_discovered_plugin_perform_cleanup_apex_and_wildcard(interface_auth, apex_and_wildcard, fake_api):
    fake_api.records[7]["text"] = apex_and_wildcard[0].validation(apex_and_wildcard[0].account_key)
    original = dict(fake_api.records)
    responses = interface_auth.perform(apex_and_wildcard)
    assert len(responses) == 2
    assert all(isinstance(response, challenges.DNS01Response) for response in responses)
    created = {key: value for key, value in fake_api.records.items() if key not in original}
    assert len(created) == 2
    assert {record["name"] for record in created.values()} == {"_acme-challenge"}
    assert {record["text"] for record in created.values()} == {challenge.validation(challenge.account_key) for challenge in apex_and_wildcard}
    print("REQUESTED: example.com, *.example.com; AFTER PERFORM:", json.dumps(fake_api.records, sort_keys=True))
    interface_auth.cleanup(apex_and_wildcard)
    assert fake_api.records == original
    print("AFTER CLEANUP:", json.dumps(fake_api.records, sort_keys=True))
    print("EVENTS:", json.dumps(fake_api.events))
    interface_auth.cleanup(apex_and_wildcard)
    assert fake_api.records == original


def test_cleanup_attempts_other_challenges_after_delete_failure(interface_auth, apex_and_wildcard, fake_api):
    interface_auth.perform(apex_and_wildcard)
    fake_api.fail_delete = 10
    with pytest.raises(errors.PluginError, match="rate limit"):
        interface_auth.cleanup(apex_and_wildcard)
    assert set(fake_api.records) == {7, 10}
    fake_api.fail_delete = None
    interface_auth.cleanup(apex_and_wildcard)
    assert set(fake_api.records) == {7}


def test_bearer_token_wins_over_netrc(interface_auth, apex_and_wildcard, fake_api, monkeypatch):
    monkeypatch.setattr(requests.sessions, "get_netrc_auth", lambda url: ("unrelated-user", "unrelated-password"))
    interface_auth.perform(apex_and_wildcard)
    interface_auth.cleanup(apex_and_wildcard)
    assert set(fake_api.records) == {7}
