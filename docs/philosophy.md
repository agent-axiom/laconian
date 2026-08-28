# The shortest complete answer

Laconian treats brevity as editing under constraints, not as a style contest. The goal is the
shortest complete answer: an answer may become shorter only while it remains correct, safe,
clear, useful, natural, and faithful to the user's request.

## Priority before compression

The `if` skill preserves, in order, correctness and safety; user requirements and format;
material facts, constraints, warnings, and uncertainty; practical sufficiency; clarity and
natural language; then brevity. Brevity never overrides a higher priority.

This order matters because token count alone rewards the empty answer. A failed answer cannot
be rehabilitated by being short. A caveat that changes a decision, an exact value required for a
command, or a step the user explicitly requested is part of completeness.

## Semantic editing

The editing pass starts from the answer the user actually needs. It first removes greetings,
acknowledgements, question restatement, unrequested process narration, repeated conclusions,
obvious explanation, decorative structure, and caveats that cannot affect the decision. It then
uses concrete language and stops at the semantic limit.

The result should retain normal grammar and human tone. Laconian is not primitive speech,
telegraphese, brusqueness, or a demand to turn every response into one sentence. A detailed,
fixed-format, pedagogical, or evidence-heavy request remains detailed, formatted, pedagogical,
or evidenced; redundancy is removed within those requirements.

## Exactness is meaning

Code, commands, errors, numbers, identifiers, versions, URLs, quotations, schemas, and required
order can lose meaning when compressed. They remain exact unless the user asks to transform
them. Safety warnings and honest uncertainty remain whenever they can change an action or
interpretation.

## An inspectable hypothesis

The benchmark does not compare `if` only with an intentionally verbose agent. Its primary
comparison is the exact one-line instruction `Answer concisely.`; ordinary and pinned Caveman
arms provide context. Activation is measured separately from deliberately applied response
behavior. Quality gates precede paired brevity metrics, and raw failures remain visible.

A public experiment may support the hypothesis, produce a negative result, or remain
inconclusive. Any of those outcomes is useful if the cases, prompts, arms, errors, judgments, and
accounting are reproducible. The project succeeds first by making the claim falsifiable—not by
forcing a favorable number.

## Portability as discipline

The project keeps examples, adapters, history, and benchmark machinery outside the single
`skills/if/SKILL.md` file. The skill should save context without first occupying it with a private
framework. More files or dependencies require evidence that their benefit exceeds their context
and portability cost.

## Related fidelity method

The decision rule was informed by the `KEEP` / `REMOVE` / `FLAG` model in
[`lossless-doc-compress`](https://github.com/ML-SystemDesign/MLSystemDesign/tree/8dd0d88852fe7445e9d2627c59124f0f161040c1/skills/lossless-doc-compress),
by Valerii Babushkin and Arseny Kravchenko. Laconian adapts that model to answer editing: uncertain
content remains in the answer, no editorial log is emitted, and the project does not claim that
model editing is lossless.

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
