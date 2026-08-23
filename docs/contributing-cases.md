# Contributing benchmark cases

Cases test whether brevity preserves the answer the user needs. They are public measurement
inputs, not prompts designed to advertise one arm. Read the
[methodology](../benchmarks/methodology.md) before proposing a case.

## File contracts

All files use strict YAML with `schema_version: "1"`. Duplicate mapping keys, unknown fields,
blank prompts, duplicate case IDs, invalid enum values, and impossible sentence bounds are
rejected. Each `scenario_id` must have exactly one `en` and one `ru` record, even when multiple
files are loaded together.

### Response file

A response file has top-level fields `schema_version`, `kind: response`, and `cases`. Every case
contains:

| Field | Contract |
|---|---|
| `id` | Lowercase letters, digits, and hyphens; ends in `-en` or `-ru` |
| `scenario_id` | Shared by the English/Russian pair; lowercase letters, digits, and hyphens |
| `locale` | Exactly `en` or `ru` |
| `category` | `direct`, `coding`, `preservation`, `structured-output`, `uncertainty`, `safety`, `user-message`, or `summarization` |
| `prompt` | Nonblank user prompt |
| `hard_constraints` | Deterministic constraints described below |
| `semantic_rubric` | Facts and warning whose meaning must survive |

`hard_constraints` supports `required_literals`, `forbidden_literals`, `required_json_keys`,
`required_yaml_keys`, `min_sentences`, and `max_sentences`. Collections default to empty; sentence
bounds default to `null`, must be positive when present, and `min_sentences` cannot exceed
`max_sentences`. JSON and YAML key constraints cannot be combined, and their declared keys must be
unique. A nonempty JSON or YAML key declaration requires the entire output to parse as one
top-level mapping whose key set exactly equals the declaration; extra or missing keys, prose,
fences, lists, and scalars fail the hard gate. YAML parsing also rejects duplicate and merge keys.

`semantic_rubric` supports `required_facts` and nullable `material_warning`. These fields describe
meaning for a blind semantic judge; rubric sentences are not treated as exact literal matches.

This complete, valid example contains one pair and every response-schema option:

```yaml
schema_version: "1"
kind: response
cases:
  - id: retry-safety-en
    scenario_id: retry-safety
    locale: en
    category: coding
    prompt: Explain the risk of retrying a POST request without idempotency protection.
    hard_constraints:
      required_literals:
        - POST
      forbidden_literals: []
      required_json_keys: []
      required_yaml_keys: []
      min_sentences: 1
      max_sentences: 2
    semantic_rubric:
      required_facts:
        - A retry can duplicate an operation when the first attempt already took effect.
      material_warning: POST is not inherently idempotent.
  - id: retry-safety-ru
    scenario_id: retry-safety
    locale: ru
    category: coding
    prompt: Объясни риск повтора POST-запроса без защиты идемпотентности.
    hard_constraints:
      required_literals:
        - POST
      forbidden_literals: []
      required_json_keys: []
      required_yaml_keys: []
      min_sentences: 1
      max_sentences: 2
    semantic_rubric:
      required_facts:
        - Повтор может продублировать операцию, если первая попытка уже сработала.
      material_warning: POST сам по себе не является идемпотентным.
```

### Activation file

An activation file has top-level fields `schema_version`, `kind: activation`, and `cases`. Every
case contains `id`, `scenario_id`, `locale`, nonblank `prompt`, Boolean `expected_activation`, and
nonblank maintainer `rationale`. The rationale is never sent to the routing model.

```yaml
schema_version: "1"
kind: activation
cases:
  - id: activation-concise-example-en
    scenario_id: activation-concise-example
    locale: en
    prompt: "Answer briefly and without filler: what does idempotent mean?"
    expected_activation: true
    rationale: The user explicitly requests a brief, filler-free answer.
  - id: activation-concise-example-ru
    scenario_id: activation-concise-example
    locale: ru
    prompt: "Ответь кратко и без воды: что значит идемпотентность?"
    expected_activation: true
    rationale: Пользователь явно просит краткий ответ без лишнего текста.
```

## Evidence and neutrality

Semantic rubrics must be evidence-backed. Cite a primary or authoritative source in the pull
request when a required fact is technical, historical, medical, legal, financial, or otherwise
contestable. Keep the source out of the user prompt unless source use is itself the task.

The runner hashes the complete validated response-case definition. Changing an ID, locale,
category, prompt, hard constraint, or semantic rubric intentionally creates new scoring
provenance; old raw attempts cannot be rescored against the edited definition.

A good rubric states the smallest observable facts needed for a correct answer. It does not copy
one preferred prose answer, encode taste as correctness, reward phrases taken from the `if` skill,
or penalize natural variation. Cases designed only to favor `if` are not accepted. A useful case
can expose a failure in any arm, including `if`.

Hard constraints must follow the user's actual request. Use `required_literals` only for exact
values that must survive, not for semantic paraphrases. Use `forbidden_literals` for explicit
prohibitions, `required_json_keys` or `required_yaml_keys` only when one complete mapping with
exactly that top-level key set is requested, and sentence limits only when the prompt makes that
limit legitimate.

English and Russian records should represent the same task and difficulty, not word-for-word
translation artifacts. A material warning present in one locale belongs in the other.

## Contribution checklist

1. Add or edit the paired records with unique IDs and a shared `scenario_id`.
2. Explain the category, evidence, hard constraints, and why the case is neutral among arms.
3. Validate the file with `uv run laconian validate PATH`.
4. Add a regression test for any new schema or scoring boundary.
5. Run the four local quality commands in [CONTRIBUTING.md](../CONTRIBUTING.md).
6. Do not make a benchmark claim from the new case without a fully disclosed run and raw
   artifacts.

Cases are licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
