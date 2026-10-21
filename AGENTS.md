# Repository workflow

Work directly on `main`. Do not create feature branches or worktrees unless the user explicitly changes this instruction. Push updates to `origin/main`.

The VPS checkout is `/opt/docker/apps/seriesradar` and must track `origin/main`. Deploy using the existing `/opt/docker/compose.yaml`, project `aio`, profile and service `seriesradar`. Preserve the VPS environment, compose overrides and database. A GitHub push alone does not update the running container.

Keep verification focused and avoid unnecessary usage, as requested by the user.

Every update on main must include the next version in VERSION and a matching entry in CHANGELOG.md. Start at 0.1.0; increment patch by one for fixes, or advance one minor/major version and reset the lower parts to zero. Never reuse an existing version for a different commit. GitHub Actions runs the checks and publishes the release; do not publish releases manually. Use short, factual Dutch release notes describing the changes, without stock promotional language or generated summaries. Preserve the actual Git authorship.

Research uses the user's own chat through copy and paste. Do not trigger paid OpenAI API research or require an API key unless the user explicitly changes this instruction. Keep the manual chat workflow prominent.
