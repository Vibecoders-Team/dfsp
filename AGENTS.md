# Repository Guidelines

## Project Structure & Module Organization
- Root has split stacks: `backend/` (FastAPI service in `backend/app`, migrations in `backend/migrations`, tests in `backend/tests`), `frontend/` (Vite + React/TS in `frontend/src`, assets in `public/`, unit tests in `src/lib/__tests__`), and `contracts/` for chain code. Deployment assets live in `deploy/` with Docker Compose files and scripts; `docker/` and `scripts/` hold helper images and utilities.
- Keep feature-specific modules co-located (API routers, services, and schemas under `app/`; React routes, hooks, and components grouped under `src/`). Shared types/utilities belong in existing `lib` or `utils` folders to avoid duplication.

## Build, Test, and Development Commands
- Backend local loop: `cd backend && uv sync --group dev` to install; `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` to serve; `make -C backend check` runs format check + lint + typecheck + tests.
- Frontend: `cd frontend && pnpm install` (pnpm is preferred); `pnpm dev` for Vite dev server; `pnpm build` for production bundle; `pnpm lint`, `pnpm typecheck`, and `pnpm test` (Vitest with happy-dom) for quality gates.

## Coding Style & Naming Conventions
- Backend: Ruff enforces 120-char lines, double quotes, LF endings, and Google-style docstrings; type hints are expected. Modules and files use `snake_case`; classes `PascalCase`; non-const variables `snake_case`.
- Frontend: ESLint + Prettier; favor functional React components in `PascalCase`, hooks/utilities in `camelCase` with `use*` prefix for hooks. Keep props typed with `interface`/`type` aliases and colocate component styles/assets when possible.

## Testing Guidelines
- Backend: `make -C backend test` runs pytest (async-friendly), some tests requires full stack, ignore it. Add tests under `backend/tests` with `test_*.py` naming; prefer fixture-driven integration tests for routers/services and keep side effects isolated (use test DB/containers).
- Frontend: Place unit tests under `src/**/__tests__` with `*.test.ts`/`*.test.tsx`. Use Vitest + happy-dom for components and crypto/helpers; mock network/storage boundaries and cover error paths, not just happy cases.

## Commit & Pull Request Guidelines- Commits follow Conventional Commit flavor seen in history
Don't commit by yourself.
We use **Conventional Commits** for a clear history and automatic generation of releases/CHANGELOG.

### Format

```

<type>(<scope>): <summary>

\[body]

\[footer]

```

- **type**: `feat` | `fix` | `docs` | `refactor` | `perf` | `test` | `build` | `ci` | `chore` | `revert`
- **scope** (optional): the scope of the change - `api`, `web`, `contracts`, `infra`, `docs`, `devops`, `db`, etc.
- **summary**: short and to the point (imperative mood).

### Examples

```
feat(api): add rate limiting for POST /orders
fix(contracts): correct role check in withdraw()
docs: clarify local setup with uv
ci: run solidity tests on PR to main
refactor(web): extract useAuth() hook
```

## Security & Configuration Tips
- Never commit secrets; keep `.env` files local (`deploy/.env.local` / `.env.dev` / `.env.prod` are ignored). Rotate keys stored in deploy buckets when sharing with teammates.
- Validate inputs at the boundary (FastAPI dependencies, React forms) and avoid logging sensitive payloads. Prefer passing hashes/IDs over raw file contents when instrumenting telemetry.
