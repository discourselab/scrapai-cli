# Security Policy

## Reporting a Vulnerability

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Email us directly: **dev@discourselab.ai**

Include:
1. Type of vulnerability (SQL injection, command injection, SSRF, etc.)
2. Affected component (CLI command, spider, handler)
3. Steps to reproduce
4. Impact assessment

We'll acknowledge within 72 hours and work with you on a fix.

## Scope

### In Scope

- Injection vulnerabilities (SQL, command, code)
- Path traversal / directory access
- Remote code execution
- Sensitive data exposure
- Server-side request forgery (SSRF)
- Insecure defaults

### Out of Scope

- Web scraping ethics (scraping public websites is not a vulnerability)
- Cloudflare bypass techniques (core feature, not a bug)
- Robots.txt violations (user responsibility)
- Outdated dependencies (unless actively exploitable)

## Safe Harbor

We will not pursue legal action against researchers who act in good faith, do not exploit vulnerabilities beyond proof-of-concept, and give us reasonable time to fix before public disclosure.

We will publicly acknowledge your contribution unless you prefer anonymity.

## Questions

📧 **dev@discourselab.ai**
