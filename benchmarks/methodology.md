# Laconian benchmark methodology

This document defines what a reproducible Laconian comparison must disclose. The current
walking skeleton exercises the data path with synthetic replay data; it is not a public model
benchmark and contains no performance conclusion.

## Questions kept separate

The benchmark has two suites because they answer different questions:

1. The **activation suite** asks whether an agent host should select `if` for a user request.
   Stored expectations and local routing checks are proxies. A compatibility claim about a named
   host requires execution in that host.
2. The **response suite** deliberately applies each comparison instruction and measures the
   resulting answer. It bypasses automatic skill selection.

Activation accuracy is never combined with response quality or brevity.

## Fixed comparison arms

The four arm identifiers and contents are:

- `baseline`: no added instruction; its instruction hash is the SHA-256 of zero bytes;
- `concise`: exactly `Answer concisely.`;
- `caveman`: the full offline fixture from `JuliusBrussee/caveman`, pinned to upstream commit
  `781c384cafc28d7ca392014dbab569f985b5b2fd`, with fixture SHA-256
  `1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8` and MIT attribution;
- `if`: the exact bytes of `skills/if/SKILL.md` in the recorded repository revision.

Every attempt records the selected arm and its instruction SHA-256. A public run must also name
the repository revision and retain the Caveman provenance file. Changing any arm content creates
a different experiment; results from different hashes are not pooled.

## Forced instruction placement

The manifest fixes `instruction_placement: system_suffix`. In the current runner this means that
the complete arm content occupies the provider request's stable `instructions` slot; `baseline`
uses no added instructions. The user prompt is unchanged. A run must keep provider, exact model
identifier, generation settings, case text, repetition index, and available tools fixed across
arms. Host-specific prompt assembly must be disclosed and must not give one arm a privileged
location.

For OpenAI runs, `model` records the requested manifest identifier and `response_model` records
the public model identifier returned by the API. Every successful record must contain the latter,
and scoring rejects a run if successful records resolve to different models. Requested and
returned identifiers must both be disclosed; an alias is not silently presented as a dated model.

## Cases, repetitions, and randomization

Response scenarios are represented as an English/Russian pair with one shared `scenario_id`.
Activation scenarios use the same pairing rule but are not response records. The manifest fixes
the case files, repetition count, and arm-order seed.

For each case and repetition, the runner shuffles only the four-arm order with the recorded
arm-order seed. Case order remains the validated file order. A publication must report the
number of scenarios, localized records, repetitions, and terminal responses; a single smoke
repetition is architecture verification, not enough for an efficiency conclusion.

## Attempts, errors, and retries

Configuration and schema validation happen before provider calls. Transient rate-limit,
timeout, connection, and server failures may be retried only up to the manifest's bounded retry
budget. Every attempt remains in `raw.jsonl` with its attempt number, retry parent, terminal flag,
and recorded backoff. Exhausted retries and non-retryable errors are results, not missing rows.

An authentication error is non-retryable and stops the run. The partial raw file and incomplete
run log remain inspectable. Retry attempts count toward operational metrics but only a terminal
record is scored for a planned case/arm/repetition key.

## Quality gates

Scoring is ordered:

1. Check raw identity against the copied manifest and source case.
2. Apply the **hard gate**: provider success with a nonblank output, required and forbidden
   literals, one complete top-level JSON or YAML mapping with exactly the declared keys, and
   sentence bounds.
3. Optionally apply the **semantic gate** to hard-pass responses: required facts and any material
   warning are judged from a request that omits arm, provider, model, token count, and length.
4. Establish task success before calculating paired brevity.

Semantic results include judge provider, model, and prompt SHA-256. A semantic-gated report is
invalid if any hard-pass response lacks a judgment. Public semantic claims require a frozen judge
protocol and a disclosed human audit sample; the walking skeleton only attaches supplied judgment
records.

**A failed answer cannot win** because it is short.

## Paired eligibility

The primary comparison is `if` versus `concise`. A pair is eligible only when both terminal
records belong to the same run, manifest, matched case/repetition, and both pass the selected
hard or semantic gate. Failed or missing arms remove that pair from the brevity calculation; they
remain visible in success and error counts.

The reported delta is `concise - if`. A positive token or character delta means the eligible
`if` output is shorter. `baseline` and `caveman` provide context, not an easier replacement for
the primary hypothesis.

## Metrics and accounting limitations

Reports keep separate, non-composite values for:

- hard-pass counts and rates;
- semantic pass counts, rates, and judgment coverage when judgments exist;
- provider errors, retries, exact-value violations, and format violations;
- median output characters and provider-reported output tokens when available;
- eligible paired token and character deltas;
- input, output, total, and cached-input tokens in raw records when the provider exposes them;
- latency and request metadata in raw attempts;
- price estimates only under the conditions below.

Token counts depend on the provider and model tokenizer. Character counts are not tokens. Cache
fields have provider-specific meanings, and cross-provider cache or cost totals must be shown
separately.

Cost requires an explicit dated price snapshot in the manifest: effective date, source URL,
currency, normal input rate, optional cached-input rate, and output rate. The calculation prices
uncached input, cached input, and output separately. If successful records lack usage or cache
accounting, the affected estimate is `n/a`. It is an estimate, not an invoice.

## Confidence intervals for public runs

Public repeated runs must predeclare the confidence interval level, estimator, resampling or
analytic method, sampling unit, and random seed. For the paired brevity hypothesis, resampling
must preserve matched arms and must not treat translations or repeated generations as unrelated
observations. Pass-rate intervals must disclose their binomial method. Point estimates without
their denominators and intervals are not publication-ready.

The walking-skeleton CLI does not calculate confidence intervals. Until an audited interval
implementation exists, its generated report is a reproducibility check rather than a public
efficiency result.

## Published artifacts

A public run publishes enough evidence to reproduce and audit it:

- `manifest.json`, including provider, exact requested model, settings, retry policy, arm-order
  seed, repetitions, and any dated price snapshot;
- append-only `raw.jsonl` and `run.log`, including failures, retries, and any provider-returned
  model identifier;
- `scored.jsonl`, `summary.json`, and `report.md`;
- the exact case files, repository revision, runner/schema version, arm hashes, and Caveman
  provenance;
- judge records and protocol metadata when semantic scoring is used;
- environment and known limitations, without credentials.

Secrets never belong in a manifest or committed artifact. Published result directories are
immutable evidence; a correction creates a new directory and explains the superseded run.

## Interpreting outcomes

The hypothesis may be supported, rejected, negative, or inconclusive. Low success, sparse paired
eligibility, incomplete accounting, wide intervals, provider instability, or disagreement with a
human audit can all prevent a conclusion. Reproducibility and truthful disclosure are release
criteria; a favorable result is not.

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
