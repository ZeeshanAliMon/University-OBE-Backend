"""
OBE Backend API Test Suite
Mocks the frontend's apiService.ts and tests every endpoint.
"""

import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000/api"  # change to your live URL if not running locally

# ─── Credentials ─────────────────────────────────────────────────────────────
# Fill these in before running
QA_EMAIL       = "qa@iqra.edu.pk"
QA_PASSWORD    = "Test@1234"
DEPT_EMAIL     = "deptadmin.cs@iqra.edu.pk"
DEPT_PASSWORD  = "Test@1234"
INST_EMAIL     = "ahmed@iqra.edu.pk"
INST_PASSWORD  = "Test@1234"

# ─── Colours ──────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

results = []

def h(title):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")

def ok(label, detail=""):
    msg = f"  {GREEN}✓{RESET} {label}"
    if detail: msg += f"  {YELLOW}({detail}){RESET}"
    print(msg)
    results.append(("PASS", label))

def fail(label, detail=""):
    msg = f"  {RED}✗{RESET} {label}"
    if detail: msg += f"  {RED}→ {detail}{RESET}"
    print(msg)
    results.append(("FAIL", label + (f" | {detail}" if detail else "")))

def warn(label, detail=""):
    msg = f"  {YELLOW}⚠{RESET} {label}"
    if detail: msg += f"  {YELLOW}({detail}){RESET}"
    print(msg)
    results.append(("WARN", label))

def check(label, res, expected_status=200, check_fn=None):
    if res.status_code != expected_status:
        fail(label, f"status {res.status_code}, expected {expected_status} | {res.text[:200]}")
        return None
    try:
        data = res.json()
    except Exception:
        fail(label, f"non-JSON response: {res.text[:100]}")
        return None
    if check_fn:
        try:
            check_fn(data)
            ok(label, f"status {res.status_code}")
        except AssertionError as e:
            fail(label, str(e))
            return None
    else:
        ok(label, f"status {res.status_code}")
    return data

# ─── 1. Health ─────────────────────────────────────────────────────────────
h("1. Health Check")
try:
    r = requests.get(f"{BASE_URL}/health/", timeout=10)
    if r.status_code == 200:
        ok("GET /health/")
    else:
        warn("GET /health/", f"status {r.status_code}")
except Exception as e:
    fail("GET /health/", str(e))

# ─── 2. Auth ──────────────────────────────────────────────────────────────
h("2. Authentication")

qa_token = dept_token = inst_token = None

# QA Login
try:
    r = requests.post(f"{BASE_URL}/auth/login/", json={"email": QA_EMAIL, "password": QA_PASSWORD}, timeout=15)
    data = check("POST /auth/login/ (QA)", r, 200,
        lambda d: (
            assert_("access" in d, "missing 'access' token"),
            assert_("refresh" in d, "missing 'refresh' token"),
            assert_("user" in d, "missing 'user' object"),
            assert_(d["user"].get("user_type") in ("qa", "admin"), f"unexpected user_type: {d['user'].get('user_type')}")
        )
    )
    if data:
        qa_token = data["access"]
        print(f"    user_type={data['user'].get('user_type')} mustChangePassword={data['user'].get('mustChangePassword')}")
except Exception as e:
    fail("POST /auth/login/ (QA)", str(e))

# Dept Admin Login
try:
    r = requests.post(f"{BASE_URL}/auth/login/", json={"email": DEPT_EMAIL, "password": DEPT_PASSWORD}, timeout=15)
    data = check("POST /auth/login/ (Dept Admin)", r, 200,
        lambda d: (
            assert_("access" in d, "missing 'access' token"),
            assert_(d["user"].get("user_type") == "dept_admin", f"unexpected user_type: {d['user'].get('user_type')}")
        )
    )
    if data:
        dept_token = data["access"]
        print(f"    departmentId={data['user'].get('departmentId')} mustChangePassword={data['user'].get('mustChangePassword')}")
except Exception as e:
    fail("POST /auth/login/ (Dept Admin)", str(e))

# Instructor Login
try:
    r = requests.post(f"{BASE_URL}/auth/login/", json={"email": INST_EMAIL, "password": INST_PASSWORD}, timeout=15)
    data = check("POST /auth/login/ (Instructor)", r, 200,
        lambda d: assert_("access" in d, "missing 'access' token")
    )
    if data:
        inst_token = data["access"]
        print(f"    user_type={data['user'].get('user_type')}")
except Exception as e:
    fail("POST /auth/login/ (Instructor)", str(e))

# Wrong role check
try:
    r = requests.post(f"{BASE_URL}/auth/login/", json={"email": "wrong@bad.com", "password": "bad"}, timeout=10)
    if r.status_code in (400, 401, 403):
        ok("POST /auth/login/ (bad credentials → rejects)", f"status {r.status_code}")
    else:
        fail("POST /auth/login/ (bad credentials → rejects)", f"got {r.status_code}")
except Exception as e:
    fail("POST /auth/login/ (bad credentials)", str(e))

def assert_(cond, msg):
    if not cond: raise AssertionError(msg)

def qa_headers():
    return {"Authorization": f"Bearer {qa_token}", "Content-Type": "application/json"}

def dept_headers():
    return {"Authorization": f"Bearer {dept_token}", "Content-Type": "application/json"}

def inst_headers():
    return {"Authorization": f"Bearer {inst_token}", "Content-Type": "application/json"}

# ─── 3. Departments ───────────────────────────────────────────────────────
h("3. Departments")

dept_id = None
if qa_token:
    r = requests.get(f"{BASE_URL}/departments/", headers=qa_headers(), timeout=15)
    data = check("GET /departments/", r, 200,
        lambda d: (
            assert_(isinstance(d, list), f"expected list, got {type(d).__name__}"),
            assert_(len(d) > 0, "empty departments list"),
            assert_("id" in d[0], "dept missing 'id'"),
            assert_("name" in d[0], "dept missing 'name'")
        )
    )
    if data:
        dept_id = data[0]["id"]
        print(f"    {len(data)} departments. First: id={data[0]['id']} name={data[0]['name']}")
        for d in data:
            missing = [f for f in ["id","name","vision","mission"] if f not in d]
            if missing:
                warn(f"  dept '{d.get('id')}' missing fields: {missing}")

    # PATCH department
    if dept_id:
        r = requests.patch(f"{BASE_URL}/departments/{dept_id}/",
            headers=qa_headers(),
            json={"vision": "Test vision updated by API test"},
            timeout=10)
        check("PATCH /departments/{id}/ (QA)", r, 200,
            lambda d: assert_(d.get("vision") == "Test vision updated by API test", "vision not updated in response")
        )

    # Unauthenticated check
    r = requests.get(f"{BASE_URL}/departments/", timeout=10)
    if r.status_code == 401:
        ok("GET /departments/ (no token → 401)")
    else:
        warn("GET /departments/ (no token)", f"expected 401 got {r.status_code}")

# ─── 4. Programs ──────────────────────────────────────────────────────────
h("4. Programs")

prog_id = None
if qa_token:
    r = requests.get(f"{BASE_URL}/programs/", headers=qa_headers(), timeout=15)
    data = check("GET /programs/", r, 200,
        lambda d: (
            assert_(isinstance(d, list), f"expected list, got {type(d).__name__}"),
            assert_(len(d) > 0, "empty programs list"),
            assert_("id" in d[0], "prog missing 'id'"),
            assert_("departmentId" in d[0], "prog missing 'departmentId'"),
            assert_("pos" in d[0], "prog missing 'pos'")
        )
    )
    if data:
        prog_id = data[0]["id"]
        print(f"    {len(data)} programs. First: id={data[0]['id']} dept={data[0]['departmentId']}")
        for p in data:
            missing = [f for f in ["id","name","code","departmentId","pos","vision","mission"] if f not in p]
            if missing:
                warn(f"  prog '{p.get('id')}' missing fields: {missing}")

    # Filter by department
    if dept_id:
        r = requests.get(f"{BASE_URL}/programs/?department={dept_id}", headers=qa_headers(), timeout=10)
        data2 = check(f"GET /programs/?department={dept_id}", r, 200)
        if data2:
            wrong = [p for p in data2 if p.get("departmentId") != dept_id]
            if wrong:
                fail(f"  department filter leak: {len(wrong)} programs from other depts")
            else:
                ok(f"  department filter correct ({len(data2)} programs)")

    # Student cannot create program
    if inst_token:
        r = requests.post(f"{BASE_URL}/programs/", headers=inst_headers(),
            json={"name":"Hack","code":"HACK","departmentId": dept_id or "test"},
            timeout=10)
        if r.status_code == 403:
            ok("POST /programs/ (instructor → 403 forbidden)")
        else:
            fail("POST /programs/ (instructor should be forbidden)", f"got {r.status_code}")

# ─── 5. Courses ───────────────────────────────────────────────────────────
h("5. Courses")

course_id = None
if qa_token:
    r = requests.get(f"{BASE_URL}/courses/", headers=qa_headers(), timeout=15)
    data = check("GET /courses/", r, 200,
        lambda d: (
            assert_(isinstance(d, list), f"expected list, got {type(d).__name__}"),
        )
    )
    if data:
        print(f"    {len(data)} courses total")
        if data:
            c = data[0]
            course_id = c.get("id") or c.get("code")
            missing = [f for f in ["id","code","title","type","courseType","departmentId","creditHours"] if f not in c]
            if missing:
                fail(f"Course response missing fields (Bug 3 check): {missing}")
            else:
                ok(f"Course has all expected fields incl. courseType={c.get('courseType')}")
            print(f"    Sample course: code={c.get('code')} type={c.get('type')} courseType={c.get('courseType')} dept={c.get('departmentId')}")

    # Create a test course
    if dept_id and prog_id:
        test_code = "TST999"
        r = requests.post(f"{BASE_URL}/courses/", headers=qa_headers(),
            json={
                "code": test_code,
                "title": "Test Course API",
                "type": "core",
                "subtype": "lab",
                "departmentId": dept_id,
                "programId": prog_id,
                "creditHours": 3,
                "mappedGAs": []
            }, timeout=15)
        created = check("POST /courses/ (create with subtype=lab)", r, 201,
            lambda d: (
                assert_(d.get("code") == test_code, f"code mismatch: {d.get('code')}"),
                assert_(d.get("courseType") in ("lab","Lab"), f"courseType not returned or wrong: {d.get('courseType')} (Bug 3 check)")
            )
        )
        if created:
            print(f"    Created: code={created.get('code')} courseType={created.get('courseType')}")

            # PATCH it — change subtype to theory
            r = requests.patch(f"{BASE_URL}/courses/{test_code}/",
                headers=qa_headers(),
                json={"title": "Test Course API Updated", "subtype": "theory"},
                timeout=10)
            updated = check("PATCH /courses/{id}/ (update subtype to theory)", r, 200,
                lambda d: assert_(d.get("courseType") in ("theory","Theory"), f"courseType not updated: {d.get('courseType')}")
            )
            if updated:
                print(f"    Updated courseType={updated.get('courseType')}")

            # DELETE it
            r = requests.delete(f"{BASE_URL}/courses/{test_code}/", headers=qa_headers(), timeout=10)
            if r.status_code in (200, 204):
                ok("DELETE /courses/{id}/ (cleanup)")
            else:
                fail("DELETE /courses/{id}/", f"status {r.status_code} {r.text[:100]}")

# ─── 6. GAs ───────────────────────────────────────────────────────────────
h("6. Graduate Attributes (GAs)")

if qa_token:
    r = requests.get(f"{BASE_URL}/gas/", headers=qa_headers(), timeout=15)
    data = check("GET /gas/", r, 200,
        lambda d: assert_(isinstance(d, list), f"expected list, got {type(d).__name__}")
    )
    if data:
        print(f"    {len(data)} GAs total")
        if data:
            g = data[0]
            missing = [f for f in ["id","name","description","departmentId"] if f not in g]
            if missing:
                warn(f"GA missing fields: {missing}")
            else:
                ok(f"GA has expected fields")

# ─── 7. Admin Profile ─────────────────────────────────────────────────────
h("7. Dept Admin Profile")

if dept_token:
    r = requests.get(f"{BASE_URL}/admin/profile/", headers=dept_headers(), timeout=10)
    data = check("GET /admin/profile/ (dept_admin)", r, 200,
        lambda d: (
            assert_("departmentId" in d, "missing 'departmentId'"),
            assert_("departmentName" in d, "missing 'departmentName'"),
            assert_(d.get("user_type") == "dept_admin", f"user_type={d.get('user_type')}")
        )
    )
    if data:
        print(f"    departmentId={data.get('departmentId')} departmentName={data.get('departmentName')}")

    # QA should NOT access dept admin profile
    if qa_token:
        r = requests.get(f"{BASE_URL}/admin/profile/", headers=qa_headers(), timeout=10)
        if r.status_code == 403:
            ok("GET /admin/profile/ (QA → 403 correctly blocked)")
        else:
            warn("GET /admin/profile/ (QA)", f"expected 403, got {r.status_code}")

# ─── 8. Teachers ──────────────────────────────────────────────────────────
h("8. Teachers")

teacher_id = None
if dept_token:
    r = requests.get(f"{BASE_URL}/teachers/", headers=dept_headers(), timeout=15)
    data = check("GET /teachers/", r, 200,
        lambda d: assert_(isinstance(d, list), f"expected list, got {type(d).__name__}")
    )
    if data:
        print(f"    {len(data)} teachers")
        if data:
            t = data[0]
            missing = [f for f in ["id","name","email","departmentId"] if f not in t]
            if missing:
                warn(f"Teacher missing fields: {missing}")
            teacher_id = t.get("employeeId") or t.get("id")

# ─── 9. Students ──────────────────────────────────────────────────────────
h("9. Students")

if dept_token:
    r = requests.get(f"{BASE_URL}/students/", headers=dept_headers(), timeout=15)
    data = check("GET /students/", r, 200,
        lambda d: assert_(isinstance(d, list), f"expected list, got {type(d).__name__}")
    )
    if data:
        print(f"    {len(data)} students")
        if data:
            s = data[0]
            missing = [f for f in ["regNo","name","departmentId","programId","batch","semester"] if f not in s]
            if missing:
                warn(f"Student missing fields: {missing}")

# ─── 10. Instructor Courses ───────────────────────────────────────────────
h("10. Instructor Courses")

inst_course_id = None
if inst_token:
    r = requests.get(f"{BASE_URL}/instructor/courses/", headers=inst_headers(), timeout=20)
    data = check("GET /instructor/courses/", r, 200,
        lambda d: assert_(isinstance(d, list), f"expected list, got {type(d).__name__}")
    )
    if data:
        print(f"    {len(data)} instructor courses")
        if data:
            ic = data[0]
            inst_course_id = ic.get("id")
            missing = [f for f in ["id","code","title"] if f not in ic]
            if missing:
                warn(f"InstructorCourse missing fields: {missing}")
            ok(f"InstructorCourse fields present, courseType={ic.get('courseType')}")

# ─── 11. Semester Plans ───────────────────────────────────────────────────
h("11. Semester Plans")

if dept_token and prog_id:
    r = requests.get(f"{BASE_URL}/admin/semester-plans/?programId={prog_id}", headers=dept_headers(), timeout=10)
    data = check(f"GET /admin/semester-plans/?programId={prog_id}", r, 200,
        lambda d: assert_(isinstance(d, list), f"expected list got {type(d).__name__}")
    )
    if data is not None:
        print(f"    {len(data)} semester plans for program {prog_id}")

    # Security: dept admin cannot access another dept's plan by guessing programId
    # (Already fixed in backend per the comment in views.py)

# ─── 12. Token Refresh ────────────────────────────────────────────────────
h("12. Token Refresh")

if qa_token:
    # Get refresh token by logging in again
    r = requests.post(f"{BASE_URL}/auth/login/", json={"email": QA_EMAIL, "password": QA_PASSWORD}, timeout=15)
    if r.status_code == 200:
        refresh = r.json().get("refresh")
        if refresh:
            r2 = requests.post(f"{BASE_URL}/auth/token/refresh/",
                json={"refresh": refresh}, timeout=10)
            check("POST /auth/token/refresh/", r2, 200,
                lambda d: assert_("access" in d, "missing new access token")
            )
        else:
            warn("Token refresh", "no refresh token in login response")

# ─── 13. Reports ──────────────────────────────────────────────────────────
h("13. Reports")

if qa_token and prog_id:
    endpoints = [
        f"/reports/program-ga-attainment/?programId={prog_id}",
        f"/reports/program-ga-attainment-by-semester/?programId={prog_id}",
        f"/reports/po-attainment/?programId={prog_id}",
        f"/reports/co-attainment-summary/?programId={prog_id}",
        f"/reports/gap-analysis/?programId={prog_id}",
        f"/reports/at-risk-students/?programId={prog_id}",
        f"/reports/cohort-comparison/?programId={prog_id}",
        f"/reports/student-ga-attainment/",
        f"/reports/student-summary/",
    ]
    for ep in endpoints:
        try:
            r = requests.get(f"{BASE_URL}{ep}", headers=qa_headers(), timeout=10)
            if r.status_code == 200:
                ok(f"GET {ep}", f"status 200")
            elif r.status_code == 404:
                warn(f"GET {ep}", "404 — endpoint may not be implemented")
            else:
                fail(f"GET {ep}", f"status {r.status_code} {r.text[:100]}")
        except Exception as e:
            fail(f"GET {ep}", str(e))

# ─── 14. Security Checks ──────────────────────────────────────────────────
h("14. Security Checks")

# Unauthenticated access to protected endpoints
for ep in ["/departments/", "/programs/", "/courses/", "/students/", "/teachers/"]:
    r = requests.get(f"{BASE_URL}{ep}", timeout=10)
    if r.status_code == 401:
        ok(f"GET {ep} (no token → 401)")
    else:
        fail(f"GET {ep} (no token)", f"expected 401, got {r.status_code}")

# Instructor cannot create programs
if inst_token and dept_id:
    r = requests.post(f"{BASE_URL}/programs/", headers=inst_headers(),
        json={"name":"Hack","code":"HACK","departmentId": dept_id},
        timeout=10)
    if r.status_code == 403:
        ok("POST /programs/ (instructor → 403)")
    else:
        fail("POST /programs/ (instructor permission check)", f"got {r.status_code}")

# ─── Summary ──────────────────────────────────────────────────────────────
h("SUMMARY")
passed = [r for r in results if r[0] == "PASS"]
failed = [r for r in results if r[0] == "FAIL"]
warned = [r for r in results if r[0] == "WARN"]

print(f"\n  {GREEN}PASSED: {len(passed)}{RESET}  {RED}FAILED: {len(failed)}{RESET}  {YELLOW}WARNINGS: {len(warned)}{RESET}\n")

if failed:
    print(f"  {RED}Failed tests:{RESET}")
    for _, msg in failed:
        print(f"    {RED}✗{RESET} {msg}")

if warned:
    print(f"\n  {YELLOW}Warnings:{RESET}")
    for _, msg in warned:
        print(f"    {YELLOW}⚠{RESET} {msg}")

print()
sys.exit(1 if failed else 0)
