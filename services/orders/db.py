"""The orders database: customers, orders and order lines.

Only the orders service talks to this database.
All names, e-mail addresses and delivery addresses are made up.

Run `python db.py --reset` inside the container to restore the seed data.
"""

import hashlib
import os
import sys
import time
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="customer")  # "customer" or "admin"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(30))  # pending, paid, payment_failed, refunded
    total_huf: Mapped[int] = mapped_column(Integer)
    delivery_name: Mapped[str] = mapped_column(String(200))
    delivery_address: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    items: Mapped[list["OrderItem"]] = relationship(lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(Integer)
    product_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_huf: Mapped[int] = mapped_column(Integer)


def hash_password(password: str) -> str:
    # A fixed salt keeps the lab readable. A real system uses a random salt per user.
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"retro-shop-lab", 100_000).hex()


def seed(session: Session) -> None:
    if session.scalar(select(func.count()).select_from(Customer)) > 0:
        return
    session.add_all([
        Customer(id=1, email="alice@example.com", password_hash=hash_password("alice123"),
                 name="Alice Example", address="12 Sample Street, 1111 Testville", role="customer"),
        Customer(id=2, email="bob@example.com", password_hash=hash_password("bob123"),
                 name="Bob Example", address="34 Placeholder Road, 2222 Mocktown", role="customer"),
        Customer(id=3, email="admin@example.com", password_hash=hash_password("admin123"),
                 name="Shop Admin", address="1 Back Office Lane, 3333 Testville", role="admin"),
    ])
    session.flush()
    # Orders 1 and 2 belong to Alice, 3 and 4 to Bob. Block 2 reads Bob's order as Alice.
    session.add_all([
        Order(id=1, customer_id=1, status="paid", total_huf=8990,
              delivery_name="Alice Example", delivery_address="12 Sample Street, 1111 Testville",
              items=[OrderItem(product_id=3, product_name="Platformer Cartridge", quantity=1, unit_price_huf=8990)]),
        Order(id=2, customer_id=1, status="paid", total_huf=4990,
              delivery_name="Alice Example", delivery_address="12 Sample Street, 1111 Testville",
              items=[OrderItem(product_id=7, product_name="Wired Controller", quantity=1, unit_price_huf=4990)]),
        Order(id=3, customer_id=2, status="paid", total_huf=39990,
              delivery_name="Bob Example", delivery_address="34 Placeholder Road, 2222 Mocktown",
              items=[OrderItem(product_id=2, product_name="8-bit Home Console, refurbished", quantity=1, unit_price_huf=39990)]),
        Order(id=4, customer_id=2, status="paid", total_huf=16970,
              delivery_name="Bob Example", delivery_address="34 Placeholder Road, 2222 Mocktown",
              items=[OrderItem(product_id=4, product_name="Racing Cartridge", quantity=1, unit_price_huf=7990),
                     OrderItem(product_id=8, product_name="Memory Card 1 MB", quantity=1, unit_price_huf=2990),
                     OrderItem(product_id=5, product_name="Puzzle Cartridge", quantity=1, unit_price_huf=5990)]),
    ])
    session.flush()
    # The ids above were set by hand, so move the sequences past them.
    session.execute(text("SELECT setval('customers_id_seq', (SELECT max(id) FROM customers))"))
    session.execute(text("SELECT setval('orders_id_seq', (SELECT max(id) FROM orders))"))
    session.commit()


def wait_and_init() -> None:
    for attempt in range(1, 31):
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                seed(session)
            return
        except Exception as error:
            print(f"database not ready (attempt {attempt}): {error}", flush=True)
            time.sleep(2)
    raise SystemExit("database not reachable, giving up")


def reset() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed(session)
    print("orders: seed data restored")


if __name__ == "__main__" and "--reset" in sys.argv:
    reset()
