# Security Policy

## Supported version

Security fixes are applied to the latest release and the default branch while the project remains pre-1.0.

## Report a vulnerability

Use GitHub private vulnerability reporting for this repository. Do not open a public issue for a suspected vulnerability.

Include reproduction steps using synthetic data. Do not attach real AI-use requests, review bundles, credentials, authorization headers, internal URLs, or personal information.

## Security boundary

The version 0.1 core makes no network calls. Users are responsible for access controls, retention, encryption, and provider review when adding adapters, databases, hosted services, or model APIs.

The `sanitize` command reduces common disclosure risks but is not an anonymization guarantee. Inspect sanitized artifacts before sharing them.

Bundle hashes detect changed files. They are not signatures, do not prevent an
attacker from recomputing hashes, and do not establish authenticity.
