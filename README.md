# certbot-dns-hosttech

[![Codecov coverage](https://codecov.io/gh/bunkerity/certbot-dns-hosttech/branch/main/graph/badge.svg)](https://app.codecov.io/gh/bunkerity/certbot-dns-hosttech)

[Certbot](https://certbot.eff.org/) DNS-01 authenticator for the [Hosttech DNS API](https://api.ns1.hosttech.eu/api/documentation/).
Supports apex names, subdomains and wildcards, including two TXT values at the same challenge name.

| At a glance | Value |
| --- | --- |
| Plugin name | `dns-hosttech` |
| Requires | Python 3.11 or newer and Certbot 5.9.x (dependency range `>=5.9.0,<6`) |
| Supported Python | 3.11–3.14 |
| Runtime dependencies | Certbot and requests |
| Credentials | Hosttech REST API bearer token in a sectionless INI file |
| License | Apache-2.0 |

> **Read before you run it**
>
> - `--dry-run` uses Let's Encrypt staging and still creates/deletes real DNS records through Hosttech.
> - If the process is killed or the network fails mid-run, a TXT record may remain. [Remove it by hand](#interrupted-runs-and-leftover-records).
> - The 600-second propagation wait is a conservative starting value, not a measured Hosttech guarantee. Live Hosttech access and DNS propagation have not been tested without a real token.

## Quickstart

### 1. Install

Install the plugin in the **same Python environment as Certbot**. A separate pip installation cannot extend a Certbot snap or another virtual environment.

The [v0.1.0 release](https://github.com/bunkerity/certbot-dns-hosttech/releases/tag/v0.1.0) will provide a wheel, source archive and `SHA256SUMS`. Once published, install the wheel:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install \
  'https://github.com/bunkerity/certbot-dns-hosttech/releases/download/v0.1.0/certbot_dns_hosttech-0.1.0-py3-none-any.whl' \
  'certbot==5.9.0'
.venv/bin/certbot plugins --text
```

The plugin should appear as `dns-hosttech`.

To verify provenance before installation, download the wheel with [GitHub CLI](https://cli.github.com/) and verify its attestation. Then install the verified local file:

```sh
gh release download v0.1.0 -R bunkerity/certbot-dns-hosttech \
  --pattern 'certbot_dns_hosttech-0.1.0-py3-none-any.whl'
gh attestation verify certbot_dns_hosttech-0.1.0-py3-none-any.whl -R bunkerity/certbot-dns-hosttech
.venv/bin/python -m pip install ./certbot_dns_hosttech-0.1.0-py3-none-any.whl 'certbot==5.9.0'
```

For development before publication, use `.venv/bin/python -m pip install . 'certbot==5.9.0'` from a checkout.

### 2. Add your token

Create a DNS API token in myhosttech.eu → DNS Editor → API. Use the REST API bearer token, not the old WSDL username/password.
The token must allow listing the relevant zones and creating/deleting their DNS records.

<details>
<summary>Token scopes</summary>

Public Hosttech documentation does not establish whether tokens support per-zone or read/write scopes; confirm available restrictions with Hosttech.

</details>

Put it in a sectionless INI file such as `/etc/letsencrypt/hosttech.ini`:

```ini
dns_hosttech_api_token = YOUR_HOSTTECH_DNS_API_TOKEN
```

Restrict access before use:

```sh
chmod 600 /etc/letsencrypt/hosttech.ini
```

Do not pass the token on the command line. Keep this file for renewals: Certbot saves its path, not its contents, in renewal configuration. Certbot warns about unsafe file permissions; it does not reject them.

### 3. Get a staging certificate

First run a staging validation with an apex and its wildcard:

```sh
.venv/bin/certbot certonly \
  --authenticator dns-hosttech \
  --dns-hosttech-credentials /etc/letsencrypt/hosttech.ini \
  --dns-hosttech-propagation-seconds 600 \
  --dry-run --non-interactive --agree-tos --email admin@example.com \
  -d example.com -d '*.example.com'
```

Replace the example domains and email address. `--dry-run` uses Let's Encrypt staging and still creates/deletes real DNS records through Hosttech.

After staging succeeds, run the same command without `--dry-run` to obtain a production certificate. Standard `certbot renew` reuses the saved authenticator options.

## Reference

### Options

| Option | Meaning |
| --- | --- |
| `--dns-hosttech-credentials PATH` | Path to the credentials INI file. |
| `--dns-hosttech-propagation-seconds N` | Fixed wait after creating all challenges, default **600 seconds**. |

### TTL and propagation

TXT TTL is **600 seconds**, matching [Hosttech's published minimum](https://en.support.hosttech.ch/knowledge-base/what-modules-are-available-for-whmcs/).
Propagation wait is a conservative initial choice, not a measured Hosttech publication guarantee. TTL and propagation delay describe different things. Increase the wait if staging validation shows it is insufficient.

<details>
<summary>What Hosttech says about timing</summary>

[Hosttech's general guidance](https://en.support.hosttech.ch/knowledge-base/how-can-i-set-change-dns-records/) allows up to six hours for DNS changes to become active; it gives no API-to-authoritative-server SLA.

</details>

### How it behaves

**Zones and names**

- Finds the most specific accessible Hosttech zone matching the validation name, including delegated `_acme-challenge` zones. Zone listing is paginated. No SOA lookup is needed, so local split DNS and future A/AAAA cutovers do not affect zone discovery.
- ACME must still be able to resolve the validation TXT records through **public authoritative DNS**. Private-only zones cannot validate with Let's Encrypt.
- Does not follow CNAMEs itself. Standard Certbot creates at its supplied validation name; CNAME delegation needs separate Certbot configuration/integration support. This plugin does not discover a hidden child zone when a token only exposes its parent.

**Records and cleanup**

- Creates separate TXT records and tracks their returned IDs. Cleanup deletes only IDs created by this authenticator instance, preserving other TXT records at the same name, even with identical content. It never replaces a zone or RRset.
- Repeating the same challenge within one instance reuses its created record. Different apex/wildcard values remain separate.
- Cleanup attempts all challenges and reports deletion failures. Failed record IDs remain available for a retry in the same process. After process exit, remove any leftovers manually.

<details>
<summary>Errors, transport and security</summary>

- Maps authentication, permission, missing-zone, validation, rate-limit (419/429), network/TLS and server failures to `PluginError` with remediation. Raw API response bodies and request exception text are not logged.
- HTTP redirects are rejected; TLS verification stays enabled; each request has a 30-second timeout. Explicit Bearer authentication takes precedence over unrelated `.netrc` credentials.

</details>

<details>
<summary>Not documented or not tested</summary>

Public API documentation does not publish a numerical rate quota, TXT TTL maximum or token-scope contract. Live Hosttech access and DNS propagation have not been tested without a real token.

</details>

### Interrupted runs and leftover records

IDs are tracked in memory. If the process is killed, the network fails after a successful create, or Hosttech returns an unusable create response, a record may remain. Inspect the DNS Editor and remove only the challenge record from that interrupted attempt before retrying. Automatic POST retries are deliberately avoided because creation may already have succeeded.

## Development

<details>
<summary>Setup, checks and CI</summary>

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -m black --check --workers 1 .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest -vv --cov --cov-branch --cov-report=term-missing
.venv/bin/python -m build --no-isolation
.venv/bin/python -m twine check dist/*
```

Tests mock Hosttech or use an HTTP fake bound to localhost. No provider token is needed. The interface test discovers the installed entry point and calls Certbot `perform`/`cleanup` with real DNS-01 challenges for an apex and wildcard in one batch. It asserts that both values coexist and existing records survive cleanup. This tests the plugin interface and HTTP contract, not issuance by a real ACME server.

CI runs lint, strict typing, 100% branch coverage and packaging checks across Python 3.11–3.14. Development dependencies are pinned with hashes in `requirements-dev.txt`; runtime package metadata retains compatible version ranges. Weekly Dependabot updates cover Python dependencies and GitHub Actions. SHA-pinned Plumber, CodeQL and OpenSSF Scorecard workflows follow the [OSS security workflow notes](.github/plumber/README.md). Score publishing is enabled only for public repositories.

</details>

## License

Apache-2.0. See [LICENSE](LICENSE).
