# Iqra University OBE Backend

Django REST Framework backend for the Outcome-Based Education (OBE) system.

---

## Setup after cloning

```bash
git clone https://github.com/ZeeshanAliMon/University-OBE-Backend.git
cd University-OBE-Backend
```

### 1. Create virtual environment

**Windows:**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run migrations

> ⚠️ Never run `makemigrations` on a fresh clone — migrations are already included.

```bash
python manage.py migrate
```

### 4. Create superuser (for Django Admin)

```bash
python manage.py createsuperuser
```

### 5. Seed the database

```bash
python manage.py seed
```

### 6. Start the server

```bash
python manage.py runserver
```

API available at `http://localhost:8000/api/`
Admin panel at `http://localhost:8000/admin/`

---

## Login credentials (after seeding)

| Username | Password | Role |
|---|---|---|
| `qa_computing` | `qapass123` | QA — Computing Dept |
| `qa_business` | `qapass123` | QA — Business Dept |
| `admission` | `admpass123` | Admission Officer |
| `dr_ali` | `instpass123` | Instructor |

---

## API Endpoints

### Auth
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login/` | None | Login → get JWT tokens |
| POST | `/api/auth/token/refresh/` | None | Refresh access token |

### QA — Departments
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/departments/` | Any | List all departments |
| GET | `/api/departments/<slug>/` | Any | Get one department |
| PATCH | `/api/departments/<slug>/` | QA only | Update vision / mission |

### QA — Programs
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/programs/` | Any | List all programs with POs |
| POST | `/api/programs/` | QA only | Create program |
| GET | `/api/programs/<slug>/` | Any | Get one program |
| PATCH | `/api/programs/<slug>/` | QA only | Update program / POs / GA mappings |

### QA — Graduate Attributes
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/gas/` | Any | List all GAs |

### QA — Courses
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/courses/` | Any | List all courses |
| POST | `/api/courses/` | QA only | Create course |
| GET | `/api/courses/<slug>/` | Any | Get one course |
| PATCH | `/api/courses/<slug>/` | QA only | Update GA mappings |

### Instructor
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/instructor/courses/` | Instructor | Get instructor's courses |
| POST | `/api/instructor/courses/` | Instructor | Save full course list (bulk upsert) |

### Admission — Students
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/students/` | Any | List all registered students |
| POST | `/api/students/` | Admission only | Register new student |
| PATCH | `/api/students/<reg_no>/` | Admission only | Update student record |
| DELETE | `/api/students/<reg_no>/` | Admission only | Delete student record |

---

## Reset database

Only needed when model changes are pulled:

```powershell
del db.sqlite3
del core\migrations\0*.py
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py seed
```

---

## Project structure

```
obe/
├── core/
│   ├── models.py          # All DB models
│   ├── serializers.py     # API serializers
│   ├── views.py           # API views
│   ├── urls.py            # URL routing
│   ├── permissions.py     # Role-based permissions (IsQA, IsInstructor, IsAdmission)
│   ├── admin.py           # Django admin
│   └── management/commands/seed.py
├── obe/
│   ├── settings.py
│   └── urls.py
└── requirements.txt
```

## Roles

| Role | Access |
|---|---|
| `qa` | Read all + write departments, programs, courses |
| `instructor` | Read all + manage own courses |
| `admission` | Read all + full CRUD on student registry |
| `dept_admin` | Read all (more features coming) |
| `student` | Coming soon |
| `admin` | Full access to everything |
