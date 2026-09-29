# Cato support engineer — current state

The main folder and the worktree contain the same commit. The knowledge-base ingestion code from `docs/superpowers/plans/2026-09-28-kb-ingestion.md` has not been written yet. There is no `kbindex` package, no `pyproject.toml`, no tests, and no Docker Compose file.

| Checkout | Path | Branch | Commit |
|---|---|---|---|
| Main folder | this directory | `master` | `a554d56` — Ignore local git worktrees |
| Worktree | `.worktrees/kb-ingestion` | `feat/kb-ingestion` | same commit |

`master` is one commit ahead of `origin/master` because of that `.gitignore` commit. `docs/kb-ingestion-decisions.md` exists only in the main folder and is not committed. The worktree also has a gitignored scratch directory, `.superpowers/sdd/`, with the execution ledger. That directory is not part of the project.

## Bring the branch into the main folder

Git will not let this folder check out `feat/kb-ingestion` while the worktree still has that branch. Remove the worktree first, then check the branch out here:

```bash
cd "/home/yaara/Documents/Assignments/cato networks"
git worktree remove ".worktrees/kb-ingestion"
git checkout feat/kb-ingestion
```

`git worktree remove` deletes `.worktrees/kb-ingestion`, including `.superpowers/sdd/`. Copy that directory out first if you want to keep the ledger.

After later commits exist only on `feat/kb-ingestion`, merge them into the main folder without deleting the worktree:

```bash
cd "/home/yaara/Documents/Assignments/cato networks"
git merge feat/kb-ingestion
```

## What you can run today

Confirm both checkouts match:

```bash
git worktree list
git log --oneline -3
git -C ".worktrees/kb-ingestion" log --oneline -3
```

Read the design and the task list:

- `docs/superpowers/specs/2026-09-28-kb-ingestion-design.md` — behavior
- `docs/superpowers/plans/2026-09-28-kb-ingestion.md` — implementation tasks
- `docs/kb-ingestion-decisions.md` — why those choices were made (main folder only, untracked)
- `data/README.md` — the assignment data bundle

## Tests

There is nothing to test yet. `pytest` is not a project command until Task 1 adds `pyproject.toml`. After that task, from the checkout that contains the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

Database tests in later tasks skip unless Postgres from Compose is up and `DATABASE_URL=postgresql://kb:kb@localhost:5432/kb` is set. That Compose file does not exist yet.
