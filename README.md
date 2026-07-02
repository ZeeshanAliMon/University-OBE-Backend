# Iqra University OBE Backend

Django REST Framework backend for the Outcome-Based Education system.

## Setup (first time or after a fresh clone)

```bash
git clone https://github.com/ZeeshanAliMon/University-OBE-Backend.git
cd University-OBE-Backend
bash setup.sh
python manage.py runserver
```

`setup.sh` installs dependencies, runs migrations, and seeds the database.

## After pulling changes

```bash
git pull
python manage.py migrate   # only if new migration files exist
python manage.py seed      # only if you want to reset all data
python manage.py runserver
```

## Login — use email address

All users log in with their **email** and password.

| Email | Password | Role |
|---|---|---|
| `qa.computing@iqra.edu.pk` | `qapass123` | QA — Computing |
| `qa.business@iqra.edu.pk` | `qapass123` | QA — Business |
| `qa.eng@iqra.edu.pk` | `qapass123` | QA — Engineering |
| `admission@iqra.edu.pk` | `admpass123` | Admission Officer |
| `admin.computing@iqra.edu.pk` | `adminpass123` | Dept Admin (Computing) |
| `admin.business@iqra.edu.pk` | `adminpass123` | Dept Admin (Business) |
| `admin.engineering@iqra.edu.pk` | `adminpass123` | Dept Admin (Engineering) |
| `ali.hassan@iqra.edu.pk` | `instpass123` | Instructor |
| `ahmed.raza@student.iqra.edu.pk` | `stupass123` | Student (FA22-BSCS-0012) |
| `zara.siddiqui@student.iqra.edu.pk` | `stupass123` | Student (FA22-BSCS-0045) |
| `hamza.tariq@student.iqra.edu.pk` | `stupass123` | Student (FA22-BSSE-0011) |
| `zeeshan@iqra.edu.pk` | `zeeshan` | Superuser → `/admin/` |

## When model changes are made

```bash
python manage.py makemigrations core --name="describe_what_changed"
python manage.py migrate
python manage.py seed
```

Commit the new migration file. Never delete old ones.

## Base URL

`http://localhost:8000/api`

## ⚠️ Before deploying to production — do NOT skip this

These are all deliberately left in a "dev-friendly, not production-safe" state
right now, since the project is still in active development. Every item below
has a comment marking it in the actual code — this section is just the
checklist so nothing gets forgotten on deployment day.

- [ ] **Rotate `SECRET_KEY`.** It's currently read from the `DJANGO_SECRET_KEY`
      env var, falling back to a hardcoded dev value in `obe/settings.py` if
      the env var isn't set. That fallback value has been committed to this
      **public** repo since early in the project, so it must be treated as
      permanently compromised — generate a new one and set it as an actual
      environment variable on the production host, never in code:
      ```bash
      python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
      ```

- [ ] **Set `DJANGO_DEBUG=False` in the production environment** (it already
      defaults to `False` if the env var is unset, but confirm nothing in the
      deploy sets it back to `True`). Leaving `DEBUG=True` in production means
      any unhandled error shows a full stack trace, local variables, and
      settings to whoever triggered it — no login required.

- [ ] **Narrow `ALLOWED_HOSTS`** in `obe/settings.py` from `["*"]` to the real
      production hostname (e.g. `yourapp.pythonanywhere.com`).

- [ ] **Narrow CORS.** `CORS_ALLOW_ALL_ORIGINS` already defaults to `False`
      (env-overridable via `CORS_ALLOW_ALL_ORIGINS=True` if ever needed as a
      stopgap), but `CORS_ALLOWED_ORIGINS` in `obe/settings.py` currently only
      lists localhost + dev tunnel domains. Add the real deployed frontend
      domain before going live, or every request from it will fail CORS.

- [ ] **Remove/rotate the personal dev credentials in
      `core/management/commands/seed.py`** (e.g. `zeeshan@ali.com`,
      `mon@admin.com` and similar accounts with known passwords). Confirm this
      command is never run against the production database — these exist
      purely for local dev/demo convenience.

- [ ] **Set `DEFAULT_TEMP_PASSWORD` via env var** rather than relying on the
      hardcoded fallback in `obe/settings.py`, and rotate it periodically —
      it's the shared temporary password issued to every newly provisioned
      student/instructor account (enforced with `must_change_password=True`,
      but the temp password itself shouldn't stay static forever).

