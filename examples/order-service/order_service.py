"""Fictional, in-process order intake example. Not a production service."""

import sqlite3


class RequestConflict(ValueError):
    pass


def connect(database=":memory:"):
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        "id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, "
        "sku TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0))"
    )
    return connection


def submit_order(connection, request_key, sku, quantity):
    if not isinstance(request_key, str) or not request_key.strip():
        raise ValueError("request_key must be a non-empty string")
    if not isinstance(sku, str) or not sku.strip():
        raise ValueError("sku must be a non-empty string")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    with connection:
        connection.execute(
            "INSERT INTO orders (request_key, sku, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(request_key) DO NOTHING",
            (request_key, sku, quantity),
        )
        order_id, existing_sku, existing_quantity = connection.execute(
            "SELECT id, sku, quantity FROM orders WHERE request_key = ?", (request_key,)
        ).fetchone()
        if (existing_sku, existing_quantity) != (sku, quantity):
            raise RequestConflict("request_key already identifies different order data")
    return order_id


if __name__ == "__main__":
    db = connect()
    try:
        first = submit_order(db, "request-1", "BOOK", 2)
        repeated = submit_order(db, "request-1", "BOOK", 2)
        print(f"Order {first}; repeated request returned {repeated}.")
    finally:
        db.close()
