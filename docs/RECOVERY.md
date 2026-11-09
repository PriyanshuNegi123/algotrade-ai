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

Manual encrypted PostgreSQL backup and network-isolated cloud restore checks are now
implemented and actually verified; see [BACKUPS.md](BACKUPS.md). The requested three-day cloud schedule is installed; see BACKUP_SCHEDULE.md.
Cloud retention deletion, off-device key escrow and production cutover remain pending. MFA and incident
alerts remain mandatory later gates before production.
