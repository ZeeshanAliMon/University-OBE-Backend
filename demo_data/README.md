# Test data

`obe_test_data.sqlite3` is made-up data for trying the system locally: 30 students in
batches FA22, SP23 and FA23, 4 teachers, 32 courses and 64 survey responses. All names and
marks are fake.

It is named this way so a `git pull` never touches a real `db.sqlite3`.
**Do not copy it over the live database.**

To use it on your own computer, keep a copy of your `db.sqlite3`, then in the backend folder:

    cp demo_data/obe_test_data.sqlite3 db.sqlite3
    python manage.py migrate

Password for every account: `test1234`

| Role | Email |
| --- | --- |
| Admission | admission@test.com |
| Department admin | computing@test.com |
| QA | qa@test.com |
| Teachers | teacher1@test.com to teacher4@test.com |
| Students | student1@test.com to student30@test.com |
