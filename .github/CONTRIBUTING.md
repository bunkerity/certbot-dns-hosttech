# Contributing

Use an issue to describe a bug or proposed change before a substantial pull request. Keep changes focused and update the README and changelog when behavior changes.

Install the development extra and run the lint, typing, test and build commands in the [README](../README.md#development). CI covers Python 3.11–3.14 with Certbot 5.9.0. Tests use mocks or a local fake; never require a real Hosttech token.

For a bug fix, first demonstrate a failing regression test, then make it pass. Preserve existing TXT records and test failures as well as successful creation/cleanup. Do not log raw API error bodies, request exception text or malformed credential contents.

Never submit API tokens, credentials files, private keys or customer identifiers. Report vulnerabilities through the [security policy](SECURITY.md).

Pull requests require maintainer review. Contributions are licensed under Apache-2.0.
