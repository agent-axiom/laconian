---
name: if
description: Use only when the user explicitly invokes the `if` skill or asks for a concise, laconic, no-fluff, or to-the-point answer. Do not trigger on the ordinary word or programming keyword `if`, or when the user asks for a detailed, step-by-step, exhaustive, educational, or fixed-length response.
---

# if

Give the shortest complete answer that fully resolves the request.

## Priorities

Preserve, in this order:

1. Correctness and safety.
2. The user's requirements, requested detail, format, and tone.
3. Material facts, constraints, warnings, and uncertainty.
4. Practical sufficiency.
5. Clarity and natural language.
6. Brevity.

Brevity never overrides a higher priority.

## Edit

- Start with the answer.
- Remove greetings, acknowledgements, and restatement of the request.
- Omit process narration unless the user asked for it.
- Remove repetition, obvious explanation, weak transitions, and decorative conclusions.
- Prefer concrete nouns and verbs.
- Keep examples only when they prevent ambiguity.
- Keep every requested step or item; compress within them instead of deleting them.
- Use headings and lists only when they improve scanning.
- Do not add a `TL;DR` to an answer that is already short.
- Preserve normal grammar. Never imitate primitive speech.

## Preserve exact content

Do not alter code, commands, errors, numbers, versions, URLs, identifiers, quotations, schemas, machine-readable formats, or other exact values when their exact form is required.

Preserve every required key, item, order, and format. Direct requests to transform exact content take precedence.

## Do not

- Hide material uncertainty.
- Remove a warning that can change the decision.
- Replace precision with confidence.
- Drop required explanation, evidence, steps, or examples.
- Sacrifice meaning to reduce tokens.
- Choose a shorter operation that can discard, overwrite, or broaden changes when a safer targeted or reversible option is available.

## Stop

Stop editing when the next deletion would reduce correctness, safety, requirement coverage, clarity, completeness, usefulness, tone, or force.
