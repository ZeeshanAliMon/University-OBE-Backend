# Iqra University OBE Backend

Django REST Framework backend for the Outcome-Based Education system.

## Setup (first time or after a fresh clone)

```bash
git clone https://github.com/ZeeshanAliMon/University-OBE-Backend.git
cd University-OBE-Backend
bash setup.sh
python manage.py runserver
```

That's it. `setup.sh` installs dependencies, runs migrations, and seeds the database.

## After pulling changes from git

```bash
git pull
python manage.py migrate   # only needed if there are new migration files
python manage.py seed      # resets all data — run if models changed
python manage.py runserver
```

If there are **no new migration files** after a pull, just `runserver` directly.

## Login credentials (after seed)

| Username | Password | Role |
|---|---|---|
| `qa_computing` | `qapass123` | QA — Computing |
| `qa_business` | `qapass123` | QA — Business |
| `qa_engineering` | `qapass123` | QA — Engineering |
| `admission` | `admpass123` | Admission Officer |
| `admin_computing` | `adminpass123` | Dept Admin (Computing) |
| `dr_ali` | `instpass123` | Instructor |
| `ahmed_cs` | `stupass123` | Student (FA22-BSCS-0012) |
| `zara_cs` | `stupass123` | Student (FA22-BSCS-0045) |
| `hamza_se` | `stupass123` | Student (FA22-BSSE-0011) |
| `zeeshan` | `zeeshan` | Superuser → `/admin/` |

## When model changes are made

```bash
python manage.py makemigrations core --name="describe_what_changed"
python manage.py migrate
python manage.py seed
```

Commit the new migration file. Never delete old migration files — just add new ones on top.

## Base URL

`http://localhost:8000/api`
