# Alpha Launch Readiness Design

## Decision

Prepare Laconian for an honest `v0.1.0-alpha.1` launch as an installable skill/plugin and
open benchmark under development. This release may describe the workflow, source, and
experimental status. It must not claim measured token savings, superior quality, or completed
benchmark evidence.

The repository root will also be the plugin root. This keeps `skills/if/SKILL.md` as the only
canonical copy of the workflow while adding the manifest and repo marketplace metadata needed
for installation.

## Goals

- Restore a green, truthful CI matrix on CPython 3.11 and 3.14.
- Preserve the standalone one-file skill and its existing activation/fidelity contract.
- Package that same file as a versioned Codex/ChatGPT plugin without duplicating it.
- Document exact, pinned installation, invocation, verification, and uninstall flows.
- Produce an immutable alpha release archive with an allowlisted file inventory and checksum.
- Prepare accurate repository metadata, a social card, and English/Russian launch copy.
- Make successful required checks a merge prerequisite after the launch PR lands.

## Non-goals

- Completing the benchmark evidence work tracked in generation-capsule Tasks 15-19.
- Publishing performance or token-saving claims.
- Calling the alpha a final `v0.1.0` benchmark release.
- Publishing the Python package to PyPI.
- Claiming acceptance into the universal Plugins Directory. The alpha will be installable from
  the GitHub repo marketplace and structured for a later public-directory submission.
- Posting to a social account without a separately identified account and explicit send action.

## Approaches considered

### 1. Standalone GitHub skill only

This is the smallest change, but it leaves users with a manual file copy and no stable plugin
identity or install surface. It does not satisfy the launch goal.

### 2. Root plugin plus repo marketplace — selected

Add `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json` at the repository root.
The plugin points at the existing `./skills/` directory, and the marketplace points at `./`.
This avoids a mirrored `plugins/laconian/skills/if/SKILL.md` and eliminates copy drift.

### 3. Universal directory submission now

This requires publisher identity, production support/privacy/terms surfaces, real host test
cases, review, and a separate publication step. Those requirements are larger than an honest
alpha and would turn launch preparation into an external approval project.

## Components

### CI and runtime compatibility

The workflow will bind `uv` explicitly to each matrix interpreter and verify the running major
and minor version before quality checks. `UV_PYTHON_DOWNLOADS=never` will prevent a silent
fallback to `.python-version`. The macOS capsule job will use the same binding.

The existing failures have three independent causes and will be handled separately:

1. Matrix jobs install Python 3.14 with `setup-python`, but `uv sync` currently creates a 3.11
   environment because `.python-version` pins 3.11.
2. Import-policy tests hard-code `_sha3` and `_hashlib` as DESTSHARED extensions, while some
   CPython distributions compile them as built-ins.
3. The OpenAI lazy-import integration test has a 30-second child timeout even though the guarded
   import and full revalidation can legitimately take more than 30 seconds on hosted runners.

Actual Python 3.14 also aliases `collections.abc` to the frozen `_collections_abc` module object;
the import-policy builder must recognize that identity-preserving alias without weakening origin
validation for unrelated modules.

Each behavior change will follow red-green TDD: a focused failing test, the smallest fix, then the
full platform-appropriate suite.

### Plugin and marketplace

The repository will add:

```text
.codex-plugin/plugin.json
.agents/plugins/marketplace.json
skills/if/SKILL.md
```

The manifest identity is `laconian`, version `0.1.0-alpha.1`, Apache-2.0 licensed, with the
existing `./skills/` directory as its skill source. It contains honest UI copy and starter prompts
but no MCP, app, hook, asset, privacy, or terms fields without matching components.

The marketplace contains one `AVAILABLE` Productivity entry named `laconian`, with authentication
timing `ON_INSTALL` and local source path `./`. A contract test will validate the exact relationship
between marketplace name, plugin name, repository layout, version, and canonical skill path.

The standalone skill remains byte-for-byte unchanged and valid as a one-file portable artifact.

### Installation contract

The README will lead with two supported paths:

1. Version-pinned repo plugin installation from `agent-axiom/laconian` followed by installation of
   `laconian@laconian` and invocation as `$laconian:if`.
2. Version-pinned standalone download to `~/.agents/skills/if/SKILL.md` and invocation as `$if`.

Both paths will include discovery verification, the required new-task/restart boundary, and
reversible uninstall commands. Main-branch URLs will not be presented as immutable release
instructions.

### Release artifact

The tag `v0.1.0-alpha.1` will produce:

- `laconian-plugin-v0.1.0-alpha.1.zip`
- `laconian-plugin-v0.1.0-alpha.1.zip.sha256`

The zip will be assembled from an explicit allowlist and contain only:

```text
.agents/plugins/marketplace.json
.codex-plugin/plugin.json
skills/if/SKILL.md
README.md
CHANGELOG.md
LICENSE
NOTICE
LICENSES/CC-BY-4.0.txt
```

Tests will inspect the archive inventory, version, license files, and skill byte identity. The
Python evaluator version will move from `0.1.0.dev0` to the PEP 440 equivalent `0.1.0a1`, and the
changelog will identify the release as alpha with no public benchmark result.

### Social launch package

The repository will include a 1200x630 social card and a source file under `assets/social/`. The
card will use the exact copy:

```text
if
The shortest complete answer.
Experimental alpha
```

The visual language will be restrained: dark ink, warm stone, one muted Spartan-red accent,
large negative space, and no charts, scores, partner logos, or implied endorsements. Text must be
rendered exactly and remain legible in a small link preview.

`docs/social/alpha-launch.md` will provide concise English and Russian variants for X/LinkedIn
and Telegram, a before/after demo format, alt text, and prohibited claims. The demo will be labeled
illustrative rather than benchmark evidence.

After merge, GitHub description and topics will be updated to match the alpha positioning. The
social card will be uploaded as the repository social preview if the GitHub UI/API permits it.

## Verification gates

The launch PR cannot merge until all of the following are fresh and green:

- skill validator;
- plugin validator;
- focused skill, plugin, release, and CI contract tests;
- Ruff formatting and lint;
- mypy;
- full pytest suite on the local supported interpreter;
- GitHub Actions quality jobs on actual Python 3.11 and 3.14;
- macOS capsule job on actual Python 3.14;
- clean-wheel install and CLI smoke test;
- local repo-marketplace list/install/discovery smoke test where the installed Codex CLI supports
  those commands.

After merge, required status checks will be configured for `main`. Only then will the alpha tag
and GitHub Release be created. The release checksum and release asset inventory will be verified
after upload.

## Failure handling

- If real Python 3.14 exposes additional incompatibilities, the alpha release pauses; the matrix
  will not be relabeled or silently downgraded.
- If repo marketplace installation cannot be reproduced with the installed Codex surface, the
  README will not claim that path; standalone installation remains available.
- If generated social-card text is inaccurate, the bitmap is not committed until corrected or
  replaced by a deterministic typographic render.
- If GitHub rejects branch-protection or social-preview mutations because of plan or permission
  limits, the code release can proceed only with that limitation disclosed.
