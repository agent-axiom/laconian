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

## Install and uninstall

The recommended route is the pinned repository plugin:

```bash
codex plugin marketplace add agent-axiom/laconian --ref v0.1.0-alpha.1 --json
codex plugin add laconian@laconian --json
```

Invoke the installed skill as `$laconian:if`. Start a new task or restart Codex if it does not
appear immediately. Verify discovery with:

```bash
codex plugin list --marketplace laconian --json
```

Plugin uninstall:

```bash
codex plugin remove laconian@laconian --json
codex plugin marketplace remove laconian --json
```

For a standalone, pinned one-file installation:

```bash
(
  set -eu
  skill_dir="$HOME/.agents/skills/if"
  skill_target="$skill_dir/SKILL.md"
  skill_expected_sha256="5c549c7c492c66a6b3ac5560499353b71615ffc6b93c4b1811f741a8f3d54006"
  test ! -L "$skill_dir"
  mkdir -p "$skill_dir"
  test ! -L "$skill_dir"
  test ! -e "$skill_target"
  test ! -L "$skill_target"
  skill_tmp="$(mktemp "$skill_dir/.SKILL.md.XXXXXX")"
  trap 'rm -f "$skill_tmp"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/agent-axiom/laconian/v0.1.0-alpha.1/skills/if/SKILL.md" -o "$skill_tmp"
  if command -v sha256sum >/dev/null 2>&1; then
    skill_actual_sha256="$(sha256sum "$skill_tmp")"
  else
    skill_actual_sha256="$(shasum -a 256 "$skill_tmp")"
  fi
  skill_actual_sha256="${skill_actual_sha256%% *}"
  test "$skill_actual_sha256" = "$skill_expected_sha256"
  chmod 0644 "$skill_tmp"
  ln "$skill_tmp" "$skill_target"
  if ! test "$skill_tmp" -ef "$skill_target"; then
    skill_misdirected="$skill_target/${skill_tmp##*/}"
    if test -f "$skill_misdirected" &&
      test ! -L "$skill_misdirected" &&
      test "$skill_tmp" -ef "$skill_misdirected"; then
      rm "$skill_misdirected"
    fi
    false
  fi
)
```

The installer refuses a symlink at either the skill directory or target, and refuses to overwrite
any existing target path.

Invoke the standalone skill as `$if`. Verify the copied file with:

```bash
test -s "$HOME/.agents/skills/if/SKILL.md"
```

Standalone uninstall accepts only the unmodified regular file. It refuses a symlink at either the
skill directory or target, and refuses modified or replaced files; those cases require manual
inspection. It removes the directory only when empty:

```bash
(
  set -eu
  skill_dir="$HOME/.agents/skills/if"
  skill_target="$skill_dir/SKILL.md"
  skill_expected_sha256="5c549c7c492c66a6b3ac5560499353b71615ffc6b93c4b1811f741a8f3d54006"
  test ! -L "$skill_dir"
  test -d "$skill_dir"
  test -f "$skill_target"
  test ! -L "$skill_target"
  if command -v sha256sum >/dev/null 2>&1; then
    skill_actual_sha256="$(sha256sum "$skill_target")"
  else
    skill_actual_sha256="$(shasum -a 256 "$skill_target")"
  fi
  skill_actual_sha256="${skill_actual_sha256%% *}"
  test "$skill_actual_sha256" = "$skill_expected_sha256"
  rm "$skill_target"
  rmdir "$skill_dir" 2>/dev/null || true
)
```

## Portability boundary

The skill artifact is one Markdown-only file. It has no scripts, dependencies, permissions,
references, assets, network calls, or platform-specific tool instructions. Benchmark code,
cases, examples, and historical notes remain outside the installable artifact.

See the [project philosophy](philosophy.md) for the editing principles behind the skill.

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
