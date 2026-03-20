# Copilot CLI Permissions Wishlist

Desired auto-approval configuration once the Copilot CLI adds persistent tool permissions.
Track progress at: https://github.com/github/copilot-cli/issues/307 (Phase 4, ~Q2 2026)
Related: https://github.com/github/copilot-cli/issues/1973

## Currently in config.json (working for git/gh, ignored for the rest until feature lands)

See `~/.copilot/config.json`.

## Desired: argument-level shell() patterns

These require argument-level matching which doesn't exist yet
(current `shell()` matches command name only, not arguments).

```json
{
  "allowed_tools": [
    "shell(git commit)",
    "shell(git checkout)",
    "shell(git branch)",
    "shell(git add)",
    "shell(git fetch)",
    "shell(git pull)",
    "shell(git log)",
    "shell(git diff)",
    "shell(git status)",
    "shell(git stash)",
    "shell(git merge)",
    "shell(git rebase)",
    "shell(gh pr create)",
    "shell(gh pr view)",
    "shell(gh pr list)",
    "shell(gh pr merge)",
    "shell(gh issue create)",
    "shell(gh issue comment)",
    "shell(gh issue reopen)",
    "shell(gh issue view)",
    "shell(gh issue list)",
    "shell(python .github/skills/ha-deploy/deploy.py:*)",
    "shell(python .github/skills/ha-investigate/investigate.py:*)"
  ],
  "denied_tools": [
    "shell(git push --force)",
    "shell(git push --force-with-lease)",
    "shell(git push --delete)",
    "shell(git push origin :*)",
    "shell(git reset --hard)",
    "shell(git commit --amend)",
    "shell(git branch -D)",
    "shell(git filter-branch)",
    "shell(gh issue close)",
    "shell(ssh:*)"
  ]
}
```

## Why not `shell(python)` broadly

`shell(python)` auto-approves ANY python script — too broad.
We only want to approve the specific skill scripts. Once argument-level
matching lands, the `python .github/skills/...` patterns above are the
right scope.

## Why `shell(ssh:*)` is denied

SSH commands vary from safe reads to destructive restarts — can't be
distinguished at command-name level. Use `ha-investigate` and `ha-deploy`
skills instead; approve those specific script invocations.

## Current workaround

The `git:*` and `gh` patterns in `config.json` already work (subcommand-level
matching is supported). Python/SSH skills require manual approval per session
until argument-level matching is implemented.
