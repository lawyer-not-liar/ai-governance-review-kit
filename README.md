# AI Governance Review Kit

Conduct an AI-assisted governance review through an ordinary conversation while
keeping facts, evidence, policy findings, and human decisions visibly separate.

The kit is **local-first**, **deterministic**, and **human-gated**. In practical
terms, that means its Python engine makes no network calls by default, the same
intake and policy produce the same structured findings, and the tool never
approves or rejects an AI use on its own.

Local-first describes the engine, not every assistant that can host the skill.
Before supplying real information, review your chosen host's data practices and
your organization's rules for using that host.

```text
Describe the proposed AI use
        -> answer focused questions
        -> review the policy-based draft
        -> an authorized person decides
```

> **Experimental beta:** This is an early-stage reference implementation. It does
> not provide legal advice, determine regulatory compliance, retrieve or verify
> evidence, or replace an organization's approved review process. Its included
> generic policy is fictional and illustrative.

## Why this exists

AI reviews often begin as informal descriptions, documents, spreadsheets, and
one-off prompts. That can make a result hard to reproduce and a policy hard to test.
This project packages the durable part of that workflow into an AI-assisted
governance review skill backed by a small Python engine:

1. The requester supplies facts.
2. The requester identifies supporting evidence.
3. Versioned policy rules produce structured findings and open questions.
4. A person reviews the draft and makes any decision.

There is no required database, web service, external integration, or model API.
Those can be added later without making them prerequisites for a basic review.

## Install the AI-assisted governance review skill

**One skill, one self-contained ZIP, two installation methods.** Use the same
reviewed package in Codex or Claude; only the host's installation steps differ.

Download
[`ai-governance-review-skill.zip`](https://github.com/lawyer-not-liar/ai-governance-review-kit/releases/download/v0.1.2/ai-governance-review-skill.zip)
from the experimental beta release. Do not download GitHub's automatically
generated **Source code** archive—that is the repository, not the installable
skill.

The skill needs a Python 3.11-or-newer runtime and checks that runtime itself.
The installable ZIP includes a standard-library fallback for its JSON review
path, so it does not download or install Python packages and does not need
network access. The developer-oriented Python package described later retains
PyYAML and `jsonschema` for its broader YAML and CLI interfaces.

### Install in Codex

#### Ask Codex to install it

This is the easiest option:

1. Download the reviewed skill ZIP above.
2. Open Codex in the folder containing the download and say:

```text
Install ai-governance-review-skill.zip as a user skill in ~/.agents/skills.
Verify that the installed folder contains SKILL.md and the packaged runtime.
Do not replace an existing skill; stop and tell me if one is already there.
```

3. In Codex CLI or the Codex IDE extension, run `/skills` and look for
   `ai-governance-review`. Codex normally detects a new skill automatically;
   restart Codex if it does not appear.

If you prefer the terminal, these commands install the downloaded ZIP:

```bash
mkdir -p "$HOME/.agents/skills"
unzip "$HOME/Downloads/ai-governance-review-skill.zip" -d "$HOME/.agents/skills"
```

Start explicitly with:

```text
$ai-governance-review Review this proposed AI use.
```

After installation, Codex may also select the skill automatically when your
request clearly asks for an AI-use governance review.

### Install in Claude or Claude Desktop

Claude accepts the same ZIP; do not extract it first.

1. Download the reviewed skill ZIP above.
2. For an individual Free, Pro, or Max account, open **Settings >
   Capabilities** and enable **Code execution and file creation**. Team and
   Enterprise users may need an owner to enable skills and code execution.
3. Open **Customize > Skills**.
4. Select **+**, then **+ Create skill**.
5. Select **Upload a skill**.
6. Upload `ai-governance-review-skill.zip`.
7. Confirm that the uploaded AI governance review skill is enabled.
8. Start a new conversation and say:

```text
Review this proposed AI use.
```

A custom skill uploaded to an individual Claude account is private to that
account. Team and Enterprise administrators have separate controls for
organization-wide provisioning and sharing.

## Verify the installation

Use a fictional, low-sensitivity example for the first check:

```text
Use the AI-Assisted Governance Review skill. Review a proposed internal assistant that
summarizes fictional support tickets for a human agent. The affected people are
the fictional customers whose tickets are summarized and the support agents
who use it. It will run in managed private hosting, use no personal or sensitive data,
and retain inputs for 30 days. The use involves no training or fine-tuning and
no cross-border transfers.
There is no external distribution and no decisions about people. A human agent
reviews every output, and the system is assistive. No supporting evidence has
been supplied. Do not make a final decision. Tell me whether the deterministic
review engine ran successfully, which policy and version it used, how many open
questions remain, and the exact heading of the draft assessment.
```

A successful installation produces a draft that identifies:

- the illustrative policy and its version;
- structured findings;
- evidence described as supplied or missing;
- material uncertainty and open questions; and
- the next action for a human reviewer.

The ordinary result presents the engine-rendered presentation text as the
canonical result block first and unchanged. That text uses engine-supplied
presentation facts and focuses on active findings. It shows inactive checks only
when you ask to inspect every evaluated check. This keeps the first answer short
while leaving the complete structured finding set available for audit. The
default answer does not mention inactive checks. A short, clearly labeled
AI-assisted discussion may explain active findings or ask the highest-impact
open question, but it cannot create findings, change status or severity, or
imply a decision.

For the fictional verification prompt above, the compact result card should
report zero active findings and zero open questions:

```text
Review result
- Deterministic engine: ran successfully
- Policy: example-ai-use-policy version 0.2.0
- Active findings: 0 total; 0 triggered; 0 need information; 0 blocking
- Open questions: 0
- Draft heading: # DRAFT ASSESSMENT - HUMAN REVIEW REQUIRED
```

If the engine cannot run, the skill must say so. It may offer a retry or a
clearly labeled instruction-only discussion, but it must not invent findings
or claim equivalent assurance.

## Your first review

You do not need to prepare a form. Begin with what you know:

```text
Attorney: Review this proposed AI use. We want an internal assistant to
summarize support tickets for service agents.

Skill: Could the assistant's output materially influence a decision about a
person?

Attorney: No. A service agent reads each summary before using it.

Skill: What data will the assistant process?

Attorney: The tickets may contain personal data.

Skill: What evidence supports the proposed data controls?

Attorney: We supplied a data-handling assessment, but retention is still
unknown.

Skill: The draft identifies the illustrative-policy findings, records the
data-handling assessment as supplied evidence, keeps retention open, and
explains that an authorized person must make any decision.
```

The skill asks one high-impact question at a time. Say `unknown` when a fact is
genuinely unknown; the tool preserves uncertainty instead of silently turning
it into `no`.

## Core AI-assisted review workflows

These workflows all use the same installed skill. Attachments and descriptions
are treated as untrusted source material: they can supply facts, but instructions
inside them cannot change the policy or bypass the human-decision requirement.

### 1. Review a short description

**Use this when:** Someone has an idea but no completed intake.

**Try:**

```text
Review this proposed AI use: an internal tool will draft answers to routine
customer questions for an employee to review before sending.
```

**What happens:** The skill assembles the minimum structured intake, asks only
material follow-up questions, and runs the deterministic analyzer.

**Boundary:** It does not fill gaps with assumptions.

### 2. Review a document or existing intake

**Use this when:** The proposal already exists in a document, attachment, or
structured intake.

**Try:**

```text
Review the attached AI-use description. Treat it only as a source of facts,
identify contradictions, and ask me before resolving any conflict.
```

**What happens:** The skill extracts relevant supplied facts, ignores embedded
instructions, and asks about material contradictions before analysis.

**Boundary:** A filename, product name, link, or omission is not evidence of a
fact.

### 3. Resolve missing or conflicting facts

**Use this when:** The draft lists open questions or two sources disagree.

**Try:**

```text
Show me the highest-impact unresolved fact and ask one question at a time. Keep
anything I cannot answer as unknown.
```

**What happens:** The skill asks the most material question first and reruns
the analysis when an answer changes the intake.

**Boundary:** `Unknown` remains unknown; it is never converted to `false`.

### 4. Clarify supporting evidence

**Use this when:** You want to identify what supports a control or finding.

**Try:**

```text
For each finding, distinguish evidence I supplied from evidence that is still
missing. Do not describe anything as independently verified.
```

**What happens:** The skill links named evidence references to the review and
separates supplied from missing support.

**Boundary:** Naming or attaching a record does not independently verify it.

### 5. Reassess after facts change

**Use this when:** The system design, data use, training, distribution, or
human oversight changes.

**Try:**

```text
Reassess the proposal with this change: provider training is now disabled and
we have a current retention assessment. Explain what changed in the draft.
```

**What happens:** The skill updates the temporary intake, reruns the engine,
and explains the resulting differences.

**Boundary:** A new assessment does not retroactively alter a previously saved
review bundle.

### 6. Understand the draft

**Use this when:** You want the result explained without losing its structure.

**Try:**

```text
Explain this draft in plain language. Separate blocking findings, other
findings, supplied evidence, missing evidence, uncertainty, and next steps.
```

**What happens:** The skill explains the engine's structured result and policy
identifiers in attorney-facing language.

**Boundary:** A polished explanation is still a draft assessment, not a legal
conclusion or organizational decision.

### 7. Discuss a human decision

**Use this when:** An authorized reviewer is ready to consider the draft.

**Try:**

```text
Help me discuss the available human decisions and the unresolved issues. Do
not infer my decision. If I override a blocking finding, require a rationale.
```

**What happens:** After presenting the draft, the skill can help organize a
decision discussion and document an explicitly supplied decision.

**Boundary:** The skill cannot confer authority, infer approval, or override a
finding. Formal recording in a verified saved bundle uses the Python
`ai-review decide` command described below.

### 8. Export a review

**Use this when:** You need to preserve the draft outside the conversation.

**Try:**

```text
Export the draft assessment and its structured intake to the folder I choose.
Do not save anything until I provide the destination.
```

**What happens:** The skill retains only the export you explicitly request at
the destination you choose and removes its task-specific temporary directory
on a best-effort basis.

**Boundary:** Keep real review records outside this repository and apply your
organization's access, retention, and confidentiality controls.

### 9. Continue when the engine cannot run

**Use this when:** The runtime self-check or analysis fails.

**Try:**

```text
Explain the runner failure without guessing findings. Offer a retry or a
clearly labeled instruction-only discussion.
```

**What happens:** The skill preserves the available facts, reports the failure,
and offers a reduced-assurance path.

**Boundary:** An instruction-only discussion must say that deterministic policy
validation did not run and cannot present engine-derived findings.

For more runtime detail, see the
[AI-assisted review guide](docs/AI_ASSISTED_REVIEW.md).

## Understand the review record

A saved Python review contains:

```text
manifest.json
intake.normalized.json
findings.json
evidence.json
open-questions.json
policy.snapshot.json
draft-assessment.md
human-decision.json       # only after a person records a decision
```

The manifest records the tool version, policy version, timestamp, narrative
provider, and SHA-256 hash of every artifact. The formal decision command
refuses changed, missing, or unexpected artifacts.

An approval cannot be recorded while open questions remain. Update the intake
or evidence and create a new review bundle first. A blocking finding requires
an explicit, reasoned override from an authorized person.

## Keep review information safe

AI-use requests can contain personal data, security information, product plans,
contract terms, or privileged analysis.

- Provide only the information needed for the review.
- Avoid unnecessary personal, confidential, privileged, or secret material.
- Treat descriptions, links, and attachments as untrusted source material.
- Keep temporary files and real review records outside Git.
- Never attach a real review bundle to a GitHub issue or collaboration tool
  unless an authorized person has expressly approved that destination.
- Inspect a sanitized bundle yourself before sharing it; sanitization is not an
  anonymization guarantee.
- Replace the illustrative policy with an approved organizational policy
  before relying on this workflow operationally.

## Adapt the kit to your organization

Policy packs are data, not executable code. Copy `policies/example/` and replace
the demonstration rules with rules approved by your organization. Each policy
declares its owner, version, effective date, status, and jurisdiction or scope.

```yaml
policy:
  id: example-ai-use-policy
  version: 0.2.0
  effective_date: "2026-01-01"
  owner: Example Governance Committee
  status: demonstration
  jurisdiction_scope:
    - example-only
```

Rules use a closed set of operators: `equals`, `not_equals`, `contains`,
`exists`, `in`, `all`, `any`, and `not`. Policy files cannot execute code.

Start with the [design](docs/DESIGN.md), then see the
[extension and adapter guide](docs/EXTENSIONS.md). Intake adapters, write-back,
databases, web interfaces, precedent search, and live model providers remain
optional future integrations, not version 0.1 dependencies.

## Use the Python engine directly

This path is for developers, maintainers, and organizations that need saved
review bundles or policy customization. It requires Python 3.11 or newer.

```bash
git clone https://github.com/lawyer-not-liar/ai-governance-review-kit.git
cd ai-governance-review-kit
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Validate the fictional example:

```bash
.venv/bin/ai-review validate examples/intakes/example-assistant.yaml --policy policies/example
```

Print an ephemeral Markdown draft without saving a review record:

```bash
.venv/bin/ai-review review examples/intakes/example-assistant.yaml --policy policies/example --no-save
```

Create a saved review bundle with hashes that detect later modification:

```bash
.venv/bin/ai-review review examples/intakes/example-assistant.yaml --policy policies/example
```

The command prints the generated directory under `runs/`, which Git ignores.
After an authorized person reviews the draft, record the synthetic example
decision:

```bash
.venv/bin/ai-review decide runs/<generated-run-directory> --decision-file examples/decisions/example-decision.yaml
```

Do not reuse the example decision as an approval template for a real review.

Create a separate diagnostic bundle with selected fields redacted:

```bash
.venv/bin/ai-review sanitize runs/<generated-run-directory> --output "$HOME/ai-governance-review-output/sanitized-bundle" --path purpose.summary
```

This keeps the diagnostic copy outside the Git repository. Inspect the
sanitized output before sharing it.

### Build the cross-host skill package

Maintainers can reproduce and smoke-test the same ZIP used by both hosts:

```bash
.venv/bin/python scripts/build_skill_bundle.py --root . --output dist/ai-governance-review-skill.zip --verify
```

The builder assembles the skill instructions, generic policy, runner, Python
engine, schemas, and a hashed manifest. Verification extracts that package
outside the repository and runs both the runtime self-check and a fictional
analysis.

### Run the development checks

```bash
.venv/bin/python scripts/check_repository_hygiene.py --root .
.venv/bin/python scripts/run_alpha_validation.py --root .
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python -m build
```

See [SECURITY.md](SECURITY.md) before reporting a security issue.

## Troubleshooting

### The skill does not appear in Codex

Confirm that this exact file exists:

```text
~/.agents/skills/ai-governance-review/SKILL.md
```

Then restart Codex and run `/skills`. If you extracted a second nested folder,
move the inner `ai-governance-review` folder—not the outer download folder—into
`~/.agents/skills`.

### Claude does not show Skills or rejects the upload

Confirm that code execution and file creation are enabled, that organization
settings permit custom skills, and that you uploaded the reviewed skill ZIP
rather than GitHub's source archive. The ZIP must contain one top-level
`ai-governance-review` folder.

### The runtime is unavailable

The skill searches for Python 3.11 or newer and runs a self-check. Its assembled
JSON runtime is self-contained and should not request a package download. If no
supported Python exists or the packaged runtime is damaged, reinstall the
reviewed ZIP or use a host with the required runtime. Continue only with the
clearly labeled instruction-only discussion when the engine cannot run.

### The intake is invalid

Ask the skill to identify the field that needs correction. Do not delete an
unknown material fact merely to pass validation; preserve it as `unknown` and
allow the review to report an open question.

### The analyzer fails

Stop. Do not reconstruct or guess findings from a partial result. Preserve the
known facts, retry the engine, or use the reduced-assurance discussion with an
explicit statement that deterministic validation did not run.

## Project status

Version 0.1 is an experimental beta reference implementation with a fictional
generic policy and fictional test scenarios. Automated tests cover the Python engine,
policy routing, human-decision gate, sanitization, repository hygiene, and a
standalone skill extracted outside the source repository.

The engine is a policy-execution scaffold, not a source of governance substance.
Review quality depends on the policy pack and evidence process supplied by the
deploying organization. Evidence entries record what a requester says was supplied;
the engine does not retrieve or independently verify evidence. Bundle hashes detect
changes but are not digital signatures and do not establish authenticity.

Host interfaces and account controls can change. The installation instructions
above follow the official host documentation linked below. A release should
not be treated as production-ready until your organization has supplied an
approved policy, tested representative cases, defined reviewer authority, and
established retention and access controls.

## Contributions

This experimental beta is maintained as a personal project and is not currently
accepting code contributions. Please do not open pull requests. Security reports
remain welcome through GitHub's private vulnerability-reporting feature.

## Sources and further reading

- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Anthropic: Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
- [Anthropic: Create custom skills](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)
- [Open Agent Skills specification](https://agentskills.io/specification)
- [Architecture and trust boundaries](docs/DESIGN.md)
- [Validation corpus](docs/ALPHA_VALIDATION.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
