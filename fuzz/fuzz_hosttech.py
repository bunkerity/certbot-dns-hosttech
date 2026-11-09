"""Coverage-guided, offline checks for provider data and credential diagnostics."""

import argparse
import io
import json
import logging
import socket
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

import atheris
import requests
from certbot import errors
from certbot.plugins import dns_common

with atheris.instrument_imports(include=["certbot_dns_hosttech"]):
    from certbot_dns_hosttech._internal import dns_hosttech

SECRET = "FUZZ_SECRET_MUST_NOT_APPEAR_IN_DIAGNOSTICS"


def response(status, body):
    result = requests.Response()
    result.status_code = status
    result._content = body
    return result


def diagnostics(error):
    return "".join(traceback.format_exception(error))


@atheris.instrument_func
def fuzz_zones(data):
    provider = atheris.FuzzedDataProvider(data)
    base = (provider.ConsumeUnicodeNoSurrogates(40).strip(".") or "example") + ".test"
    name = provider.PickValueInList([base, "_acme-challenge.sub." + base, "not" + base, base + ".invalid"])
    names = [base, "sub." + base, "not" + base + ".invalid", provider.ConsumeUnicodeNoSurrogates(60).rstrip(".") or "other.test"]
    zones = [{"id": i + 1, "name": n.upper() + "."} for i, n in enumerate(names)]
    full_page = provider.ConsumeBool()
    if full_page:
        zones = [{"id": i + 10, "name": f"zone{i}.invalid"} for i in range(99)] + zones
    pages = [zones[:100], zones[100:]] if full_page else [zones]
    repeated = full_page and provider.ConsumeBool()
    if repeated:
        pages[1] = pages[0]
    invalid = provider.ConsumeBool()
    if invalid:
        pages[0][0] = {"id": provider.PickValueInList([True, 0, -1, "1", None]), "name": base}
    iterator = iter(pages)

    def request(method, url, **kwargs):
        assert method == "GET" and url == dns_hosttech.API_URL + "/zones"
        assert kwargs["params"]["offset"] in (0, 100)
        return response(200, json.dumps({"data": next(iterator)}).encode())

    # Compare whole labels independently of the client's suffix matcher.
    name = name.upper() + "."
    labels = name.lower().rstrip(".").split(".")
    matches = [
        (z["id"], z["name"].lower().rstrip(".")) for z in zones if labels[-len(z["name"].rstrip(".").split(".")) :] == z["name"].lower().rstrip(".").split(".")
    ]
    client = dns_hosttech._HosttechClient(SECRET)
    with patch.object(requests, "request", request):
        try:
            actual = client.find_zone(name)
        except errors.PluginError:
            assert repeated or invalid or not matches
        else:
            assert not repeated and not invalid and matches
            assert actual == max(matches, key=lambda z: len(z[1]))
            assert client.find_zone(name) == actual  # A cached lookup must not fetch another page.


@atheris.instrument_func
def fuzz_credentials(data):
    provider = atheris.FuzzedDataProvider(data)
    content = provider.PickValueInList([data, b"dns_hosttech_api_token = " + SECRET.encode(), SECRET.encode() + b"\n", b"[" + SECRET.encode() + b"\n"])
    stream = io.StringIO()
    logger = logging.getLogger(dns_common.__name__)
    handler = logging.StreamHandler(stream)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    error_text = ""
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.ini"
            path.write_bytes(content)
            path.chmod(0o600)
            auth = dns_hosttech.Authenticator(argparse.Namespace(dns_hosttech_credentials=str(path), dns_hosttech_propagation_seconds=0), "dns-hosttech")
            try:
                auth._setup_credentials()
            except errors.PluginError as error:
                error_text = diagnostics(error)
            else:
                token = auth.credentials.conf("api-token")
                assert token and all(33 <= ord(c) <= 126 for c in token)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    assert SECRET not in error_text + stream.getvalue()


@atheris.instrument_func
def fuzz_api(data):
    provider = atheris.FuzzedDataProvider(data)
    status = provider.PickValueInList([200, 201, 204, 302, 400, 401, 403, 404, 419, 422, 429, 500, 599])
    method = provider.PickValueInList(["GET", "POST", "DELETE"])
    transport_error = provider.ConsumeBool()
    envelope = provider.ConsumeIntInRange(0, 2)
    body = provider.ConsumeBytes(provider.remaining_bytes())
    if envelope:
        fields = {"message": SECRET, "errors": [body.decode("utf-8", errors="replace")]}
        if envelope == 1:
            fields["data"] = body.decode("utf-8", errors="replace")
        body = json.dumps(fields).encode()
    reply = response(status, body)
    try:
        payload = reply.json()
    except ValueError:
        payload = None
    expected_success = not transport_error and status in {"GET": (200,), "POST": (201,), "DELETE": (204, 404)}[method]
    expected_success = expected_success and (method == "DELETE" or isinstance(payload, dict) and "data" in payload)
    client = dns_hosttech._HosttechClient(SECRET)
    with patch.object(requests, "request", side_effect=requests.Timeout(SECRET)) if transport_error else patch.object(requests, "request", return_value=reply):
        try:
            result = client._request(method, "/zones")
        except errors.PluginError as error:
            assert not expected_success
            assert SECRET not in diagnostics(error)
        else:
            assert expected_success
            if method == "DELETE":
                assert result is None
            else:
                assert result == payload["data"]


if __name__ == "__main__":
    target = {"zones": fuzz_zones, "credentials": fuzz_credentials, "api": fuzz_api}[sys.argv.pop(1)]
    with patch.object(socket, "socket", side_effect=AssertionError("Fuzzing must not open network sockets")):
        atheris.Setup(sys.argv, target)
        atheris.Fuzz()
