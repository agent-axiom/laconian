[Website](https://agent-axiom.github.io/laconian/) · [English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

# Laconian

Laconian asks for the shortest complete answer—not the shortest answer.

## Status

Laconian is a public philosophy project and an open benchmark under active development. The
repository currently contains a walking skeleton: one portable skill, bilingual smoke cases,
four comparison arms, an offline replay path, deterministic scoring, optional blind semantic
judgments, and a mocked contract for one live provider adapter.

No public benchmark result is available yet. The smoke fixtures validate the architecture; they
do not show that `if` wins, saves a particular amount, or performs better than another arm.

## Why “if”?

Plutarch, writing centuries later, preserves an anecdote about Philip II in *On Talkativeness*
17 (Moralia 511A). Philip writes a threat concerning entry into Laconia; the Laconians answer
in writing with one Doric word: `αἴκα`—“if.” The letter itself does not survive. What survives is
Plutarch's later literary account, not a contemporary document.

The story is an image for the project, not proof of its benchmark hypothesis. It is also not a
story about an unfulfilled entry: Polybius 9.33 has a speaker acknowledge that Philip entered
Laconia with an army.

## What the skill does

[`skills/if/SKILL.md`](skills/if/SKILL.md) asks an agent to determine the complete answer first,
then remove only what can be removed without weakening correctness, safety, requirements,
material facts, uncertainty, practical sufficiency, clarity, tone, or natural language.

It removes greetings, restatement, unrequested process narration, repetition, and decoration
before it removes substance. It preserves requested detail and exact code, commands, errors,
numbers, versions, URLs, identifiers, quotations, and machine-readable structures when their
exact form matters.

The skill is one Markdown-only file. It has no scripts, dependencies, permissions, references,
assets, network calls, or platform-specific tool instructions.

## What the skill does not do

`if` does not turn prose into primitive speech, replace evidence with confidence, hide material
caveats, shorten tool calls, minify code, compress input context, or execute an action. It does
not override a request for a detailed tutorial, fixed structure, evidence, examples, or a
required length. It makes no promise that every agent or model will respond identically.

## Install and uninstall

Copy the one skill file into the `if` directory of an agent host that supports Markdown skills:

```bash
mkdir -p "<agent-skills-directory>/if"
cp skills/if/SKILL.md "<agent-skills-directory>/if/SKILL.md"
```

Remove that copied file to uninstall it:

```bash
rm "<agent-skills-directory>/if/SKILL.md"
rmdir "<agent-skills-directory>/if"
```

The placeholder is host-specific. The walking skeleton does not yet claim installation coverage
across named agent hosts.

## Four-arm benchmark

Every response case is compared under the same model, user prompt, generation settings, tool
availability, and instruction location. Only the comparison instruction changes:

| Arm | Added instruction |
|---|---|
| `baseline` | None |
| `concise` | Exactly `Answer concisely.` |
| `caveman` | A byte-pinned offline snapshot of the full Caveman skill |
| `if` | The exact bytes of this repository's `skills/if/SKILL.md` |

The primary hypothesis is `if` versus `concise`. The `baseline` and `caveman` arms provide
context; they are not easier substitutes for the primary comparison. Activation and response
quality are evaluated separately.

## Quality gate and reported metrics

Deterministic constraints are checked before brevity. An optional semantic judgment can then
assess required facts and material warnings without receiving the arm name. A failed answer
cannot win merely by being short; paired deltas include only matched case/repetition pairs where
both responses pass the selected quality gate.

Reports keep separate metrics for hard and semantic success, exact-value and format violations,
provider errors, retries, output tokens or characters, latency data in raw artifacts, and the
paired `if`-versus-`concise` delta. There is no composite score. Cost is estimated only from an
explicit dated price snapshot and sufficiently complete provider token and cache accounting.
See the full [benchmark methodology](benchmarks/methodology.md).

## Quickstart

The offline replay path needs no network access or provider credentials:

```bash
uv sync --all-extras
uv run laconian validate evals/cases/response-smoke.yaml
uv run laconian validate evals/cases/activation-smoke.yaml
uv run laconian validate evals/manifests/replay-smoke.yaml
uv run laconian run evals/manifests/replay-smoke.yaml --results-root benchmarks/results
```

The last command prints its unique run directory. Copy that path into `RUN_DIR`, then score and
render the report:

```bash
RUN_DIR="benchmarks/results/PASTE_THE_PRINTED_DIRECTORY_NAME"
uv run laconian score "$RUN_DIR/raw.jsonl" --cases evals/cases/response-smoke.yaml --output "$RUN_DIR/scored"
uv run laconian report "$RUN_DIR/scored/scored.jsonl" --output "$RUN_DIR/report.md"
```

These replay outputs are local verification artifacts, not published benchmark evidence.

### Optional live run

```bash
export OPENAI_API_KEY="your key"
uv sync --extra openai
uv run laconian run evals/manifests/openai-example.yaml --results-root benchmarks/results
```

This command incurs provider cost. Model availability can vary by account and date. API keys
belong only in the configured environment variable; never place them in manifests or committed
result files. A live run is not publication-ready until its model identifier, raw artifacts,
method, and limitations are reviewed.

## Repository map

| Path | Purpose |
|---|---|
| `skills/if/SKILL.md` | The entire portable skill |
| `src/laconian_eval/` | Provider-neutral runner, scoring, judging boundary, and reporting |
| `evals/cases/` | Paired English/Russian response and activation inputs |
| `evals/manifests/` | Reproducible run configuration |
| `evals/baselines/caveman/` | Pinned third-party benchmark fixture and attribution |
| `tests/fixtures/` | Synthetic replay and judge data for offline tests |
| `benchmarks/methodology.md` | Rules for a publishable comparison |
| `benchmarks/results/` | Future immutable public run artifacts |
| `docs/` | Design, philosophy, and case-contribution guidance |

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md). New cases must be evidence-backed, neutral among
arms, and paired in English and Russian. Benchmark claims require the corresponding raw
artifacts. Security-sensitive reports follow [SECURITY.md](SECURITY.md), not a public issue.

## Licensing

Licensing follows the map in [NOTICE](NOTICE):

- code, tests, workflow configuration, and `skills/if/SKILL.md`: Apache-2.0 under [LICENSE](LICENSE);
- README files, project documentation, eval cases and manifests, methodology, and published
  results: [CC BY 4.0](LICENSES/CC-BY-4.0.txt);
- the pinned Caveman snapshot: [MIT](LICENSES/CAVEMAN-MIT.txt), with upstream provenance in
  [`evals/baselines/caveman/SOURCE.md`](evals/baselines/caveman/SOURCE.md).

## Historical and linguistic sources

- [Plutarch, *On Talkativeness* 17 (*Moralia* 511A)](https://www.perseus.tufts.edu/hopper/text?doc=Perseus%3Atext%3A2008.01.0287%3Asection%3D17), for the later literary account and `αἴκα`.
- [Eva A. Mitchell, *Laconian Dialect*, University of Edinburgh](https://era.ed.ac.uk/items/385e1ac5-539c-47f6-94b7-8ab83a94a139), for the fragmentary and heterogeneous evidence for ancient Laconian.
- [Polybius, *Histories* 9.33](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Polybius/9%2A.html), for ancient testimony that Philip entered Laconia with an army.
