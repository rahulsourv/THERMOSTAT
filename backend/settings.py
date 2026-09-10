"""
Database connection settings.

Two ways to configure, and the second one is safer:

  1. SUPABASE_DB_URL  - one connection string.
     Fragile: a URL uses ':' and '@' as separators, so if your password
     contains either of those the string is parsed wrongly. That is exactly
     what happens with a password like "abc@123".

  2. SUPABASE_HOST / USER / PASSWORD / PORT / DB  - separate fields.
     Nothing is parsed, so any character in the password is fine.

If both are present, the separate fields win.
"""

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def connection_kwargs():
    """Return keyword arguments for psycopg2.connect()."""
    host = os.getenv("SUPABASE_HOST")

    if host:
        password = os.getenv("SUPABASE_PASSWORD")
        if not password:
            raise RuntimeError("SUPABASE_HOST is set but SUPABASE_PASSWORD is not.")
        return {
            "host": host,
            "port": int(os.getenv("SUPABASE_PORT", "5432")),
            "user": os.getenv("SUPABASE_USER", "postgres"),
            "password": password,
            "dbname": os.getenv("SUPABASE_DB", "postgres"),
            "connect_timeout": 20,
            "sslmode": "require",
        }

    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "No database settings found.\n"
            "Copy backend/.env.example to backend/.env and fill it in."
        )
    return {"dsn": url, "connect_timeout": 20}


def describe():
    """Host and user only - never the password. Safe to print or log."""
    kw = connection_kwargs()
    if "dsn" in kw:
        tail = kw["dsn"].rsplit("@", 1)[-1]
        return f"(from URL) {tail}"
    return f"{kw['user']}@{kw['host']}:{kw['port']}/{kw['dbname']}"


def as_url():
    """Build a properly escaped URL, for tools that require one.

    quote() turns '@' into '%40' and ':' into '%3A' so the password
    cannot be mistaken for a separator.
    """
    kw = connection_kwargs()
    if "dsn" in kw:
        return kw["dsn"]
    return (
        f"postgresql://{quote(kw['user'], safe='')}:"
        f"{quote(kw['password'], safe='')}@"
        f"{kw['host']}:{kw['port']}/{kw['dbname']}?sslmode=require"
    )
