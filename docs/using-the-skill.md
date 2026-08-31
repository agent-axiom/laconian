# Using the `if` skill

[`skills/if/SKILL.md`](../skills/if/SKILL.md) asks an agent to find the shortest complete answer,
not merely the shortest answer.

## What it does

The skill asks the agent to determine the complete answer first, then remove only what can be
removed without weakening correctness, safety, requirements, material facts, uncertainty,
practical sufficiency, clarity, tone, or natural language.

It removes greetings, restatement, unrequested process narration, repetition, and decoration
before it removes substance. It preserves requested detail and exact code, commands, errors,
numbers, versions, URLs, identifiers, quotations, and machine-readable structures when their
exact form matters.

## What it does not do

`if` does not turn prose into primitive speech, replace evidence with confidence, hide material
caveats, shorten tool calls, minify code, compress input context, or execute an action. It does
not override a request for a detailed tutorial, fixed structure, evidence, examples, or a
required length. It makes no promise that every agent or model will respond identically.

## Install

From the repository root, copy the one skill file into the `if` directory of an agent host that
supports Markdown skills:

```bash
mkdir -p "<agent-skills-directory>/if"
cp skills/if/SKILL.md "<agent-skills-directory>/if/SKILL.md"
```

The placeholder is host-specific. The project does not yet claim installation coverage across
named agent hosts.

## Uninstall

Remove the copied file and its empty directory:

```bash
rm "<agent-skills-directory>/if/SKILL.md"
rmdir "<agent-skills-directory>/if"
```

## Portability boundary

The skill is one Markdown-only file. It has no scripts, dependencies, permissions, references,
assets, network calls, or platform-specific tool instructions. Benchmark code, cases, examples,
and historical notes remain outside the installable artifact.

See the [project philosophy](philosophy.md) for the editing principles behind the skill.

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
