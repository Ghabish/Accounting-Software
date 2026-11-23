"""PostgreSQL integrity triggers (defence in depth beneath the application rules).

1. Posted journal lines can never be updated or deleted.
2. Posted / reversed journals cannot be deleted, and their financial header fields cannot change.
3. A journal can only reach POSTED if its lines balance (deferred constraint trigger).
4. The audit log is append-only.
"""
from __future__ import annotations

from sqlalchemy import text

TRIGGERS_SQL = r"""
CREATE OR REPLACE FUNCTION ucf_protect_posted_lines() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.is_posted THEN RAISE EXCEPTION 'UCF: posted journal lines cannot be deleted (journal %)', OLD.journal_id; END IF;
    RETURN OLD;
  END IF;
  IF OLD.is_posted THEN
    RAISE EXCEPTION 'UCF: posted journal lines cannot be modified (journal %)', OLD.journal_id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_protect_posted_lines ON journal_lines;
CREATE TRIGGER trg_protect_posted_lines BEFORE UPDATE OR DELETE ON journal_lines
  FOR EACH ROW EXECUTE FUNCTION ucf_protect_posted_lines();

CREATE OR REPLACE FUNCTION ucf_protect_posted_journals() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('POSTED','REVERSED') THEN RAISE EXCEPTION 'UCF: posted journal % cannot be deleted', OLD.number; END IF;
    RETURN OLD;
  END IF;
  IF OLD.status IN ('POSTED','REVERSED') THEN
    IF NEW.status NOT IN ('POSTED','REVERSED')
       OR NEW.total_debit <> OLD.total_debit OR NEW.total_credit <> OLD.total_credit
       OR NEW.posting_date <> OLD.posting_date OR NEW.number IS DISTINCT FROM OLD.number
       OR NEW.company_id <> OLD.company_id OR NEW.period_id IS DISTINCT FROM OLD.period_id THEN
      RAISE EXCEPTION 'UCF: posted journal % cannot be modified; use a reversal', OLD.number;
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_protect_posted_journals ON journal_entries;
CREATE TRIGGER trg_protect_posted_journals BEFORE UPDATE OR DELETE ON journal_entries
  FOR EACH ROW EXECUTE FUNCTION ucf_protect_posted_journals();

CREATE OR REPLACE FUNCTION ucf_check_balanced() RETURNS trigger AS $$
DECLARE dr numeric; cr numeric;
BEGIN
  IF NEW.status = 'POSTED' THEN
    SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) INTO dr, cr FROM journal_lines WHERE journal_id = NEW.id;
    IF dr <> cr OR dr = 0 OR dr <> NEW.total_debit THEN
      RAISE EXCEPTION 'UCF: journal % is not balanced (Dr %, Cr %)', NEW.id, dr, cr;
    END IF;
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_balanced ON journal_entries;
CREATE CONSTRAINT TRIGGER trg_check_balanced AFTER INSERT OR UPDATE ON journal_entries
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ucf_check_balanced();

CREATE OR REPLACE FUNCTION ucf_audit_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'UCF: audit log is append-only';
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_append_only ON audit_log;
CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION ucf_audit_append_only();
"""

DROP_SQL = r"""
DROP TRIGGER IF EXISTS trg_protect_posted_lines ON journal_lines;
DROP TRIGGER IF EXISTS trg_protect_posted_journals ON journal_entries;
DROP TRIGGER IF EXISTS trg_check_balanced ON journal_entries;
DROP TRIGGER IF EXISTS trg_audit_append_only ON audit_log;
DROP FUNCTION IF EXISTS ucf_protect_posted_lines();
DROP FUNCTION IF EXISTS ucf_protect_posted_journals();
DROP FUNCTION IF EXISTS ucf_check_balanced();
DROP FUNCTION IF EXISTS ucf_audit_append_only();
"""


def install_triggers(conn) -> None:
    if conn.dialect.name != "postgresql":
        return
    conn.execute(text(TRIGGERS_SQL))


def drop_triggers(conn) -> None:
    if conn.dialect.name != "postgresql":
        return
    conn.execute(text(DROP_SQL))
