#!/usr/bin/env python3
import re, sys, textwrap

if len(sys.argv) < 2:
    sys.exit(0)

msg_path = sys.argv[1]
branch = sys.argv[2] if len(sys.argv) > 2 else ""

with open(msg_path, "r", encoding="utf-8") as f:
    raw = f.read().strip("\n")

lines = raw.splitlines()
header = lines[0] if lines else ""
body = "\n".join(lines[1:]) if len(lines) > 1 else ""

allowed = r"(feat|fix|docs|refactor|perf|test|build|ci|chore|revert)"
pat = re.compile(rf"^{allowed}(?:\([^)]+\))?(?:!)?: .+", re.U)

errors = []

# 1) Заголовок по шаблону
if not pat.match(header or ""):
    errors.append(
        "Header must be: <type>(<scope>): <summary>. "
        "Allowed types: feat|fix|docs|refactor|perf|test|build|ci|chore|revert"
    )

# 2) Длина заголовка
if len(header) > 100:
    errors.append("Header max length is 100 characters")

# 3) BREAKING CHANGE при '!'
if "!" in header and not re.search(r"(?m)^BREAKING CHANGE:\s+.+", body):
    errors.append("Header contains '!' but no 'BREAKING CHANGE:' block in body/footer")

# 4) Рекомендация футера ссылок (только предупреждение)
if header.startswith(("feat", "fix")) and not re.search(r"(?mi)^(Refs:|Closes:)\s+\S+", raw):
    print("[warn] Add footer 'Refs: PROJ-123' or 'Closes: #456' if applicable.")

if errors:
    print("\n[error] Conventional Commits validation failed:")
    for e in errors:
        print(" -", e)
    print("\nExamples:")
    print(" - feat(api): add rate limiting for POST /orders")
    print(" - feat(api)!: switch auth to JWT\n")
    print(textwrap.dedent("""\
        Example body for breaking change:

        BREAKING CHANGE: OAuth tokens are no longer supported; migrate to JWT by 2025-10-01.
    """))
    sys.exit(1)

sys.exit(0)
