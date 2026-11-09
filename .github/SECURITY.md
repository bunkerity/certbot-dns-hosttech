# Security policy

Report suspected vulnerabilities privately to **security@bunkerity.com**, with reproduction details and the affected version.
Do not include API tokens, credentials files or customer data. Do not open a public issue for an undisclosed vulnerability.

The latest released version and current main branch are supported. Upgrade to the latest release before requesting a fix for an older version. Security reports include token exposure, unauthorized DNS changes, unsafe cleanup and supply-chain vulnerabilities.

Maintainers aim to acknowledge private reports within 14 days, assess severity and coordinate a fix with the reporter. The target for confirmed vulnerabilities is a fix or documented mitigation within 60 days of a public report, with critical issues prioritized immediately. These are response targets, not claims about historical response times. If no acknowledgement arrives within 14 days, send a follow-up to the same address.

Keep exploit details private until coordinated disclosure. Released fixes identify applicable public CVE or advisory identifiers in the changelog and credit reporters who consent. Maintainers review dependency alerts and CodeQL findings, investigate fuzzing crashes, and resolve confirmed vulnerabilities before the next release.

## Security design and limits

The plugin delegates ACME cryptography to Certbot and TLS to requests and the Python/OpenSSL stack. It implements no cryptographic primitives, password database or random-number generator. TLS certificate verification is enabled and redirects are disabled. Operators must maintain trusted CA certificates and update dependencies.

Provider responses and credential files are untrusted input. The plugin validates API envelopes, zone and record identifiers, token syntax and DNS label boundaries. It creates independent TXT records and deletes only the identifiers returned to this process. Diagnostics omit credential contents, provider response bodies and request exception text.

The API token grants DNS access and must remain in a restricted credentials file. In-memory record tracking cannot recover from process termination or an ambiguous create timeout. The README explains manual recovery, DNS delegation limits and the unverified live propagation boundary. These limits are part of the supported behavior, not assurances that a real provider or ACME issuance has been tested.
