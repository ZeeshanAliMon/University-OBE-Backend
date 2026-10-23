"""
Run seed_full_demo.py as a management command so it works on Windows too:

    python manage.py seed_full_demo

"manage.py shell < file.py" only executes piped input on non-Windows systems
(Django skips it when sys.platform == "win32"), so on Windows the file is fed
line-by-line into IPython and fails. A management command has no such limit.
"""
import os
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed data (runs seed_full_demo.py from the project root)."

    def handle(self, *args, **options):
        # Never let an unprintable character kill the run on a legacy console.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass

        from django.conf import settings
        path = os.path.join(settings.BASE_DIR, "seed_full_demo.py")
        if not os.path.exists(path):
            self.stderr.write(f"Cannot find {path}")
            return

        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        exec(compile(source, path, "exec"), {"__name__": "__main__", "__file__": path})
