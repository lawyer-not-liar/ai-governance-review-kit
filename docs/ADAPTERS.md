# Adapter contracts

The core package is local and integration-neutral. Adapters should translate external systems into or out of the canonical bundle without changing policy semantics.

## Intake adapter

An intake adapter returns a dictionary conforming to `intake.schema.json`. It owns source-specific field mapping and must preserve the source record identifier in `request.id` or `request.metadata`.

```python
class IntakeAdapter(Protocol):
    def load(self, reference: str) -> dict[str, object]: ...
```

Validate the returned intake before policy evaluation. Keep authentication, pagination, and ticket-specific fields outside the core package.

## Evidence adapter

Evidence metadata and evidence content are separate concerns. A future adapter should return bytes plus provenance metadata and state whether retrieval and integrity checks succeeded. A URL alone is not verified evidence.

## Narrative provider

Narrative providers receive normalized intake, structured findings, and open questions. They return explanatory prose only. They cannot change finding status or create an organizational decision.

## Write-back adapter

A write-back adapter is intentionally absent from version 0.1. Any implementation must require:

1. A bundle that passes hash verification.
2. A valid `human-decision.json` tied to the same policy version.
3. An explicit confirmation naming the target system and record.
4. Idempotency protection.
5. A durable audit record of the exact content sent.

Write-back must fail closed when identity, authorization, target visibility, or artifact integrity cannot be verified.
