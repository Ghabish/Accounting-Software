"""Gapless document numbers. The sequence row is locked inside the posting transaction."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounting.models import NumberSequence


def next_number(db: Session, company_id: int, key: str, prefix: str, padding: int = 6) -> str:
    seq = db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id,
                                                 NumberSequence.seq_key == key).with_for_update())
    if seq is None:
        seq = NumberSequence(company_id=company_id, seq_key=key, prefix=prefix, next_value=1, padding=padding)
        db.add(seq)
        db.flush()
        seq = db.scalar(select(NumberSequence).where(NumberSequence.id == seq.id).with_for_update())
    value = seq.next_value
    seq.next_value = value + 1
    return f"{seq.prefix}{str(value).zfill(seq.padding)}"
