"""Solve DNS-01 challenges with the Hosttech DNS API v1."""

import logging
from collections.abc import Callable
from typing import Any, cast

import requests
from certbot import achallenges, configuration, errors
from certbot.plugins import dns_common

API_URL = "https://api.ns1.hosttech.eu/api/user/v1"


def _redact_credential_errors(record: logging.LogRecord) -> bool:
    # Certbot's INI parser includes malformed lines (potentially the token) in DEBUG tracebacks.
    if str(record.msg).startswith("Error parsing credentials configuration"):
        record.msg = "Error parsing credentials configuration; check the Hosttech INI file syntax."
        record.args = ()
        record.exc_info = None
        record.exc_text = None
    return True


class Authenticator(dns_common.DNSAuthenticator):
    """Create independent TXT records and remove only their returned IDs."""

    description = "Obtain certificates using DNS TXT records hosted by Hosttech."
    ttl = 600

    def __init__(self, config: configuration.NamespaceConfig, name: str) -> None:
        super().__init__(config, name)
        self.credentials: dns_common.CredentialsConfiguration | None = None
        self._client: _HosttechClient | None = None
        self._records: dict[tuple[str, str], tuple[int, int]] = {}

    @classmethod
    def add_parser_arguments(cls, add: Callable[..., None], default_propagation_seconds: int = 600) -> None:
        super().add_parser_arguments(add, default_propagation_seconds)
        add("credentials", help="Hosttech credentials INI file.")

    def more_info(self) -> str:
        return "This plugin creates DNS TXT records through the Hosttech DNS API to respond to DNS-01 challenges."

    def _setup_credentials(self) -> None:
        if self.conf("propagation-seconds") < 0:
            raise errors.PluginError("--dns-hosttech-propagation-seconds must be non-negative.")
        credentials_logger = logging.getLogger(dns_common.__name__)
        credentials_logger.addFilter(_redact_credential_errors)
        try:
            self.credentials = self._configure_credentials(
                "credentials",
                "Hosttech credentials INI file",
                {"api-token": "Hosttech DNS API bearer token"},
                self._validate_credentials,
            )
        except OSError:
            raise errors.PluginError("Cannot read Hosttech credentials; check the file path and read permissions for the Certbot user.") from None
        except errors.PluginError as error:
            if str(error).startswith("Error parsing credentials configuration"):
                raise errors.PluginError(
                    "Cannot parse Hosttech credentials; use a sectionless INI file containing dns_hosttech_api_token = YOUR_TOKEN."
                ) from None
            raise
        finally:
            credentials_logger.removeFilter(_redact_credential_errors)
        if self._client is None:
            self._client = _HosttechClient(cast(str, self.credentials.conf("api-token")))

    @staticmethod
    def _validate_credentials(credentials: dns_common.CredentialsConfiguration) -> None:
        token = credentials.conf("api-token")
        if not isinstance(token, str) or not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise errors.PluginError("dns_hosttech_api_token must be a single non-empty ASCII token without whitespace.")

    def _perform(self, domain: str, validation_name: str, validation: str) -> None:
        if self._client is None:
            raise errors.PluginError("Hosttech credentials have not been configured.")
        key = (validation_name.lower().rstrip("."), validation)
        if key not in self._records:
            self._records[key] = self._client.add_txt_record(validation_name, validation, self.ttl)

    def _cleanup(self, domain: str, validation_name: str, validation: str) -> None:
        key = (validation_name.lower().rstrip("."), validation)
        record = self._records.get(key)
        if record is not None:
            assert self._client is not None
            self._client.delete_record(*record)
            del self._records[key]

    def cleanup(self, achalls: list[achallenges.AnnotatedChallenge]) -> None:
        failures = []
        for achall in achalls:
            try:
                super().cleanup([achall])
            except errors.PluginError as error:
                failures.append(str(error))
        if failures:
            raise errors.PluginError("Hosttech cleanup incomplete: " + "; ".join(failures))


class _HosttechClient:
    """Minimal API client; untrusted response bodies never enter diagnostics."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._zones: list[tuple[int, str]] | None = None

    def _authenticate(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        # Explicit auth takes precedence over unrelated credentials in the operator's .netrc.
        request.headers["Authorization"] = "Bearer " + self._token
        return request

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = requests.request(
                method,
                API_URL + path,
                headers={"Accept": "application/json"},
                auth=self._authenticate,
                timeout=30,
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException:
            raise errors.PluginError(
                f"Hosttech API {method} failed: check network access, proxy settings and trusted TLS certificates. "
                "If creating a TXT record, check the DNS Editor for a leftover before retrying."
            ) from None

        status = response.status_code
        expected = {"GET": (200,), "POST": (201,), "DELETE": (204, 404)}[method]
        if status not in expected:
            if status == 401:
                hint = "Authentication failed; replace or correct dns_hosttech_api_token in the credentials file."
            elif status == 403:
                hint = "Access denied; check the token's zone access and DNS read/write permissions with Hosttech."
            elif status == 404:
                hint = "Zone or record not found; check that the zone still exists in this Hosttech account."
            elif status in (419, 429):
                hint = "Hosttech rate limit reached; wait for the limit to reset, then retry."
            elif status in (400, 422):
                hint = "Record rejected; check the zone, TXT name/value and TTL in the Hosttech DNS Editor."
            elif status >= 500:
                hint = "Hosttech is unavailable; retry later or contact Hosttech support."
            else:
                hint = "Unexpected response; check Hosttech service status and contact support."
            raise errors.PluginError(f"Hosttech API {method} failed (HTTP {status}). {hint}")

        if method == "DELETE":
            return None
        try:
            payload = response.json()
        except ValueError:
            raise errors.PluginError("Hosttech API returned an invalid JSON response. Check the DNS Editor for leftover TXT records before retrying.") from None
        if not isinstance(payload, dict) or "data" not in payload:
            raise errors.PluginError("Hosttech API returned an unexpected response. Check the DNS Editor for leftover TXT records before retrying.")
        return payload["data"]

    def find_zone(self, validation_name: str) -> tuple[int, str]:
        """Find the most specific accessible zone, including delegated challenge zones."""
        if self._zones is None:
            zones = []
            zone_ids = set()
            offset = 0
            while True:
                page = self._request("GET", "/zones", params={"limit": 100, "offset": offset})
                if not isinstance(page, list):
                    raise errors.PluginError("Hosttech API returned an invalid zone list response.")
                for zone in page:
                    if (
                        not isinstance(zone, dict)
                        or type(zone.get("id")) is not int
                        or zone["id"] <= 0
                        or not isinstance(zone.get("name"), str)
                        or not zone["name"].rstrip(".")
                    ):
                        raise errors.PluginError("Hosttech API returned an invalid zone response.")
                    if zone["id"] in zone_ids:
                        raise errors.PluginError("Hosttech zone pagination repeated a zone ID; contact Hosttech support before retrying.")
                    zone_ids.add(zone["id"])
                    zones.append((zone["id"], zone["name"].lower().rstrip(".")))
                if len(page) < 100:
                    break
                offset += len(page)
            self._zones = zones

        name = validation_name.lower().rstrip(".")
        matches = [zone for zone in self._zones if name == zone[1] or name.endswith("." + zone[1])]
        if not matches:
            raise errors.PluginError(f"No matching Hosttech zone for {name}; check the account, zone delegation and token access.")
        return max(matches, key=lambda zone: len(zone[1]))

    def add_txt_record(self, validation_name: str, validation: str, ttl: int) -> tuple[int, int]:
        name = validation_name.lower().rstrip(".")
        zone_id, zone_name = self.find_zone(name)
        relative_name = "" if name == zone_name else name[: -(len(zone_name) + 1)]
        record = self._request("POST", f"/zones/{zone_id}/records", json={"type": "TXT", "name": relative_name, "text": validation, "ttl": ttl})
        if not isinstance(record, dict) or type(record.get("id")) is not int or record["id"] <= 0:
            raise errors.PluginError("Hosttech API returned no valid created record ID; check the DNS Editor for a leftover TXT record before retrying.")
        return zone_id, record["id"]

    def delete_record(self, zone_id: int, record_id: int) -> None:
        self._request("DELETE", f"/zones/{zone_id}/records/{record_id}")
