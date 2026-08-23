# Security policy

## Private reporting

Report a suspected vulnerability through
[GitHub private vulnerability reporting](https://github.com/agent-axiom/laconian/security/advisories/new).
Do not open a public issue, discussion, or pull request for an undisclosed vulnerability. Do not
include real credentials in a report or reproduction; use a clearly fake marker instead.

Include the affected revision, minimal reproduction, impact, and any safe mitigation you have
identified. Maintainers will use the private advisory to coordinate validation, a fix, credit,
and disclosure. This pre-release project does not yet promise a fixed response-time SLA.

## In scope

Security reports are especially useful for:

- secret exposure through provider errors, request identifiers, logs, raw records, manifests, or
  reports;
- unsafe execution of model output, benchmark prompts, fixtures, or judge evidence;
- benchmark artifact path traversal, target escape, symlink abuse, or unintended overwrite;
- retry or resume behavior that mixes runs, bypasses manifest integrity, or leaks data;
- parsing behavior that lets untrusted YAML or JSON change configuration or execute code;
- dependency or packaging issues that affect the installed `laconian` command or portable skill.

## Security invariants

API credentials come from the configured environment or a provider-native credential store, not
from manifests. Model prompts and outputs are untrusted data. Generated text must never be run as
code or a shell command. Artifact writers must remain constrained to explicit targets and refuse
existing outputs unless a separately specified, integrity-checked resume operation applies.

## Out of scope

Ordinary disagreement about answer quality, missing benchmark cases, unsupported model access,
provider availability, and performance claims without a security impact belong in normal issue
tracking. Do not probe third-party providers, agent hosts, or accounts you do not own.

Only the current default branch is supported while the project remains pre-release. Historical
commits may receive a forward fix rather than a patch release.
