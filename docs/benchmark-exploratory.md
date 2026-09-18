# Exploratory API pilot

This is a small operational pilot, not a publishable efficacy benchmark. It tests API
access, response capture, usage accounting, and literal preservation before the full
quality-gated campaign. It does not replace that campaign's approvals or evidence.

## Frozen scope

- Models: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-6-astra`.
- Arms: `baseline`, `concise`, `caveman`, `if`.
- Cases: the English and Russian `preserve-config` prompts; one repetition.
- At most 32 sequential generation requests; no retries or resume.
- Responses API, global endpoint, default service tier, medium reasoning and verbosity,
  1,024 maximum output tokens, explicit cache mode without breakpoints (no cache writes
  or reads expected), 30-minute TTL setting, no tools, no stored responses.
- USD 5 local exposure limit; dated price snapshot, including cache writes and reads.

The launcher reserves a conservative per-request amount before sending it, then settles
only complete validated usage. Unknown delivery or cost retains the reservation and stops
the run. Its input envelope (UTF-8 bytes plus 65,536 tokens) is a repository reservation
contract, not a provider guarantee about tokenization or the account's invoice. The limit
applies to this run, not to other clients using the same OpenAI project. Pricing is rejected
if more than seven days old. See the [dated source](https://developers.openai.com/api/docs/pricing).

## Launch

The workflow must first be reviewed and merged into `main`. Ensure the `benchmark-live`
environment contains `OPENAI_API_KEY`. The launcher requires GitHub Actions, `main`, and
the first run attempt. The key is passed only to the live step; offline tests and the dry
run have no key. Nothing is launched by a push or pull request.

Immediately before dispatch, inform the operator that provider requests are about to
start, including the models, 32-request maximum, no retries, and USD 5 exposure limit.
Then manually run **Exploratory API pilot** on `main`, checking the cost confirmation, or:

```bash
gh workflow run benchmark-exploratory.yml --repo agent-axiom/laconian \
  --ref main -f confirm_cost=true
```

Do not use GitHub's **Re-run jobs** action. A stopped run is preserved as failed/partial;
correct the cause and obtain authorization for a fresh dispatch and fresh budget. Never
overwrite the previous artifacts or silently substitute an inaccessible model.

GitHub environment protection rules are managed separately. This workflow does not create
reviewers or deployment restrictions. A repository maintainer can edit workflow code; the
workflow checks are not a substitute for account-level access and spend controls.

## Inspect results

Download `exploratory-pilot-<run_id>-<run_attempt>` from the workflow run. The artifact
contains separate dry-run and live directories. The live directory preserves the plan,
source snapshots and hashes, price snapshot, request reservations, raw response bodies,
validated usage, failures, and an operational summary. Model output is untrusted data:
inspect it as text, never execute it. Artifacts expire after 90 days; retain a copy before
expiry if needed. They are not automatically published as benchmark results.

The summary distinguishes completed, failed, and unattempted calls and preserves unknown
cost exposure separately from settled cost. Literal checks alone do not establish semantic
task success. Output usage includes reasoning; non-reasoning output tokens are not an exact
visible-text count. Do not infer a winner, cost saving, or paired brevity improvement from
this pilot. A later campaign needs broader cases, repetitions, blind semantic judgments,
matched successful pairs, and complete provenance under `benchmarks/methodology.md`.

## Offline checks

Only the Python standard library is needed:

```bash
python tests/test_exploratory_pilot.py
python tests/test_exploratory_workflow.py
python tools/exploratory_pilot.py --dry-run --output build/exploratory-pilot-new \
  --revision <exact-40-character-commit-sha>
```

Use a new output directory each time. Dry runs do not construct an HTTP connection or
read the API key. Test responses are synthetic and are not empirical benchmark evidence.
