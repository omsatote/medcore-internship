"""Vercel entry point for the MedCore JSON API."""

import os

os.environ.setdefault("MEDCORE_DB_PATH", "/tmp/medcore.db")

from index import Handler, init_db

init_db()


class handler(Handler):
    """Expose the existing MedCore request handler to Vercel."""

    pass
