# Security and deployment scope

Contact Emanuele Enrico, e.enrico@inrim.it, for private reports. Do not put credentials or private research data in public issues.

SQE Studio v0.3 is a research application for a trusted laboratory group on one server. Use HTTPS and the provided proxy, current OS/dependencies, restricted administrative access, and institutional network controls. It has application-level access-control and session tests, but has not had an independent security audit or penetration test. Docker deployment and native tools must be qualified on the actual host before use with important data.

Passwords use PBKDF2-HMAC-SHA256 with 600,000 iterations and individual random salts. Sessions are opaque, stored as hashes, expire, and use HttpOnly/SameSite cookies (Secure in deployment mode). Mutations require a session-bound CSRF token and reject foreign origins. There is no open registration, and first-admin setup/activation tokens are random and one-use. Admins can disable accounts and sessions.

Administrator-enabled Python macros are trusted server code. They execute as the worker account and are not a sandbox. Do not enable code from an untrusted contributor. Researchers cannot install/approve code; enabling a version is an audited administrative action. A public source repository does not imply an anonymous public compute service.

The queue limits concurrent jobs and reserves CPU/memory estimates; it does not enforce a per-job cgroup or isolate project processes from malicious enabled code. The worker and scientific software share a service account. Multi-host queues, untrusted tenant isolation, SSO/OIDC, per-user quotas and cluster schedulers require further engineering.

Uploaded logos are decoded as raster data; HTML artifacts are served under a sandbox CSP. Project capsules reject path traversal and symlinks and have bounded sizes. Preserve backups of both SQLite and artifacts. SQLite must reside on a local disk, not an NFS share. Never serve the data directory directly with a static web server.
