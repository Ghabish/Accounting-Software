# Security

## Authentication
* Passwords hashed with PBKDF2-HMAC-SHA256 (390,000 iterations, per-user salt; configurable), never stored or logged in clear.
* Password policy: minimum 10 characters with upper and lower case letters and a digit (configurable length).
* Account lockout after 5 failed sign-ins for 15 minutes; per-IP throttle (20 failures / 15 minutes) against password spraying.
* Signed JWT bearer tokens (HS256, 8-hour expiry). Every token carries the user's token version: changing the
  password, "sign out" (all sessions) or deactivating the user revokes existing tokens immediately.
* New users and password resets can be forced to change the password at next sign-in.
* In production the server refuses to start with the default or a short secret key, or with SQLite.

## Authorisation
* Role-based access control with ~90 granular permissions (`backend/authentication/permissions.py`); roles are
  editable. Seeded roles: CFO, Finance Manager, Accountant, AP Officer, AR Officer, Cashier, Site Manager,
  Auditor (read-only), System Administrator (no finance posting).
* Site scoping: users without *all sites* see and post only their sites' transactions, reports and documents.
* Workflow controls: segregation of duties for preparer / checker / approver / poster (no self-approval, even for
  the CFO), approval limits by document type, role / user, site and amount.
* Period control: closed and locked periods reject postings; reopening is CFO-only, reasoned and audited.

## Data integrity
* Posted ledger data is immutable at three layers: application rules, ORM guards and PostgreSQL triggers.
* Balanced-journal constraint trigger, CHECK constraints on amounts, foreign keys everywhere (no orphan records),
  unique keys preventing duplicate postings and duplicate supplier invoices.
* All posting happens inside one database transaction with row locks on the document, the period and number
  sequences (no double posting, gapless numbering).
* Append-only audit log (PostgreSQL trigger blocks update / delete) with user, time, action, old / new values,
  IP address and user agent.

## Web security
* Same-origin API (CORS off by default), `Content-Security-Policy`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS in production,
  `Cache-Control: no-store` on all API responses; the service worker never caches API data.
* Input validation on every request (Pydantic schemas); SQL is built by SQLAlchemy (parameterised).
* Uploads: allow-listed content types (PDF, images, CSV, Excel, Word, text), size limit (20 MB), sanitised file
  names, stored outside the web root with a SHA-256 hash; attachments of posted documents cannot be deleted.
* Tokens are kept in the browser's session storage (cleared when the browser closes).

## Operating recommendations
1. Serve only over HTTPS (TLS at IIS / nginx / the cloud load balancer); keep port 8000 bound to localhost.
2. Use a dedicated PostgreSQL role with access to this database only; restrict network access to the DB server.
3. Generate `UCF_SECRET_KEY` with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and keep `.env` readable only by the service account.
4. Remove `UCF_ADMIN_PASSWORD` after the first run; disable the `admin` account once named administrators exist.
5. Set `UCF_ENABLE_API_DOCS=false` on internet-facing servers if API documentation should not be public.
6. Back up nightly and test restores quarterly (see 07_BACKUP_RESTORE.md); review the audit trail and user list monthly.
7. When running several server instances, also rate-limit `/api/auth/login` at the reverse proxy (the in-process IP throttle is per process).
