# Security Policy

## Overview

ScrapAI is a web scraping framework built by [DiscourseLab](https://www.discourselab.ai/). We take security seriously and appreciate the responsible disclosure of security vulnerabilities.

This document outlines our security policy, how to report vulnerabilities, and what to expect from our security response process.

---

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          | Notes                          |
| ------- | ------------------ | ------------------------------ |
| main    | :white_check_mark: | Latest development version     |
| 1.x     | :white_check_mark: | Current stable release         |
| < 1.0   | :x:                | No longer supported            |

**Recommendation:** Always use the latest stable release for production deployments.

---

## Reporting a Vulnerability

**Please DO NOT report security vulnerabilities through public GitHub issues.**

### How to Report

**For security vulnerabilities, email us directly:**

📧 **dev@discourselab.ai**

### What to Include

Please provide as much information as possible:

1. **Type of vulnerability** (e.g., SQL injection, command injection, XSS)
2. **Affected component** (e.g., CLI command, spider, Cloudflare handler)
3. **Steps to reproduce** (detailed, with example commands/payloads)
4. **Impact assessment** (what an attacker could do)
5. **Suggested fix** (optional, but appreciated)
6. **Your contact information** (for follow-up questions)

### Example Report

```
Subject: [SECURITY] Command Injection in Spider Import

Vulnerability Type: Command Injection
Component: cli/spiders.py (spider import command)
Severity: High

Description:
The `./scrapai spiders import` command does not validate the spider
name field, allowing arbitrary command execution.

Steps to Reproduce:
1. Create malicious_spider.json with name: "; rm -rf /"
2. Run: ./scrapai spiders import malicious_spider.json
3. Command executes on import

Impact:
Remote code execution via malicious spider configuration files.

Suggested Fix:
Validate spider names with regex: ^[a-zA-Z0-9_-]+$
```

---

## Response Process

### Timeline

- **24 hours:** Initial acknowledgment of your report
- **72 hours:** Preliminary assessment (severity, impact, affected versions)
- **7 days:** Detailed response with fix timeline or clarification questions
- **30 days:** Security patch released (for confirmed vulnerabilities)

### What Happens Next

1. **Acknowledgment:** We'll confirm receipt and assign a tracking ID
2. **Investigation:** We'll reproduce the issue and assess impact
3. **Fix Development:** We'll develop and test a fix internally
4. **Coordinated Disclosure:** We'll coordinate a release date with you
5. **Public Disclosure:** We'll publish a security advisory with credit

### Security Advisories

Security fixes will be announced via:
- GitHub Security Advisories
- Release notes with `[SECURITY]` tag
- Email notification to commercial license holders

---

## Scope

### In Scope ✅

We welcome reports on:

- **Injection vulnerabilities** (SQL, command, code injection)
- **Authentication/authorization bypass**
- **Path traversal / directory access**
- **Remote code execution (RCE)**
- **Sensitive data exposure** (credentials, API keys leaking)
- **Unsafe deserialization**
- **Server-side request forgery (SSRF)**
- **XML external entity (XXE) attacks**
- **Insecure defaults** (weak configurations)
- **Dependency vulnerabilities** (if actively exploitable in ScrapAI context)

### Out of Scope ❌

The following are **NOT** security vulnerabilities:

- **Web scraping ethics** (scraping public websites is not a vulnerability)
- **Rate limiting bypass** (ScrapAI is designed to crawl efficiently)
- **Cloudflare bypass techniques** (this is a core feature, not a bug)
- **Robots.txt violations** (users control their own robots.txt compliance)
- **Social engineering attacks** (attacking ScrapAI users, not the software)
- **Denial of Service** (local CLI tool, not a public service)
- **Browser automation detection** (expected behavior, not a security issue)
- **Outdated dependencies** (unless actively exploitable in ScrapAI)

### Responsible Use

ScrapAI is a **legitimate web scraping tool**. Users are responsible for:
- Complying with website terms of service
- Respecting robots.txt (configurable in settings)
- Not violating computer fraud laws (CFAA, etc.)
- Ethical data collection practices

**We do not consider "ability to scrape protected content" a vulnerability.**

---

## Safe Harbor

We support safe harbor for security researchers who:

- **Act in good faith** to identify and report vulnerabilities
- **Do not exploit vulnerabilities** beyond proof-of-concept
- **Do not access, modify, or delete user data** without permission
- **Do not disrupt services** (including our infrastructure or third-party sites)
- **Respect user privacy** (do not exfiltrate personal data)
- **Give us reasonable time to fix** before public disclosure (90 days)

We commit to:
- **Not pursue legal action** against researchers following this policy
- **Work with you** to understand and resolve the issue
- **Publicly acknowledge your contribution** (unless you prefer anonymity)

---

## Security Best Practices for Users

### Running ScrapAI Securely

**1. Use Virtual Environments**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Validate Spider Configurations**
```bash
# Never import untrusted spider configs
# Always review JSON before importing
cat spider.json  # Review first
./scrapai spiders import spider.json --project myproject
```

**3. Secure Database Credentials**
```bash
# Use strong passwords in .env
# Never commit .env to git
DATABASE_URL="postgresql://user:STRONG_PASSWORD@localhost/db"
```

**4. Limit Scrapy Concurrency**
```json
{
  "CONCURRENT_REQUESTS": 8,
  "DOWNLOAD_DELAY": 1,
  "AUTOTHROTTLE_ENABLED": true
}
```

**5. Use Least Privilege**
```bash
# Don't run as root
# Use dedicated user account for production crawls
useradd -m scrapai-runner
sudo -u scrapai-runner ./scrapai crawl myspider --project prod
```

**6. Keep Dependencies Updated**
```bash
# Check for security updates regularly
pip list --outdated
pip install --upgrade scrapy sqlalchemy
```

**7. Review Logs**
```bash
# Monitor for suspicious activity
grep ERROR logs/scrapai.log
grep WARNING logs/scrapai.log
```

---

## Known Security Considerations

### Browser Automation

ScrapAI uses Playwright and nodriver for browser automation. This involves:
- **Launching browser processes** (isolated, but still inherits environment)
- **Executing JavaScript** (from target websites, not user input)
- **Downloading browser binaries** (from official sources)

**Mitigation:** Browsers run in isolated profiles. No persistent cookies unless explicitly configured.

### Cloudflare Bypass

ScrapAI's Cloudflare bypass uses browser automation to obtain cookies. This:
- **Does not exploit Cloudflare vulnerabilities** (legitimate browser verification)
- **Stores cookies in memory** (cached per spider, cleared on exit)
- **Falls back to browser** if HTTP requests are blocked

**Mitigation:** Cookies are not persisted to disk. Browser is cleaned up on exit.

### Database Storage

ScrapAI stores scraped data in SQLite or PostgreSQL:
- **Uses SQLAlchemy ORM** (prevents SQL injection)
- **No raw SQL execution** (all queries parameterized)
- **WAL mode for SQLite** (concurrent read/write safety)

**Mitigation:** Database file permissions should be restricted (chmod 600).

### File System Access

ScrapAI writes to:
- `data/` directory (crawl outputs, exports)
- `logs/` directory (application logs)
- `.env` file (credentials)

**Mitigation:** Run ScrapAI in isolated directory. Never run as root.

---

## Security Updates

### Subscribing to Updates

**Watch this repository:**
- GitHub: Click "Watch" → "Custom" → "Security alerts"
- Release notes: Check `CHANGELOG.md` for `[SECURITY]` tags

**Commercial users:**
- Email security notifications (included with license)
- Priority security patches

---

## Bug Bounty Program

We currently **do not** offer a formal bug bounty program.

However, we deeply appreciate security research and will:
- **Publicly acknowledge** your contribution (in release notes, CONTRIBUTORS.md)
- **Provide attribution** in security advisories
- **Consider donations/compensation** for critical vulnerabilities (at our discretion)

For commercial security assessments or penetration testing, contact: **info@discourselab.ai**

---

## Questions?

If you have questions about this security policy, contact:

📧 **dev@discourselab.ai**
🌐 **https://www.discourselab.ai/**

---

## Version History

| Date       | Version | Changes                                      |
| ---------- | ------- | -------------------------------------------- |
| 2026-02-22 | 1.0     | Initial security policy                      |

---

**Thank you for helping keep ScrapAI and its users safe!**
