# Repository workflow

Work directly on `main`. Do not create feature branches or worktrees unless the user explicitly changes this instruction. Push updates to `origin/main`.

The VPS checkout is `/opt/docker/apps/seriesradar` and must track `origin/main`. Deploy using the existing `/opt/docker/compose.yaml`, project `aio`, profile and service `seriesradar`. Preserve the VPS environment, compose overrides and database. A GitHub push alone does not update the running container.

Keep verification focused and avoid unnecessary usage, as requested by the user.
