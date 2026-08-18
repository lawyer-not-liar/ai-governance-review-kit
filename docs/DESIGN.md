# Design

## Purpose

The AI Governance Review Kit turns a structured AI-use intake and an organization-owned policy into a traceable draft assessment. It is intentionally local-first, deterministic, and human-gated.

The core workflow is:

```text
intake -> validation -> policy evaluation -> draft bundle -> human decision
```

The package does not make organizational decisions, provide legal advice, retrieve evidence, or determine regulatory compliance.

## Trust boundaries

The system keeps four sources distinct:

1. Requester-supplied facts.
2. Requester-supplied evidence references.
3. Findings produced by versioned policy rules.
4. Decisions recorded by an identified human reviewer.

Generated prose can explain structured findings but cannot change their status or create a decision.

## Intake and policy

JSON Schemas define the canonical intake, policy, findings, manifest, and decision formats. Unknown material facts remain explicitly `unknown` and become open questions rather than inferred answers.

Policy conditions use a closed operator vocabulary. Policy files are data and cannot execute code. A saved bundle includes an exact snapshot of the policy used for evaluation.

## Review bundles

Each saved run contains normalized intake, findings, evidence references, open questions, the policy snapshot, and a draft assessment. The manifest records the tool and policy versions and SHA-256 hashes for every artifact. These hashes detect changes; they are not digital signatures and do not establish who created an artifact or whether its contents are true.

Bundle verification rejects changed, missing, unexpected, symlinked, or unsafe-path artifacts. Writes use temporary files and atomic replacement where the platform supports it.

## Human decision gate

The `decide` command operates only on a verified bundle. Approval requires:

- No unresolved open questions.
- A documented override with rationale for every blocking finding.
- At least one condition for `approved_with_conditions`.
- Confirmation of independent human review.

Missing facts are resolved by updating the intake or evidence and generating a new immutable bundle. A blocking finding cannot be cleared by acknowledgement alone.

## Privacy and sanitization

The default implementation makes no network calls. Runs are excluded from Git, and `review --no-save` supports ephemeral use.

Sanitization creates a separate bundle, replaces direct identifiers and requested sensitive fields, rebuilds derived artifacts, and verifies the resulting hashes. It is a support aid rather than an anonymization guarantee, so a person must inspect sanitized output before sharing it.

## Extension boundaries

Version 0.1 does not include ticketing adapters, databases, web services, precedent search, or live model providers. Extension contracts are documented separately so integrations can be added without weakening the core trust boundaries.

Any future database should remain optional. Files are the portable system of record for the reference implementation; a database may provide indexing, retention controls, access control, or reporting without becoming required for local use.
