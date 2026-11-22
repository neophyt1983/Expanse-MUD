"""Durable, offscreen municipal membership for disposable founding simulations."""
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS resident (
    id TEXT PRIMARY KEY, city TEXT, alive INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS by_city ON resident(city) WHERE city IS NOT NULL;
CREATE TABLE IF NOT EXISTS membership_event (
    id TEXT PRIMARY KEY, minute INTEGER NOT NULL, person TEXT NOT NULL,
    kind TEXT NOT NULL, origin TEXT, destination TEXT
);
CREATE INDEX IF NOT EXISTS by_person ON membership_event(person, minute, id);
CREATE INDEX IF NOT EXISTS chronology ON membership_event(minute DESC, id DESC);
"""


def open_register(path):
    db = sqlite3.connect(path, isolation_level=None)
    db.executescript(SCHEMA)
    return db


def apply_batch(db, events):
    """Commit one dated batch atomically. Exact retries are safe after restart."""
    db.execute("BEGIN IMMEDIATE")
    try:
        latest = db.execute(
            "SELECT minute,id FROM membership_event ORDER BY minute DESC,id DESC LIMIT 1"
        ).fetchone()
        for event in sorted(events, key=lambda row: (row[1], row[0])):
            key, minute, person, kind, origin, destination = event
            if not key or not person or type(minute) is not int:
                raise ValueError("Missing event identity, resident identity or date")
            prior = db.execute("SELECT * FROM membership_event WHERE id=?", (key,)).fetchone()
            if prior == tuple(event):
                continue
            if prior or (latest and (minute, key) <= latest):
                raise ValueError("Conflicting or out-of-order founding event")
            state = db.execute("SELECT city,alive FROM resident WHERE id=?", (person,)).fetchone()
            if kind in ("founder", "birth", "immigration"):
                if state is not None or origin is not None or not destination:
                    raise ValueError("Invalid new resident")
                db.execute("INSERT INTO resident VALUES (?,?,1)", (person, destination))
            elif kind in ("move", "death", "emigration"):
                if not origin or state != (origin, 1):
                    raise ValueError("Resident is absent from the stated origin")
                if kind == "move":
                    if not destination or destination == origin:
                        raise ValueError("A move needs a different destination")
                elif destination is not None:
                    raise ValueError("Departures and deaths have no municipal destination")
                db.execute("UPDATE resident SET city=?,alive=? WHERE id=?",
                           (destination, kind != "death", person))
            elif kind == "return":
                if state != (None, 1) or origin is not None or not destination:
                    raise ValueError("Only a living emigrant can return")
                db.execute("UPDATE resident SET city=? WHERE id=?", (destination, person))
            else:
                raise ValueError("Unknown membership event")
            db.execute("INSERT INTO membership_event VALUES (?,?,?,?,?,?)", event)
            latest = minute, key
        db.commit()
    except BaseException:
        db.rollback()
        raise


def census(db):
    return dict(db.execute(
        "SELECT city,count(*) FROM resident WHERE city IS NOT NULL GROUP BY city"
    ))
