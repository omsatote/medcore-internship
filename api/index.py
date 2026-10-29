"""Vercel entry point for the MedCore JSON API."""

from index import Handler


class handler(Handler):
    """Expose the existing MedCore request handler to Vercel."""

    pass
