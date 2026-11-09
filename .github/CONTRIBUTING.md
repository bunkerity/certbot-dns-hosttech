# Contributing

Use an issue to describe a bug or proposed change before a substantial pull request. Keep changes focused and update the README and changelog when behavior changes.

Install the development extra and run the lint, typing, test and build commands in the [README](../README.md#development). CI covers Python 3.11–3.14 with Certbot 5.9.0. Tests use mocks or a local fake; never require a real Hosttech token.

For a bug fix, first demonstrate a failing regression test, then make it pass. Preserve existing TXT records and test failures as well as successful creation/cleanup. Do not log raw API error bodies, request exception text or malformed credential contents.

Never submit API tokens, credentials files, private keys or customer identifiers. Report vulnerabilities through the [security policy](SECURITY.md).

## Review and verification

Submit changes as pull requests, including maintainer changes. A maintainer other than the author reviews each change before merging. Re-request review after changing reviewed code; do not use administrator bypass for routine work. Repository settings determine the enforced approval count and required checks.

Black (160 columns) defines Python formatting; Ruff checks imports and common errors, and mypy checks the package in strict mode. Resolve lint, typing, test and CodeQL findings before merging. Treat new warnings as defects to investigate, rather than suppressing them without a documented reason.

Add automated tests for new functionality and fixes. A regression test must fail against the unfixed implementation before it is trusted. Keep the authenticator's 100% statement and branch coverage gate, including failure paths. CI runs these checks on pull requests and main, with offline Atheris fuzzing for provider data and credential diagnostics. Add a non-secret regression input when fuzzing finds a defect.

Reviewers of security-sensitive changes must understand least privilege, complete input validation, safe failure, separation of credentials from diagnostics, and common Python and HTTP errors. Use the [OWASP secure coding practices](https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/) and the [Python security considerations](https://docs.python.org/3/library/security_warnings.html) as review references. Never replace a failed security check with a weaker gate.

Release notes in `CHANGELOG.md` describe user-visible changes and upgrade impact, including public vulnerability identifiers when applicable. Versions use semantic versioning and signed `v` tags. Before a release, complete review and all CI checks, then follow the release workflow's approval and attestation gates. Never reuse an already published PyPI version or immutable GitHub release tag.

Contributions are licensed under Apache-2.0.
