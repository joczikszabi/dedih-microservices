"""The payments database: one ledger of charges and refunds.

Nothing real is charged. This is a simulation.
Run `python db.py --reset` inside the container to empty the ledger.
"""

import os
import sys
import time
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class LedgerEntry(Base):
    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # "charge" or "refund"
    order_id: Mapped[int] = mapped_column(Integer)
    amount_huf: Mapped[int] = mapped_column(Integer)
    # Who asked for this: the caller's workload identity, see main.py.
    requested_by: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def wait_and_init() -> None:
    for attempt in range(1, 31):
        try:
            Base.metadata.create_all(engine)
            return
        except Exception as error:
            print(f"database not ready (attempt {attempt}): {error}", flush=True)
            time.sleep(2)
    raise SystemExit("database not reachable, giving up")


def reset() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("payments: ledger emptied")


if __name__ == "__main__" and "--reset" in sys.argv:
    reset()
