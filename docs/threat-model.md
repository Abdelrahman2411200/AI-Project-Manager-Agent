# MVP Threat Model

Status: reviewed with no unresolved Critical or High release risk. Scope: browser, API,
worker, PostgreSQL, AI-provider boundary, Markdown export, backup files, and CI.

## Assets and trust boundaries

Assets are credentials, session tokens, project content, approved plans, audit history,
reports, provider usage/cost data, and backups. Trust boundaries exist at browser-to-API,
API/worker-to-database, worker-to-provider, export download, CI-to-package registries, and
operator-to-backup storage.

## Abuse cases and controls

| Threat | Primary controls | Verification | Residual risk |
|---|---|---|---|
| Account/session takeover | Argon2id, opaque hashed sessions, Secure/HttpOnly/SameSite cookie, CSRF token, expiry/revocation | Auth/session and CSRF tests | Medium: endpoint/device compromise |
| Cross-owner data access | Owner-scoped services, indirect-ID checks, 404 for foreign resources | Authorization integration suite | Low |
| Prompt injection/data exfiltration | Project text treated as data, no model tools, bounded context, strict schema/reference/business validation, `store=false` | Contract and injection fixtures | Medium: persuasive user-authored content |
| Active-plan corruption | Approval boundary, content hashes, row locks, immutable versions, no model write path | Lifecycle/concurrency tests | Low |
| Dependency/graph corruption | Version-local FKs, duplicate/self checks, deterministic cycle validation | Domain and PostgreSQL tests | Low |
| Request/AI abuse | Body limit, request timeout, per-session/IP AI rate limit, daily owner run/token limits, per-run budget | Hardening and budget tests | Medium: distributed abuse; edge rate limit required in production |
| XSS/unsafe export | React escaping, Markdown sanitization, attachment download, restrictive CSP, `nosniff` | Malicious Markdown and header tests | Low |
| Sensitive error/log leakage | Problem Details allowlist, correlation IDs, no stack/SQL/provider payloads, redacted telemetry | Safe-error tests and review | Low |
| Duplicate worker execution | Atomic `SKIP LOCKED` claim, lease token, heartbeat, idempotent checkpoint | Concurrent claim/resume tests | Low |
| Dependency/supply-chain compromise | Lockfiles, pinned CI actions, dependency/SAST/secret scans, least workflow permissions | CI security gate | Medium: registry compromise |
| Backup disclosure/tampering | AES-256-CBC/PBKDF2 encryption, out-of-band passphrase, SHA-256 manifest, restricted storage | Restore drill | Medium: operator key handling |
| Denial of service | Request/body/time limits, bounded schemas, async jobs, queue/cost alerts | Load/failure tests | Medium: deployment edge saturation |

## Release rules

Critical or High findings block release. Medium findings require an owner and mitigation date.
Secrets must never be committed; rotate any credential that appears in a log or CI artifact.
Production must terminate TLS at a trusted proxy, set secure cookies, apply a global edge rate
limit, restrict database/network access, and store backup passphrases outside the backup
location.

The client-only Vite build has one advisory-specific not-applicable exception for
`GHSA-qwww-vcr4-c8h2`: the affected React Router RSC/server-action mode is not installed or
enabled. The audit script permits only that exact advisory/dependency chain; any new High or
Critical finding still blocks CI.

## Data flow review

Only node-required, schema-bounded fields cross the provider boundary. Password hashes,
session material, raw headers, database URLs, CSRF tokens, and unrelated project records are
never included. Audit and provider-usage records retain identifiers, outcome, latency, and
token counts—not chain-of-thought or raw provider payloads.
