"""The invoicing database: invoices and whether the external system has them.

Run `python db.py --reset` inside the container to empty it.
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


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer)
    customer_email: Mapped[str] = mapped_column(String(200))
    amount_huf: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # "pending" or "sent"
    reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def wait_and_init() -> None:
    for attempt in range(1, 91):
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
    print("invoicing: invoices emptied")


if __name__ == "__main__" and "--reset" in sys.argv:
    reset()
