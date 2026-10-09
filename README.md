# IS 4420 – SQL Midterm Study Tool & SQL Lab

A database-course study app with ~170 practice questions and a built-in SQL lab. One self-contained file; Python 3.8+ (Tkinter and SQLite ship with Python).

## Features
- Questions organized by study-guide week, or a mixed full practice exam
- Every SQL answer choice is verified by actually running the query
- **SQL Lab (F2):** run SELECT queries on a sample database, read queries in plain English, and **step through clause by clause** (FROM → WHERE → GROUP BY → HAVING → SELECT → DISTINCT → ORDER BY) to see the rows at each stage
- Study reference (SELECT pattern, WHERE vs HAVING, LIKE, aggregates, keys), SQL syntax highlighting, light/dark mode

## Run it
```bash
python IS4420_Midterm_Study_Tool.py
```
Safe by design: in-memory read-only SQLite, SELECT-only, 3-second query timeout, no network or file access.
