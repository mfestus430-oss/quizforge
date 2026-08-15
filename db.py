"""SQLite persistence: tutor sessions, courses, user accounts and sync data."""
import hashlib
import json
import os
import secrets
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with _conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS store ("
                  "kind TEXT, id TEXT, data TEXT, updated REAL, PRIMARY KEY(kind, id))")
        c.execute("CREATE TABLE IF NOT EXISTS users ("
                  "username TEXT PRIMARY KEY, pw_hash TEXT, salt TEXT, token TEXT, created REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS sync ("
                  "username TEXT PRIMARY KEY, data TEXT, updated REAL)")


# ---- generic object store (tutor sessions, courses) -------------------------

def save_obj(kind, id_, obj):
    with _conn() as c:
        c.execute("REPLACE INTO store VALUES (?,?,?,?)",
                  (kind, id_, json.dumps(obj), time.time()))
        # expire anything unused for 14 days
        c.execute("DELETE FROM store WHERE kind=? AND updated < ?",
                  (kind, time.time() - 14 * 86400))


def load_obj(kind, id_):
    with _conn() as c:
        row = c.execute("SELECT data FROM store WHERE kind=? AND id=?",
                        (kind, id_)).fetchone()
    return json.loads(row[0]) if row else None


# ---- accounts ---------------------------------------------------------------

def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()


def register(username, password):
    salt = secrets.token_hex(16)
    token = secrets.token_hex(24)
    try:
        with _conn() as c:
            c.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                      (username, _hash(password, salt), salt, token, time.time()))
        return token
    except sqlite3.IntegrityError:
        return None  # username taken


def login(username, password):
    with _conn() as c:
        row = c.execute("SELECT pw_hash, salt FROM users WHERE username=?",
                        (username,)).fetchone()
        if not row or _hash(password, row[1]) != row[0]:
            return None
        token = secrets.token_hex(24)
        c.execute("UPDATE users SET token=? WHERE username=?", (token, username))
    return token


def user_from_token(token):
    if not token:
        return None
    with _conn() as c:
        row = c.execute("SELECT username FROM users WHERE token=?", (token,)).fetchone()
    return row[0] if row else None


def google_login(username, email):
    """Find-or-create an account backed by a verified Google email."""
    with _conn() as c:
        row = c.execute("SELECT username FROM users WHERE username=?", (username,)).fetchone()
        token = secrets.token_hex(24)
        if row:
            c.execute("UPDATE users SET token=? WHERE username=?", (token, username))
        else:
            # google accounts have no local password; store a random unusable hash
            salt = secrets.token_hex(16)
            c.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                      (username, "google:" + hashlib.sha256(email.encode()).hexdigest(),
                       salt, token, time.time()))
    return token


# ---- sync (library backup per user) ------------------------------------------

def save_sync(username, data):
    with _conn() as c:
        c.execute("REPLACE INTO sync VALUES (?,?,?)",
                  (username, json.dumps(data), time.time()))


def load_sync(username):
    with _conn() as c:
        row = c.execute("SELECT data FROM sync WHERE username=?", (username,)).fetchone()
    return json.loads(row[0]) if row else {}
