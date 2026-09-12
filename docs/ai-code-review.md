# AI code review pilot

Use CodeRabbit for automatic pull request reviews and Codex on demand for complex
changes. Compare Sourcery on the same small sample before adopting another automatic
reviewer. This is a workflow experiment, not a published Laconian benchmark result.

## Repository configuration

- .coderabbit.yaml selects the chill profile, reviews non-draft PRs targeting the default
  branch, and reviews subsequent pushes incrementally.
- Summaries stay in the collapsed walkthrough. Poems, fortunes, unrelated PR/issue
  suggestions, and extra summary sections are disabled.
- CodeRabbit's Ruff, Markdown style, and grammar integrations are disabled to reduce
  duplicate formatting feedback. Existing CI remains the source of lint/type/test checks.
- AGENTS.md defines shared, project-specific code review rules. Both CodeRabbit and
  Codex can discover it automatically.
- AI findings are advisory during the pilot. Do not add an AI status to required checks
  or use a bot's approval as permission to merge.

Committing these files does not install either service or enable its account settings.

## Activate CodeRabbit

1. Sign in at [CodeRabbit](https://app.coderabbit.ai/) with GitHub.
2. Select the agent-axiom organization. Install or configure its GitHub App with
   **Only select repositories**, choosing **laconian**.
3. Review the app permissions on GitHub, then complete installation. Public repositories
   qualify for free reviews; the pilot does not require a paid plan.
4. Make this configuration available in the repository. On a representative, non-draft
   PR targeting main, confirm the bot posts a review and accepts the configuration.
5. For an existing PR that was not reviewed automatically, request a review with
   `@coderabbitai review`.

If the app is already installed, preserve its existing repository selection and add
laconian only if it is missing. Do not switch an existing installation to all repositories.

## Use Codex on demand

Connect the repository to Codex cloud and enable Code review for agent-axiom/laconian in
Codex settings. Keep automatic reviews off for this pilot so routine PRs use CodeRabbit.

On a complex PR, request `@codex review`. A focused request can name the concern, such as
`@codex review for scoring eligibility, provenance, and provider failure handling`.

Codex reviews use the account's applicable usage limits. Local reviews are an alternative
when the GitHub integration is unavailable; record them separately in the comparison.

## Compare on 10-20 pull requests

Start with CodeRabbit. For the comparative sample, install Sourcery on laconian only,
then collect both services' reviews of the same PR head commit before applying fixes.
Use Codex selectively for changes to scoring, reporting, provider contracts, security
boundaries, or methodology.

For each distinct finding, record:

| PR and head SHA | Reviewer | Finding link | Maintainer decision | Also found by | Triage minutes |
| --- | --- | --- | --- | --- | --- |

Use one of these decisions: confirmed bug, false positive, non-bug suggestion, or unresolved.
Group comments describing the same root cause; duplicates count once per reviewer.
Count a finding as unique only when all compared reviewers completed the same revision.
Record skipped, failed, and unavailable reviews separately instead of treating them as
zero findings. Include review latency and any usage cost alongside the findings log.

After 10-20 PRs, compare confirmed bugs, confirmed unique bugs, false positives, non-bug
suggestions, unresolved findings, and maintainer time. Retain a second automatic reviewer
only if its additional confirmed findings justify the extra triage effort. Keep the raw
sample and acknowledge that this small pilot cannot establish general reviewer accuracy.

## Pause or remove

Set `reviews.auto_review.enabled: false` in .coderabbit.yaml to pause automatic reviews.
Manual mentions can still trigger a review. To revoke access, remove laconian from the
GitHub App's repository selection, or uninstall the app if it serves no other repositories.
Disable Codex Code review for this repository separately in Codex settings.

## References

Configuration and service conditions checked on 2026-09-12:

- [CodeRabbit open source offer](https://www.coderabbit.ai/oss)
- [CodeRabbit GitHub setup](https://docs.coderabbit.ai/platforms/github-com)
- [CodeRabbit configuration reference](https://docs.coderabbit.ai/reference/configuration)
- [Codex GitHub reviews](https://learn.chatgpt.com/docs/third-party/github)
- [Codex pricing and limits](https://learn.chatgpt.com/docs/pricing)
- [Sourcery public repository offer](https://github.com/sourcery-ai/sourcery)
