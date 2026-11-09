# Changelog

## Unreleased

- Add offline coverage-guided fuzzing for zone selection, credentials and API diagnostics.
- Report non-UTF-8 credential files as actionable, sanitized parsing errors.
- Publish signed in-toto provenance and its Sigstore verification bundle with release assets.
- Upload release assets before publishing both stable releases and prereleases, supporting immutable releases.
- Upload CodeQL pull request findings and document review, testing and vulnerability response policies.

## v0.1.0 - 2026/11/09

- Add Hosttech DNS-01 authentication for Certbot 5.9.x and Python 3.11–3.14.
- Find the most specific zone across all API pages.
- Support apex and wildcard TXT values; delete only records created by the plugin.
- Validate credentials and sanitize API errors, with offline integration tests.
- Add packaging checks, hashed development dependencies and pinned security workflows.
- Publish to PyPI with Trusted Publishing and PEP 740 attestations.
- Require reviewer approval and a verified signed tag before publishing a release.
- Detect PEP 440 prereleases such as `0.2.0rc1` for the GitHub release flag.
- Use absolute README links so the PyPI project page renders them.
