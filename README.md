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
