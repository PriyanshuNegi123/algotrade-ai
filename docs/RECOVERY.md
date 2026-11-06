# Recovery

- Database unavailable: liveness remains 200; readiness and session operations fail closed.
  Restore DB connectivity, verify migration revision, then retry. No orders can be submitted.
- Missing/old schema: apply reviewed migrations; do not auto-create tables during startup.
- Restart: engine is recreated; session rows persist and expire at their original UTC instant.
  Trading remains disabled unconditionally. No worker attempts autonomous resumption.
- Lost admin password: generate a new Argon2 hash locally, replace secret configuration,
  restart and delete all rows in admin_sessions using authorized database administration.
- Suspected credential leak: restrict network access, revoke sessions, rotate affected secrets,
  retain allowlisted operational logs and investigate. Do not collect broker secrets in chat.
- Future unresolved orders/positions must remain unknown until broker reconciliation;
  this phase does not claim account flatness because it cannot read broker exposure.

PostgreSQL backup/restore is not automated or tested. Encrypted backups, restore drills,
MFA and incident alerts are mandatory later gates before production.
