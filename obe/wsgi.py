"""
WSGI config for obe project.
Auto-runs migrations on every startup so PythonAnywhere never needs
manual manage.py commands after a git pull.
"""

import os
import subprocess
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'obe.settings')

# ── Auto-migrate on startup ───────────────────────────────────────────────────
try:
    from django.core.management import call_command
    from django.db import connection

    # Run migrations silently
    call_command('migrate', '--run-syncdb', verbosity=0)

    # Seed only if database is empty (no users yet)
    with connection.cursor() as cursor:
        try:
            cursor.execute("SELECT COUNT(*) FROM core_user")
            count = cursor.fetchone()[0]
        except Exception:
            count = 0

    if count == 0:
        call_command('seed', verbosity=0)

    # Always ensure specific accounts exist (idempotent — safe every startup)
    call_command('ensure_accounts', verbosity=0)

except Exception as e:
    # Never crash the server on startup errors — log and continue
    print(f"[WSGI startup] Migration/seed error: {e}", file=sys.stderr)

# ── WSGI application ──────────────────────────────────────────────────────────
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
