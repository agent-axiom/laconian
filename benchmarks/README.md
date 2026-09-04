# Laconian benchmark

The benchmark tests whether the `if` skill produces shorter answers without weakening the answer
the user needs. The current smoke data verifies the evaluation pipeline; it is not a public model
result.

## Comparison arms

Every response case uses the same model, prompt, generation settings, tools, and instruction
location. Only the comparison instruction changes:

| Arm | Added instruction |
|---|---|
| `baseline` | None |
| `concise` | Exactly `Answer concisely.` |
| `caveman` | The pinned offline Caveman skill snapshot |
| `if` | The exact bytes of [`skills/if/SKILL.md`](../skills/if/SKILL.md) |

The primary comparison is `if` versus `concise`; the other arms provide context.

## Quality before brevity

Deterministic constraints are checked before brevity. Optional blind semantic judgment can then
check required facts and material warnings. A failed answer cannot win merely by being short,
and the project reports separate metrics rather than a composite score. See the full
[methodology](methodology.md).

## Install dependencies

From the repository root, install the project dependencies:

```bash
uv sync --all-extras
```

On a fresh checkout, this initial synchronization may require network access to a package index.

## Offline replay

After dependencies are installed, the validation, replay, scoring, and reporting commands below
need no network access or provider credentials:

```bash
uv run laconian validate evals/cases/response-smoke.yaml
uv run laconian validate evals/cases/activation-smoke.yaml
uv run laconian validate evals/manifests/replay-smoke.yaml
uv run laconian run evals/manifests/replay-smoke.yaml --results-root benchmarks/results
```

The last command prints a unique run directory. Copy it into `RUN_DIR`, then score and render the
report:

```bash
RUN_DIR="benchmarks/results/PASTE_THE_PRINTED_DIRECTORY_NAME"
uv run laconian score "$RUN_DIR/raw.jsonl" --cases evals/cases/response-smoke.yaml --output "$RUN_DIR/scored"
uv run laconian report "$RUN_DIR/scored/scored.jsonl" --output "$RUN_DIR/report.md"
```

Replay outputs are local verification artifacts, not published benchmark evidence.

## Optional live run

```bash
export OPENAI_API_KEY="your key"
uv sync --extra openai
uv run laconian run evals/manifests/openai-example.yaml --results-root benchmarks/results
```

This command incurs provider cost. Model availability can vary by account and date. API keys
belong only in the configured environment variable; never place them in manifests or committed
results. A live run is not publication-ready until its model identifier, artifacts, method, and
limitations are reviewed.

## Further reading

- [Evaluation data and manifests](../evals/README.md)
- [Full publication methodology](methodology.md)
- [Contributing benchmark cases](../docs/contributing-cases.md)

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
