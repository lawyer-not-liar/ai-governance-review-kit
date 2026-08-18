# Alpha Validation

The alpha corpus tests whether the demonstration policy produces useful,
traceable review signals across materially different fictional proposals. It
supplements unit tests with scenario-level expectations and a structured human
review workbook. The Markdown workbook is a maintainer evaluation artifact
retained to evaluate output quality; it is not required of ordinary attorney
users.

All names, organizations, facts, decisions, evidence references, and policies
in the corpus are invented for this repository. The golden expectations define
the intended behavior of the demonstration policy; they are not legal
conclusions or a substitute for an organization's approved policy.

## Run the automated gate

```bash
python scripts/run_alpha_validation.py --root .
```

The command validates each intake and policy, evaluates findings and open
questions, exercises supplied decision records, and compares the results with
`examples/alpha/scenarios.yaml`. It exits unsuccessfully if any status,
question, blocking finding, or decision differs from its golden expectation.

The corpus covers:

1. A low-risk assistive use.
2. Personal data with missing evidence.
3. Personal data with the required evidence reference.
4. Training with missing evidence and a decline.
5. Training with evidence and a documented override.
6. External distribution controls.
7. A consequential decision influence.
8. Autonomous operation without human oversight.
9. Unknown material facts.
10. Multiple simultaneous risks and a decline.
11. Overlapping permissive and restrictive policy signals.
12. Personal data combined with external distribution and missing supporting records.
13. Sensitive data with missing assessment evidence.
14. Cross-border transfers with missing assessment evidence.
15. Autonomous operation with no supplied oversight plan.
16. Third-party hosting with a supplied provider assessment.

The low-risk, personal-data missing-evidence, external-distribution, and combined
personal-data/external-distribution scenarios cover all four combinations of
personal data and external distribution when training or fine-tuning is false.
Training behavior is covered separately by missing-evidence, documented-override,
and combined-risk scenarios.

## Generate the maintainer evaluation artifact

```bash
python scripts/run_alpha_validation.py --root . \
  --report /tmp/ai-governance-alpha-review.md
```

The generated workbook is a maintainer evaluation artifact. It includes each
review focus, golden expectation, draft assessment, and a scorecard. Reviewers
score factual accuracy, policy traceability, question quality, proportionality,
actionability, and false confidence from 1 to 5, then mark the scenario Accept,
Revise, or Reject. Ordinary attorney users do not need to generate or complete
this workbook to use the AI-assisted governance review skill.

## Release gate

Before changing repository visibility or describing the kit as ready for
general use:

- All automated scenarios must pass.
- At least one person must complete every workbook scorecard.
- A second person should review the blocking, override, and overlapping-policy
  scenarios.
- No scenario may remain marked Reject.
- Any score below 3 must have a resolved issue or a documented decision to
  defer it.
- Changes to the demonstration policy must update golden expectations through
  an independently reviewed pull request.

The workbook should normally remain outside Git because reviewer notes may
contain names, organizational context, or non-public policy judgments.
