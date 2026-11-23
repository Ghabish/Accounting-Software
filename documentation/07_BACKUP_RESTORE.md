# Backup and restore

Two things must be backed up together: the **PostgreSQL database** and the **attachments folder**
(`UCF_ATTACHMENT_DIR`). Nothing else holds business data.

## Nightly backup
* Linux: `scripts/backup_postgres.sh /backups` (cron, e.g. `30 1 * * *`).
* Windows: `scripts/backup_postgres.ps1 -Dest D:\Backups` (Task Scheduler, daily).
Both write a compressed custom-format dump, archive the attachments, verify the dump is readable and keep 30 days.
Copy backups off the server (another site or cloud storage). For point-in-time recovery enable PostgreSQL WAL
archiving or use the managed database's automated backups.

## Restore
```bash
# 1. stop the application service
createdb -U postgres ucfin_restored
pg_restore -U postgres --no-owner --role=ucfin_app -d ucfin_restored /backups/ucfin_YYYYMMDD_HHMMSS.dump
tar -xzf /backups/attachments_YYYYMMDD_HHMMSS.tar.gz -C /var/lib/ucfin/
# 2. point UCF_DATABASE_URL at ucfin_restored (or rename databases), then
alembic upgrade head        # brings an older backup up to the current schema
# 3. start the service and run Reports → Trial balance and Reconciliation status as a check
```
The integrity triggers are part of the schema dump, so they are restored with the data.

## Restore test (quarterly)
Restore the latest backup to a separate database, start a test instance against it and confirm: sign-in works,
the trial balance balances, the balance sheet balances and the sub-ledger reconciliation status is all green.

## Removing demo data
Demo data is only ever loaded with `scripts.load_demo_data` into a demo database. To start production clean,
create a new empty database and run `alembic upgrade head` followed by `python -m scripts.seed` (without `--demo`).
