# Storage decision

The user reports5TB of Google Drive capacity and selected it for project storage.
PostgreSQL remains the working transactional database for metadata, candles, sessions,
event integrity, permissions and migrations. Google Drive is the chosen future destination
for exported archives and backups; capacity alone does not configure that connection.

Do not place an active PostgreSQL data directory, Docker volume or live SQLite database in
a desktop-synchronized Drive folder. Export a consistent database snapshot instead. Keep
checksummed immutable archive exports separate from working data. Sensitive backups require
client-side encryption and separately protected recovery keys; exclude plaintext local
credentials, browser sessions, environment files and raw credential-bearing URLs.

Google Desktop OAuth and one116-byte synthetic upload/download are now verified;
see GOOGLE_DRIVE.md. No working database was migrated, backup scheduled or restore verified. A future backup task must configure authorized Drive access,
verify the app's actual API limits/scopes, preserve source checksums and perform an isolated
restore drill before claiming backups work. Broker OAuth and Google Drive authorization
are separate integrations. Existing local data/settings remain unchanged.

Manual encrypted PostgreSQL Drive backup and independent isolated restore now verified;
see BACKUPS.md. Scheduling,retention and off-device recovery-key escrow remain pending.

User's updated policy:cloud-first encrypted backups every3IST calendar days;installed
LaunchAgent checks at21:30IST. New ciphertext is not cached locally;one old verified local
copy removed after cloud revalidation. PostgreSQL remains local;no cloud data deleted.
Offline key/receipt copy still missing. See BACKUP_SCHEDULE.md.
