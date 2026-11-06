"""Hosttech API contract and authenticator behavior without provider credentials."""

import argparse
import json
import logging
import traceback
from unittest.mock import Mock

import pytest
import requests
from certbot import errors
from certbot.plugins import dns_common

from certbot_dns_hosttech._internal import dns_hosttech

TOKEN = "test-secret-token"
NAME = "_acme-challenge.example.com"


def response(status=200, data=None, raw=None):
    result = requests.Response()
    result.status_code = status
    result._content = raw if raw is not None else json.dumps({"data": data}).encode()
    return result


@pytest.fixture
def api(monkeypatch):
    request = Mock()
    monkeypatch.setattr(requests, "request", request)
    return dns_hosttech._HosttechClient(TOKEN), request


@pytest.fixture
def auth(tmp_path):
    credentials = tmp_path / "hosttech.ini"
    credentials.write_text(f"dns_hosttech_api_token = {TOKEN}\n")
    credentials.chmod(0o600)
    config = argparse.Namespace(dns_hosttech_credentials=str(credentials), dns_hosttech_propagation_seconds=0)
    return dns_hosttech.Authenticator(config, "dns-hosttech")


def test_parser_and_base_interface():
    parser = argparse.ArgumentParser()
    dns_hosttech.Authenticator.inject_parser_options(parser, "dns-hosttech")
    config = parser.parse_args(["--dns-hosttech-credentials", "hosttech.ini"])
    auth = dns_hosttech.Authenticator(config, "dns-hosttech")
    assert config.dns_hosttech_propagation_seconds == 600
    assert config.dns_hosttech_credentials == "hosttech.ini"
    assert isinstance(auth, dns_common.DNSAuthenticator)
    assert "Hosttech" in auth.more_info()
    assert [c.typ for c in auth.get_chall_pref("example.com")] == ["dns-01"]


def test_credentials(auth):
    auth._setup_credentials()
    assert auth.credentials.conf("api-token") == TOKEN
    client = auth._client
    auth._setup_credentials()
    assert auth._client is client


def test_malformed_credentials_do_not_leak_token(auth, caplog):
    with open(auth.conf("credentials"), "w") as stream:
        stream.write(TOKEN + "\n")
    with caplog.at_level(logging.DEBUG), pytest.raises(errors.PluginError) as exc:
        auth._setup_credentials()
    assert TOKEN not in "".join(traceback.format_exception(exc.value)) + caplog.text


@pytest.mark.parametrize(
    "contents", ["", "other_key = value\n", "dns_hosttech_api_token =\n", 'dns_hosttech_api_token = " "\n', "dns_hosttech_api_token = one, two\n"]
)
def test_invalid_credentials(auth, contents):
    with open(auth.conf("credentials"), "w") as stream:
        stream.write(contents)
    with pytest.raises(errors.PluginError, match="dns_hosttech_api_token"):
        auth._setup_credentials()


def test_missing_credential_file(auth):
    auth.config.dns_hosttech_credentials += ".missing"
    with pytest.raises(errors.PluginError, match="File not found"):
        auth._setup_credentials()


def test_credential_path_is_directory(auth, tmp_path):
    auth.config.dns_hosttech_credentials = str(tmp_path)
    with pytest.raises(errors.PluginError, match="directory"):
        auth._setup_credentials()


def test_credential_permissions_warn(auth, caplog):
    import os

    os.chmod(auth.conf("credentials"), 0o644)
    with caplog.at_level(logging.WARNING):
        auth._setup_credentials()
    assert "Unsafe permissions" in caplog.text
    assert TOKEN not in caplog.text


def test_unreadable_credentials_are_actionable(auth, monkeypatch):
    monkeypatch.setattr(auth, "_configure_credentials", Mock(side_effect=PermissionError(TOKEN)))
    with pytest.raises(errors.PluginError, match="read.*credentials") as exc:
        auth._setup_credentials()
    assert TOKEN not in "".join(traceback.format_exception(exc.value))


def test_negative_propagation_seconds(auth):
    auth.config.dns_hosttech_propagation_seconds = -1
    with pytest.raises(errors.PluginError, match="non-negative"):
        auth._setup_credentials()


def test_unprepared_perform(auth):
    with pytest.raises(errors.PluginError, match="credentials"):
        auth._perform("example.com", NAME, "value")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (NAME, (1, "example.com")),
        ("_acme-challenge.www.example.com", (2, "www.example.com")),
        ("_ACME-CHALLENGE.SUB.EXAMPLE.COM.", (3, "sub.example.com")),
        ("_acme-challenge.deep.sub.example.com", (3, "sub.example.com")),
        ("_acme-challenge.other.example.com", (1, "example.com")),
        ("example.com", (1, "example.com")),
    ],
)
def test_longest_zone(api, name, expected):
    client, request = api
    request.return_value = response(data=[{"id": 1, "name": "Example.COM."}, {"id": 2, "name": "www.example.com"}, {"id": 3, "name": "sub.example.com"}])
    assert client.find_zone(name) == expected
    assert client.find_zone(name) == expected
    assert request.call_count == 1


@pytest.mark.parametrize("zones", [[], [{"id": 1, "name": "notexample.com"}], [{"id": 1, "name": "example.com.evil.test"}]])
def test_zone_not_found(api, zones):
    client, request = api
    request.return_value = response(data=zones)
    with pytest.raises(errors.PluginError, match="No matching Hosttech zone"):
        client.find_zone(NAME)


def test_zone_pagination_prefers_later_more_specific_zone(api):
    client, request = api
    page = [{"id": i + 1, "name": f"zone{i}.invalid"} for i in range(99)] + [{"id": 100, "name": "example.com"}]
    request.side_effect = [response(data=page), response(data=[{"id": 101, "name": "sub.example.com"}])]
    assert client.find_zone("_acme-challenge.sub.example.com") == (101, "sub.example.com")
    assert [call.kwargs["params"] for call in request.call_args_list] == [{"limit": 100, "offset": 0}, {"limit": 100, "offset": 100}]


def test_exact_full_page_fetches_empty_final_page(api):
    client, request = api
    page = [{"id": 1, "name": "example.com"}] + [{"id": i + 2, "name": f"zone{i}.invalid"} for i in range(99)]
    request.side_effect = [response(data=page), response(data=[])]
    assert client.find_zone(NAME) == (1, "example.com")
    assert request.call_count == 2


def test_repeated_zone_page_fails_instead_of_looping(api):
    client, request = api
    page = [{"id": i + 1, "name": f"zone{i}.invalid"} for i in range(100)]
    request.side_effect = [response(data=page), response(data=page), response(401)]
    with pytest.raises(errors.PluginError, match="pagination"):
        client.find_zone(NAME)
    assert request.call_count == 2


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        [None],
        [{"id": 1}],
        [{"id": "1", "name": "example.com"}],
        [{"id": True, "name": "example.com"}],
        [{"id": 0, "name": "example.com"}],
        [{"id": 1, "name": None}],
        [{"id": 1, "name": ""}],
    ],
)
def test_malformed_zone_response(api, data):
    client, request = api
    request.return_value = response(data=data)
    with pytest.raises(errors.PluginError, match="zone"):
        client.find_zone(NAME)


@pytest.mark.parametrize(
    ("zone", "relative"), [("example.com", "_acme-challenge"), ("sub.example.com", "_acme-challenge"), ("_acme-challenge.sub.example.com", "")]
)
def test_create_payload(api, zone, relative):
    client, request = api
    name = NAME if zone == "example.com" else "_acme-challenge.sub.example.com"
    request.side_effect = [response(data=[{"id": 4, "name": zone}]), response(201, {"id": 17})]
    assert client.add_txt_record(name.upper() + ".", "validation", 600) == (4, 17)
    call = request.call_args
    assert call.args == ("POST", dns_hosttech.API_URL + "/zones/4/records")
    assert call.kwargs["json"] == {"type": "TXT", "name": relative, "text": "validation", "ttl": 600}
    prepared = requests.Request("GET", dns_hosttech.API_URL).prepare()
    assert call.kwargs["auth"](prepared).headers["Authorization"] == "Bearer " + TOKEN
    assert call.kwargs["headers"]["Accept"] == "application/json"
    assert call.kwargs["timeout"] == 30
    assert call.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("data", [None, [], {}, {"id": "17"}, {"id": False}, {"id": -1}])
def test_malformed_created_record_warns_about_orphan(api, data):
    client, request = api
    request.side_effect = [response(data=[{"id": 1, "name": "example.com"}]), response(201, data)]
    with pytest.raises(errors.PluginError, match="DNS Editor"):
        client.add_txt_record(NAME, "validation", 600)


@pytest.mark.parametrize(
    ("status", "hint"),
    [
        (400, "rejected"),
        (401, "token"),
        (403, "permission"),
        (404, "not found"),
        (419, "rate limit"),
        (429, "rate limit"),
        (422, "rejected"),
        (500, "unavailable"),
        (503, "unavailable"),
        (302, "Unexpected"),
        (418, "Unexpected"),
    ],
)
def test_api_errors_are_actionable_and_do_not_leak_secrets(api, status, hint, caplog):
    client, request = api
    request.return_value = response(status, {"message": TOKEN, "errors": {TOKEN: [TOKEN]}})
    with caplog.at_level(logging.DEBUG), pytest.raises(errors.PluginError, match=hint) as exc:
        client.find_zone(NAME)
    assert str(status) in str(exc.value)
    assert TOKEN not in "".join(traceback.format_exception(exc.value)) + caplog.text
    assert request.call_count == 1


@pytest.mark.parametrize(
    "error", [requests.Timeout(TOKEN), requests.ConnectionError(TOKEN), requests.exceptions.SSLError(TOKEN), requests.RequestException(TOKEN)]
)
def test_request_errors_are_sanitized(api, error, caplog):
    client, request = api
    request.side_effect = error
    with pytest.raises(errors.PluginError, match="network") as exc:
        client.find_zone(NAME)
    assert TOKEN not in "".join(traceback.format_exception(exc.value)) + caplog.text


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"{}", b"null"])
def test_malformed_api_envelope(api, raw):
    client, request = api
    request.return_value = response(raw=raw)
    with pytest.raises(errors.PluginError, match="response"):
        client.find_zone(NAME)


def test_two_values_cleanup_only_created_ids(auth, api):
    _, request = api
    request.side_effect = [
        response(data=[{"id": 1, "name": "example.com"}]),
        response(201, {"id": 17}),
        response(201, {"id": 18}),
        response(204),
        response(204),
    ]
    auth._setup_credentials()
    auth._perform("example.com", NAME, "apex-value")
    auth._perform("example.com", NAME, "wildcard-value")
    auth._cleanup("example.com", NAME.upper() + ".", "apex-value")
    auth._cleanup("example.com", NAME, "wildcard-value")
    auth._cleanup("example.com", NAME, "not-ours")
    auth._cleanup("example.com", NAME, "apex-value")
    deletes = [c.args[1] for c in request.call_args_list if c.args[0] == "DELETE"]
    assert deletes == [dns_hosttech.API_URL + "/zones/1/records/17", dns_hosttech.API_URL + "/zones/1/records/18"]


def test_repeated_perform_same_value_is_idempotent(auth, api):
    _, request = api
    request.side_effect = [
        response(data=[{"id": 1, "name": "example.com"}]),
        response(201, {"id": 17}),
        response(204),
    ]
    auth._setup_credentials()
    auth._perform("example.com", NAME, "same")
    auth._perform("example.com", NAME, "same")
    auth._cleanup("example.com", NAME, "same")
    assert [c.args[0] for c in request.call_args_list] == ["GET", "POST", "DELETE"]


def test_failed_perform_cleanup_never_deletes(auth, api):
    _, request = api
    request.return_value = response(401)
    auth._setup_credentials()
    with pytest.raises(errors.PluginError):
        auth._perform("example.com", NAME, "value")
    auth._cleanup("example.com", NAME, "value")
    assert request.call_count == 1


def test_cleanup_before_setup_is_noop(auth):
    auth._cleanup("example.com", NAME, "value")


@pytest.mark.parametrize("status", [204, 404])
def test_delete_missing_is_idempotent(api, status):
    client, request = api
    request.return_value = response(status)
    client.delete_record(1, 17)
    assert request.call_args.args == ("DELETE", dns_hosttech.API_URL + "/zones/1/records/17")


def test_failed_cleanup_keeps_ids_for_retry(auth, api):
    _, request = api
    request.side_effect = [response(data=[{"id": 1, "name": "example.com"}]), response(201, {"id": 17}), response(429), response(204)]
    auth._setup_credentials()
    auth._perform("example.com", NAME, "value")
    with pytest.raises(errors.PluginError, match="rate limit"):
        auth._cleanup("example.com", NAME, "value")
    auth._cleanup("example.com", NAME, "value")
    assert request.call_args_list[-1].args == request.call_args_list[-2].args
