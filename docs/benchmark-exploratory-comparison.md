# Exploratory four-model comparison

This is the simplified, exploratory route authorized on 2026-09-18. It is **not**
the governed confirmatory campaign, publication-ready evidence, or a substitute
for its independent human audit. The previous 32-response pilot is separate.

## Frozen conditions

The comparison has 1,920 planned generation responses: four models
(`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-6-astra`), four arms
(`baseline`, `concise`, `caveman`, `if`), 12 scenarios in English and Russian,
and five repetitions. Model/case/repetition blocks and arm order are seeded.
Generation uses medium reasoning and verbosity, 1,024 output tokens, no
temperature, tools disabled, default service tier and `store: false`.

`evals/exploratory/response-cases.yaml` freezes the authored case definitions
from the experimental branch, separately from the older public smoke cases.
Original and frozen file SHA-256:
`99e4bcc61995f81a1668f9d05134cdf7a1cba31b09780aee6856d2d8ce1ea58e`.
The standalone sentence counter is copied from the repository scorer.
JSON rejects duplicate keys/nonfinite values; YAML uses a bounded safe loader
and rejects duplicate keys, aliases, anchors and explicit tags. These stricter
exploratory parsing rules are recorded in source, not substituted into published
governed evidence.

Every completed, nonblank generation is eligible for a blind Sol judgment,
including hard-check failures. The judge uses low reasoning/verbosity, 768
output tokens, no tools, and strict JSON Schema output. Its input contains only
an opaque ID, task prompt, locale, rubric, warning requirement and candidate
answer: no model, arm, repetition, token counts, cost or character counts.
Judge order is shuffled; identity mappings are stored separately. This blinds
metadata, not intrinsic writing style. Semantic success is derived from all
rubric items, warning compliance and absence of material contradiction.

## Cost and failure policy

One serial process shares a **USD 75 exposure cap** across generation and judging.
This is a dated-price usage estimate, not a provider invoice guarantee. Ordinary
input, cache reads, cache writes and output including reasoning are accounted
separately. Explicit 30-minute caching is requested without breakpoints.
The current price snapshot is dated 2026-09-18 and expires after seven days.
See [official pricing](https://developers.openai.com/api/docs/pricing) and
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Reserve before dispatch; persist raw bytes before parsing; settle only validated
usage and exact model/tier/cache provenance. No retries, resume, or automatic
reruns. Known billable incomplete/refused generations and malformed judgments
remain failures. Transport/accounting uncertainty stops the campaign with the
reservation outstanding. Authentication errors never retry. Credential-echo
bodies are withheld, oversized bodies retain only a bounded prefix; neither is
represented as a complete unchanged raw record. A time limit leaves room for
artifact upload before the GitHub job timeout.

## Reports and operation

Reports retain quality/error/coverage counts per model and arm. Descriptive
paired differences are `concise - if`, using only identical case/repetition
pairs where both arms pass hard and semantic checks. Incomplete generation or
judgment coverage suppresses brevity comparisons; failed/missing responses do
not become apparent savings. Nonreasoning tokens are **not** exact visible-text
tokens. Models are never pooled. No confidence intervals, significance claim or
public superiority claim is supplied by this exploratory report.

The manually dispatched `benchmark-comparison.yml` workflow runs only on `main`,
first attempt, with explicit cost confirmation. Locked dependencies, tests and
dry-run execute before the only step given `benchmark-live`'s API key. Pilot and
comparison share a concurrency group. Partial artifacts are always uploaded
with 90-day retention; archive them before expiration. Re-dispatch is a new paid
experiment and must not be used as an automatic retry.

```sh
uv run python tools/exploratory_comparison.py --dry-run \
  --output /existing-parent/new-evidence --revision <40-character-commit>
```

The operator informs the user immediately before paid dispatch and reports
progress every 15 minutes. After this route, governed implementation continues
separately; it must not silently reuse this run as confirmatory evidence or
assume authorization for an additional USD 75 campaign.
