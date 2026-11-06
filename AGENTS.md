# Repository Guidelines

This is the canonical agent guide. `CLAUDE.md` imports it; edit this file when project guidance changes.

## Purpose and layout

`certbot-dns-hosttech` is a Python DNS-01 authenticator for the Hosttech REST DNS API v1. It is installed in the same Python environment as Certbot and discovered as `dns-hosttech` through the `certbot.plugins` entry point. It is not a BunkerWeb Lua plugin.

- `certbot_dns_hosttech/_internal/dns_hosttech.py`: `DNSAuthenticator` hooks and minimal HTTP client.
- `tests/test_dns_hosttech.py`: mocked API, credentials, zone discovery and cleanup tests.
- `tests/test_interface.py`: installed entry-point discovery and public Certbot `perform`/`cleanup` against a local HTTP fake.
- `tests/conftest.py`: blocks unexpected network access during tests.
- `pyproject.toml`: setuptools metadata, runtime dependency ranges and quality-tool configuration.
- `requirements-dev.txt`: generated universal development lock with hashes.
- `.github/workflows/`: Python matrix, Plumber, CodeQL and OpenSSF Scorecard.

Python 3.11–3.14 and Certbot 5.9.x are supported. Direct runtime dependencies are only `certbot` and `requests`. Keep development tools separate. Update compatibility metadata, matrix and documentation together when changing support.

## DNS and API invariants

Read the connected code and tests before editing. Use pinned official Certbot source for plugin conventions and Hosttech's [OpenAPI document](https://api.ns1.hosttech.eu/api/documentation/api.yaml) for its API contract. Distinguish documented behavior from assumptions that need a real token.

- Keep the standard `DNSAuthenticator` hooks, credential-file handling and `--dns-hosttech-*` flags. Credential key is `dns_hosttech_api_token` in a sectionless INI file.
- Select the longest matching accessible zone using the validation name, including label boundaries, normalized case and trailing dots. Process every page before choosing. Do not substitute the requested certificate domain: an integration may supply an aliased validation name.
- Create a separate TXT record and retain its returned zone/record IDs. Never replace an RRset or delete records found by name/value. Other records, including identical TXT content, belong to someone else.
- Different apex/wildcard values at one name must coexist. Repeating the same challenge is idempotent within one authenticator instance. Cleanup before creation or after successful deletion is harmless.
- Attempt cleanup for every challenge even when one deletion fails. Retain failed IDs for retry. Do not automatically retry POST: a timeout may follow a successful create.
- IDs live in memory; interrupted or ambiguous creates can leave records. Preserve the manual-recovery guidance.
- TXT TTL is 600 seconds. Propagation wait defaults to 600 seconds and uses Certbot's standard override. Neither value establishes a measured Hosttech publication guarantee. No native CNAME following or DNS polling is implemented.
- Use explicit Bearer authentication so `.netrc` cannot override it. Keep TLS verification enabled, redirects disabled and requests bounded by a timeout.
- Convert provider failures into actionable `certbot.errors.PluginError`. Never expose tokens, raw API bodies, request exception text or malformed credential contents in errors or DEBUG tracebacks. Preserve the narrow sanitizer around Certbot's credential parser.
- Never require a live provider token for automated tests. Real Hosttech requests and ACME staging issuance require explicit authorization; `--dry-run` still changes real DNS.

## Development and verification

Use a repository-local virtual environment. From the repository root, after creating `.venv` with Python 3.11 or newer:

```sh
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

Black uses line length 160. Ruff handles lint/import order; mypy checks the package in strict mode. The current coverage gate is 100% statements and branches for the authenticator module. Add focused tests for changed behavior and demonstrate a regression test failing on the unfixed implementation before trusting it. Keep raw failing output when reporting a fix.

When changing packaging or discovery, also install the built wheel in a fresh environment with `certbot==5.9.0`. Run `certbot plugins --text` and `certbot certonly --help dns-hosttech` from outside the source checkout. Exercise the public interface against the local fake; private CRUD tests alone do not prove Certbot integration. Hosted CI, real Hosttech propagation and real certificate issuance are separate evidence boundaries.

The lock is generated from `pyproject.toml`, not edited by hand:

```sh
uv pip compile pyproject.toml --extra dev --universal --generate-hashes --output-file requirements-dev.txt
```

Use `--upgrade-package <name>` for a targeted update. After dependency updates, regenerate the universal lock and check Python 3.11–3.14. Review Dependabot-generated locks against the same process; do not accept interpreter-specific drift silently.

## OSS workflows and delivery

Keep external Actions pinned to full commit SHAs, checkout credentials disabled and permissions scoped to each job. Preserve Plumber's upstream policy and failing grade-B gate, explicit binary version and attestation verification. Do not weaken controls to obtain a passing score. Score publishing stays off for private repositories and pull requests. See `.github/plumber/README.md` for hosted setup boundaries.

Update README and CHANGELOG when behavior changes. Preserve Apache-2.0 licensing. Never include tokens, INI files, private keys, virtual environments, build output or test caches in a patch. Report vulnerabilities through `.github/SECURITY.md`.

Preserve unrelated work. Never create a git commit; stage only authorized paths and leave the commit to the maintainer. Do not push, publish, change repository visibility/settings, post externally or modify a BunkerWeb checkout without explicit task authorization. A future BunkerWeb integration must pin the actual reviewed plugin commit archive and generated hash, not a moving branch or an invented SHA.

Codex sessions prefix shell commands with `rtk` and use `python3` on the host. Keep user-facing reports concise; code, documentation and proposed commit messages use normal English.
