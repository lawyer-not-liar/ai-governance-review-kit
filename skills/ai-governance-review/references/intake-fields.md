# Intake fields

Build a JSON intake that conforms to the kit's intake schema. Record only facts supplied by the requester or an identified evidence source. For a missing material fact, use the literal string `unknown` where the field permits it; never convert `unknown` to `false`.

| Intake path | Plain-language meaning | Processing rule |
| --- | --- | --- |
| `request.title` | Name of the proposed AI use | Use the requester's description. |
| `purpose` | What the use does, its outcome, affected people, and deployment scope | Preserve uncertainty and distinguish a prototype, internal, external, or `unknown` scope. |
| `system` | System name, provider, hosting, autonomy, and human oversight | Ask about human intervention when it may affect the review. |
| `data` | Data categories, personal or sensitive data, training, retention, and transfers | Do not infer handling practices from the provider name. |
| `outputs` | Output types, recipients, external distribution, and decisions influenced | Ask whether people can be materially affected by a decision. |
| `evidence` | Named records supplied for the review | Record references; a reference alone is not verification. |

## Transparent processing placeholders

When a required administrative field is not material and is not supplied, record each generated value in `request.metadata.generated_placeholders`:

```text
request.id -> generated `conversation-review-<timestamp>`
request.owner.name -> `Not supplied`
request.owner.email -> `not-supplied@example.invalid`
request.metadata.generated_placeholders -> list of generated paths
```

Explain these placeholders in the summary. They are administrative defaults, not supplied facts.
