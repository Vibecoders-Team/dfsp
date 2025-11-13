# CI/CD Documentation

This document describes the continuous integration and deployment setup for DFSP.

## GitHub Actions Workflows

### 1. CI Pipeline (`ci.yml`)

Runs on every push to `main`/`develop` branches and on all pull requests.

**Jobs:**

#### Backend (Python 3.11)
- **Format check**: `ruff format --check`
- **Linting**: `ruff check`
- **Type checking**: `pyright`
- **Tests**: `pytest` (unit tests only, e2e tests skipped)

**Requirements:**
- Python 3.11
- uv package manager
- Dependencies from `backend/pyproject.toml`

#### Frontend (Node.js 22)
- **Type checking**: TypeScript compiler (`tsc --noEmit`)
- **Linting**: ESLint
- **Tests**: Vitest (with jsdom)
- **Build**: Production build validation

**Requirements:**
- Node.js 22
- pnpm 9
- Dependencies from `frontend/package.json`

#### Contracts (Solidity)
- **Compilation**: Hardhat compile
- **Tests**: Hardhat test suite
- **ABI Export**: Validates ABI generation

**Requirements:**
- Node.js 22
- npm
- Hardhat with OpenZeppelin contracts

**Success Criteria:**
All three jobs must pass for CI to succeed. The final `ci-success` job aggregates results.

---

### 2. Commit Message Linting (`commitlint.yml`)

Runs on pull requests to validate commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).

**Format:**
```
type(scope): description

[optional body]

[optional footer]
```

**Allowed types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Test additions or changes
- `build`: Build system changes
- `ci`: CI/CD changes
- `chore`: Maintenance tasks
- `revert`: Revert previous commit

**Examples:**
```bash
feat(api): add rate limiting for POST /orders
fix(contracts): correct role check in withdraw()
docs: clarify local setup with uv
ci: run solidity tests on PR to main
refactor(web): extract useAuth() hook
```

See `meta/commit-message.md` for full guidelines.

---

## Local Pre-commit Hooks

The project includes Git hooks in `.githooks/`:

### `pre-commit`
Runs Python checks before commit:
- `ruff format --check`
- `ruff check`
- `pyright`

**Enable hooks:**
```bash
make hooks
```

**Behavior:**
- **dev branches**: Warnings only (soft fail)
- **Other branches**: Strict enforcement

### `commit-msg`
Validates commit message format using `commit-msg.py`.

---

## Running Checks Locally

### Backend
```bash
cd backend
make check  # runs fmt-check, lint, typecheck, test
```

Or individually:
```bash
make fmt-check  # format check
make lint       # ruff linting
make typecheck  # pyright
make test       # pytest
```

### Frontend
```bash
cd frontend
pnpm run typecheck  # TypeScript
pnpm run lint       # ESLint
pnpm run test:run   # Vitest
pnpm run build      # Production build
```

### Contracts
```bash
cd contracts
npm run build  # Compile contracts
npm test       # Run tests
```

---

## Caching Strategy

### Backend
- uv manages virtual environment and dependencies
- No explicit caching needed (uv is fast)

### Frontend
- pnpm store directory cached by commit hash
- Speeds up dependency installation significantly

### Contracts
- npm cache for node_modules
- Hardhat cache for compiled contracts

---

## Troubleshooting

### CI fails but local checks pass

**Python/Backend:**
1. Ensure you're using Python 3.11
2. Run `uv sync --all-extras` to update dependencies
3. Check `.venv` is activated

**TypeScript/Frontend:**
1. Delete `node_modules` and `pnpm-lock.yaml`
2. Run `pnpm install`
3. Ensure Node.js 22 is used

**Contracts:**
1. Clear Hardhat cache: `npm run clean`
2. Reinstall: `rm -rf node_modules && npm install`

### Commit message validation fails

Check your commit message follows the format:
```
type(scope): short description
```

Use `git commit --amend` to fix the last commit message.

### Pre-commit hooks not working

Enable hooks:
```bash
make hooks
```

Verify hook is executable:
```bash
chmod +x .githooks/pre-commit
```

---

## CI Performance

Typical run times (approximate):
- **Backend**: 2-3 minutes
- **Frontend**: 3-4 minutes (including build)
- **Contracts**: 2-3 minutes
- **Total**: ~5-7 minutes (jobs run in parallel)

---

## Future Improvements

Potential enhancements:
- [ ] E2E tests with Docker Compose in CI
- [ ] Automated deployment on tag push
- [ ] Security scanning (dependabot, CodeQL)
- [ ] Code coverage reports
- [ ] Performance benchmarks
- [ ] Automated changelog generation
- [ ] Docker image builds and registry push
- [ ] Staging environment deployment

---

## Contact

For CI/CD issues, check:
1. GitHub Actions logs
2. `meta/` documentation
3. Project maintainers

**Related docs:**
- `meta/commit-message.md` - Commit message guidelines
- `meta/code-style.md` - Code style guidelines
- `meta/branching.md` - Branching strategy

