---
name: skill-audit-push
version: 1.0.0
description: |
  Find the 2 most useful skills installed in the last 7 days,
  audit them per code review standards (hardcoded IPs/paths, debug logs, plaintext secrets),
  fix issues, test, and push to GitHub repo feastfuyan/0512.
triggers:
  - "skill audit push"
  - "weekly skill push"
---

# Skill Audit & Push

## Workflow

1. **Discover**: List all skills under `~/.openclaw/workspace/skills/` whose `SKILL.md` mtime is within the last 7 days.
2. **Rank**: Pick the 2 most useful based on:
   - SKILL.md description quality
   - Code complexity / feature richness
   - Practical utility (automation > scaffolding > docs-only)
3. **Audit** each selected skill against these standards:
   - **Hardcoded IPs/ports/URLs**: grep for IP patterns, hardcoded `http://`/`https://` URLs (excluding XML namespaces and example.com)
   - **Hardcoded file paths**: grep for `/Users/`, `/home/`, `/tmp/`, `C:\` in code (not comments/docs)
   - **Plaintext secrets**: grep for `api_key`, `password`, `secret`, `token` assignments with literal string values
   - **Debug residuals**: excessive `console.log` / `print()` beyond status logging, `debugger` statements
   - **Commented-out code**: `# import`, `# def`, `// var`, `// function` etc.
4. **Fix**: Apply fixes for all issues found:
   - Replace hardcoded paths with `os.homedir()` / `os.tmpdir()` / env vars
   - Replace hardcoded IPs/URLs with config or env vars
   - Remove debug residuals
   - Add `.env.example` if secrets were hardcoded
5. **Test**: Run existing tests or create minimal tests to verify fixes don't break functionality.
6. **Push**:
   ```bash
   cd /tmp/0512_repo || gh repo clone feastfuyan/0512 /tmp/0512_repo
   cd /tmp/0512_repo && git pull
   cp -r <skill_path> ./<skill_name>/
   git add -A
   git commit -m "audit: <skill_name> - <summary of fixes>"
   git push origin main
   ```
7. **Report**: Output a summary of what was audited, fixed, and pushed.

## Important
- Do NOT push skills that are purely internal/personal (containing user-specific data)
- Always test before pushing
- Use `$(gh auth token)` for GitHub auth, never hardcode tokens
- Execute completion triple: Glass sound + Tingting voice summary
