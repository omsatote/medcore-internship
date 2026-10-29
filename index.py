"""Vercel entry point for the MedCore JSON API.

The application keeps its business logic in the project-level ``index.py``.
Vercel invokes this ``BaseHTTPRequestHandler`` subclass for requests under
``/api/*``.
"""

from index import Handler


class handler(Handler):
    """Expose the existing MedCore request handler to Vercel."""

    pass
