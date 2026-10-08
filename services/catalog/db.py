"""The catalog database: products, prices and stock.

Only the catalog service talks to this database. Other services ask catalog
over HTTP. That is what "a microservice owns its data" means in practice.

Run `python db.py --reset` inside the container to restore the seed data.
"""

import os
import sys
import time

from sqlalchemy import Boolean, Integer, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

# pool_pre_ping checks a pooled connection before using it, so a restarted
# database does not leave us holding dead connections.
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500))
    price_huf: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer)
    limited: Mapped[bool] = mapped_column(Boolean, default=False)


SEED_PRODUCTS = [
    # The limited item. 20 units, and the bot in scripts/bot.sh wants all of them.
    Product(id=1, name="Handheld Console, 2026 re-release", price_huf=49990, stock=20, limited=True,
            description="Limited run of the classic handheld. 20 units in total."),
    Product(id=2, name="8-bit Home Console, refurbished", price_huf=39990, stock=12,
            description="Tested, cleaned, with one wired controller."),
    Product(id=3, name="Platformer Cartridge", price_huf=8990, stock=40,
            description="Jump, run, collect coins. Battery save."),
    Product(id=4, name="Racing Cartridge", price_huf=7990, stock=35,
            description="Eight tracks, split screen for two players."),
    Product(id=5, name="Puzzle Cartridge", price_huf=5990, stock=50,
            description="Falling blocks, endless mode."),
    Product(id=6, name="Arcade Joystick", price_huf=12990, stock=25,
            description="Eight-way stick, two buttons, USB."),
    Product(id=7, name="Wired Controller", price_huf=4990, stock=60,
            description="Replacement controller, 2 m cable."),
    Product(id=8, name="Memory Card 1 MB", price_huf=2990, stock=80,
            description="Fifteen save slots."),
]


def seed(session: Session) -> None:
    """Insert the seed products if the table is empty."""
    if session.scalar(select(func.count()).select_from(Product)) == 0:
        for product in SEED_PRODUCTS:
            session.merge(product)
        session.commit()


def wait_and_init() -> None:
    """Wait for Postgres, create the tables and seed them. Called at startup."""
    for attempt in range(1, 31):
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                seed(session)
            return
        except Exception as error:  # the database may still be starting
            print(f"database not ready (attempt {attempt}): {error}", flush=True)
            time.sleep(2)
    raise SystemExit("database not reachable, giving up")


def reset() -> None:
    """Drop everything and start again from the seed data."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed(session)
    print("catalog: seed data restored")


if __name__ == "__main__" and "--reset" in sys.argv:
    reset()
