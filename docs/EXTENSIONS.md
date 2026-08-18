# Optional extensions

Version 0.1 stores each review as a local directory and requires no external
service. Organizations can add adapters or centralized storage without changing
the review model.

## Preserve the bundle contract

An extension should retain:

- normalized intake;
- findings and open questions;
- evidence metadata separate from evidence content;
- policy identity and version;
- the draft assessment;
- artifact hashes; and
- a distinct, attributable human decision.

The review-bundle manifest is the interchange format. An external system should
be able to export a valid bundle for independent verification.

## Possible additions

- Intake and write-back adapters for an organization's existing workflow.
- SQLite for local search and history.
- PostgreSQL for controlled team queues, retention, and reporting.
- Object storage for large evidence files, with metadata and hashes kept separately.
- Retrieval only after a measured need and representative evaluation.

External systems introduce authorization, encryption, deletion, legal hold,
residency, backup, tenant isolation, and incident-response responsibilities.
Those controls belong to the deploying organization and are not supplied here.

Prior reviews are context, not authority. Store the policy version with every
record and re-evaluate when the policy changes.
