## What's done
-

## Why
-

## Cheklist
- [ ] PR headline complies with Conventional Commits:
      `<type>(<scope>): <summary>`
      where `type ∈ { feat | fix | docs | refactor | perf | test | build | ci | chore | revert }`
- [ ] A block for BREAKING CHANGES has been added to the body/footer:
      ```
      BREAKING CHANGE: <what has changed and how to migrate>
      ```
- [ ] Links added (if relevant):
      `Refs: PROJ-123` / `Closes: #456`
- [ ] Tests/lint pass

### Examples
- `feat(api): add rate limiting for POST /orders`
- `fix(contracts): correct role check in withdraw()`
- `docs: clarify local setup with uv`
- `ci: run solidity tests on PR to main`
- `refactor(web): extract useAuth() hook`
- `feat(api)!: switch auth to JWT`

> SemVer:
> - `feat` → **minor**
> - `fix` → **patch**
> - `BREAKING CHANGE` (или `type!`) → **major**
> - остальные — не меняют версию
