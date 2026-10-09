#!/usr/bin/env python3
"""
IS 4420 - Midterm Practice Exam & SQL Lab
=========================================
One self-contained file. Needs only Python 3.8+ (tkinter and sqlite3 ship with Python).

    python IS4420_Midterm_Study_Tool.py

What it is
  * ~170 practice questions organized by the midterm study guide (Weeks 1-6 + data types and
    query interpretation), or a mixed "full practice exam".
  * Every SQL question is checked by actually running the query: answer choices that show
    results are the real output of real queries.
  * SQL LAB (press F2 in any question): run SELECT queries against a sample database, read a
    query in plain English, and STEP THROUGH it clause by clause (FROM -> WHERE -> GROUP BY ->
    HAVING -> SELECT -> DISTINCT -> ORDER BY) to see the rows after every step.
  * Study Reference (the SELECT pattern, WHERE vs HAVING, LIKE, aggregates, keys, ...),
    colored SQL, and a light / dark mode button.

Safety notes
  * Everything runs locally: no network access, no files are read or written.
  * The SQL Lab uses a private in-memory SQLite database that is read-only: only SELECT is
    allowed (INSERT/UPDATE/DROP/PRAGMA/ATTACH are refused) and a query is stopped after 3 seconds.
  * Concept questions use standard textbook wording; always double-check terms against your
    lecture slides. SQL runs on SQLite; the course uses MySQL, and these query types behave the same.
"""
import sys
try:
    import sqlite3  # noqa: F401
except ImportError:
    print("This Python was built without sqlite3, which the SQL Lab needs. Install Python from python.org.")
    sys.exit(1)
import os

import random
import re
import sqlite3
import time

# ===========================================================================
# Sample database (what every SQL question and the SQL Lab run against)
# ===========================================================================
SCHEMAS = {
    "employees": [("emp_id", "INT"), ("first_name", "VARCHAR"), ("last_name", "VARCHAR"),
                  ("department", "VARCHAR"), ("job_title", "VARCHAR"), ("salary", "DECIMAL"),
                  ("bonus", "DECIMAL"), ("hire_date", "DATE")],
    "products": [("product_id", "INT"), ("product_name", "VARCHAR"), ("category", "VARCHAR"),
                 ("price", "DECIMAL"), ("stock", "INT")],
    "orders": [("order_id", "INT"), ("customer_name", "VARCHAR"), ("order_date", "DATE"),
               ("total", "DECIMAL"), ("status", "VARCHAR")],
}
SQLITE_TYPES = {"INT": "INTEGER", "VARCHAR": "TEXT", "DATE": "TEXT", "DECIMAL": "REAL"}
DATA = {
    "employees": [
        (1, "Alice", "Nguyen", "Sales", "Sales Rep", 52000, 2500, "2019-03-15"),
        (2, "Brian", "Carter", "Sales", "Sales Manager", 78000, 6000, "2016-07-01"),
        (3, "Carla", "Diaz", "IT", "Developer", 91000, 4000, "2018-01-20"),
        (4, "David", "Kim", "IT", "Analyst", 67000, None, "2020-09-08"),
        (5, "Elena", "Rossi", "HR", "HR Specialist", 58000, None, "2017-05-12"),
        (6, "Frank", "Moore", "Sales", "Sales Rep", 49000, None, "2021-02-01"),
        (7, "Grace", "Lee", "IT", "Developer", 95000, 5000, "2015-11-30"),
        (8, "Henry", "Patel", "HR", "HR Manager", 72000, 3000, "2014-06-18"),
        (9, "Isabel", "Torres", "Finance", "Accountant", 64000, None, "2019-08-25"),
        (10, "Jack", "Brown", "Finance", "Analyst", 61000, None, "2022-04-04"),
        (11, "Karen", "White", "Sales", "Sales Rep", 52000, None, "2022-10-10"),
        (12, "Liam", "Scott", "IT", "Analyst", 67000, None, "2023-01-16"),
    ],
    "products": [
        (1, "Laptop", "Electronics", 899.99, 15), (2, "Mouse", "Electronics", 19.99, 120),
        (3, "Keyboard", "Electronics", 49.99, 80), (4, "Monitor", "Electronics", 249.50, 25),
        (5, "Desk", "Furniture", 199.00, 10), (6, "Office Chair", "Furniture", 149.00, 18),
        (7, "Bookshelf", "Furniture", 89.00, 0), (8, "Notebook", "Stationery", 3.99, 300),
        (9, "Pen Pack", "Stationery", 5.49, 250), (10, "Stapler", "Stationery", 8.99, 60),
        (11, "USB Cable", "Electronics", 9.99, 200), (12, "Whiteboard", "Furniture", 75.00, 12),
    ],
    "orders": [
        (1, "Smith", "2024-01-05", 120.00, "Shipped"), (2, "Jones", "2024-01-07", 75.50, "Shipped"),
        (3, "Smith", "2024-01-15", 300.00, "Pending"), (4, "Garcia", "2024-02-02", 45.00, "Shipped"),
        (5, "Lee", "2024-02-10", 210.00, "Cancelled"), (6, "Jones", "2024-02-14", 99.99, "Shipped"),
        (7, "Smith", "2024-03-01", 150.00, "Shipped"), (8, "Patel", "2024-03-05", 600.00, "Shipped"),
        (9, "Garcia", "2024-03-18", 80.00, "Pending"), (10, "Lee", "2024-03-20", 35.00, "Shipped"),
        (11, "Patel", "2024-04-02", 250.00, "Cancelled"), (12, "Smith", "2024-04-11", 60.00, "Shipped"),
    ],
}


def fmt(v):
    """How a value is shown in a result grid (DECIMAL-style: two places)."""
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


class SqlError(Exception):
    pass


HINTS = [
    ("misuse of aggregate", "Aggregate functions like COUNT() or SUM() can't be used in WHERE. "
                            "Filter groups with HAVING (after GROUP BY) instead."),
    ("no such table", "That table doesn't exist. Tables here: employees, products, orders."),
    ("no such column", "That column doesn't exist in the table. Check the spelling in the table browser."),
    ("syntax error", "Syntax error. Clauses must be written in this order: SELECT, FROM, WHERE, "
                     "GROUP BY, HAVING, ORDER BY."),
    ("interrupted", "That query ran too long and was stopped."),
    ("not authorized", "Only SELECT queries are allowed in this tool."),
    ("one statement", "Only one statement at a time, please."),
]


def friendly(e):
    msg = str(e)
    for needle, hint in HINTS:
        if needle in msg.lower():
            return f"{msg}\n\nHint: {hint}"
    return msg


class Sandbox:
    """In-memory, read-only SQLite database. Only SELECT is allowed, and a query is stopped after 3 s."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        for name, cols in SCHEMAS.items():
            decl = ", ".join(f"{c} {SQLITE_TYPES[t]}" for c, t in cols)
            self.conn.execute(f"CREATE TABLE {name} ({decl})")
            marks = ", ".join("?" * len(cols))
            self.conn.executemany(f"INSERT INTO {name} VALUES ({marks})", DATA[name])
        self.conn.commit()
        self.conn.execute("PRAGMA query_only = ON")
        self.deadline = 0.0
        self.conn.set_authorizer(self._auth)
        self.conn.set_progress_handler(self._tick, 2000)

    @staticmethod
    def _auth(action, a, b, db, source):
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        if hasattr(sqlite3, "SQLITE_RECURSIVE"):
            allowed.add(sqlite3.SQLITE_RECURSIVE)
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    def _tick(self):
        return 1 if time.monotonic() > self.deadline else 0

    def run(self, sql, limit=500):
        """-> (columns, rows, truncated). Raises SqlError with a friendly message."""
        sql = (sql or "").strip().rstrip(";").strip()
        if not sql:
            raise SqlError("Type a query first.")
        self.deadline = time.monotonic() + 3.0
        try:
            cur = self.conn.execute(sql)
            if cur.description is None:
                raise SqlError("Only SELECT queries are allowed in this tool.")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(limit + 1)
        except SqlError:
            raise
        except Exception as e:  # sqlite3.Error, sqlite3.Warning, ...
            raise SqlError(friendly(e))
        return cols, [tuple(r) for r in rows[:limit]], len(rows) > limit

    def table_rows(self, name):
        return self.run(f"SELECT * FROM {name}", limit=100)


# ===========================================================================
# Reading a query: clause splitter, plain-English reading, and step-by-step stages
# ===========================================================================
KW_RE = re.compile(r"(SELECT|FROM|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT)\b", re.I)
ORDER = ["SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT"]
AGG_RE = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", re.I)


def parse_select(sql):
    """Split a single SELECT into clauses. -> dict or None. Each clause: (text, start, end)."""
    n, i, depth, marks = len(sql), 0, 0, []
    while i < n:
        ch = sql[i]
        if ch in "'\"`":
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            continue
        if ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] == "_")):
            m = KW_RE.match(sql, i)
            if m:
                marks.append((re.sub(r"\s+", " ", m.group(1).upper()), i, m.end()))
                i = m.end()
                continue
        i += 1
    names = [m[0] for m in marks]
    if (not marks or names[0] != "SELECT" or sql[:marks[0][1]].strip()
            or len(set(names)) != len(names) or [ORDER.index(x) for x in names] != sorted(ORDER.index(x) for x in names)):
        return None
    out = {}
    for k, (name, ks, ce) in enumerate(marks):
        end = marks[k + 1][1] if k + 1 < len(marks) else n
        raw = sql[ce:end]
        start = ce + len(raw) - len(raw.lstrip())
        text = raw.strip()
        out[name] = (text, start, start + len(text))
    text, start, end = out["SELECT"]
    m = re.match(r"DISTINCT\b\s*", text, re.I)
    out["DISTINCT"] = (m.group(0).strip(), start, start + len(m.group(0).strip())) if m else None
    if m:
        out["SELECT"] = (text[m.end():], start + m.end(), end)
    return out


def split_commas(text):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def read_query(sb, sql):
    """Plain-English reading of a query (the 'what table, what columns, what conditions...' list)."""
    p = parse_select(sql)
    if not p or "FROM" not in p:
        return [("Can't read this one", "Only a single SELECT ... FROM ... query can be broken down here "
                                        "(the clauses must also be in the standard order).")]
    out = [("Table(s) used", p["FROM"][0])]
    sel = p["SELECT"][0]
    items = split_commas(sel)
    what = "ALL columns (*)" if sel.strip() == "*" else ", ".join(items)
    if p["DISTINCT"]:
        what += "   (DISTINCT: duplicate rows are removed)"
    out.append(("Selected (columns / expressions)", what))
    out.append(("Rows kept by WHERE", p["WHERE"][0] if "WHERE" in p else "none - every row is used"))
    if "GROUP BY" in p:
        out.append(("Grouped by", p["GROUP BY"][0] + "   (one result row per group)"))
    elif AGG_RE.search(sel):
        out.append(("Aggregation", "no GROUP BY, so the aggregate function(s) summarize ALL remaining rows into ONE row"))
    if "HAVING" in p:
        out.append(("Groups kept by HAVING", p["HAVING"][0]))
    if "ORDER BY" in p:
        items = split_commas(p["ORDER BY"][0])
        desc = []
        for it in items:
            up = it.upper()
            desc.append(it.rsplit(None, 1)[0] + " (highest to lowest / Z to A)" if up.endswith(" DESC") else
                        (it.rsplit(None, 1)[0] if up.endswith(" ASC") else it) + " (lowest to highest / A to Z)")
        out.append(("Sorted by", ", ".join(desc)))
    else:
        out.append(("Sorted by", "nothing specified - the order isn't guaranteed"))
    try:
        cols, rows, _ = sb.run(sql)
        out.append(("Result set shape", f"{len(cols)} column(s) x {len(rows)} row(s):  " + ", ".join(cols)))
    except SqlError as e:
        out.append(("Result set", "the query fails:  " + str(e).split("\n")[0]))
    return out


def plan_stages(sb, sql):
    """Run the query clause by clause in SQL's logical order. -> list of stage dicts, or None."""
    p = parse_select(sql)
    if not p or "FROM" not in p:
        return None
    f = p["FROM"][0]
    sel = p["SELECT"][0]
    w, g, h, o = (p[k][0] if k in p else None for k in ("WHERE", "GROUP BY", "HAVING", "ORDER BY"))
    lim = p["LIMIT"][0] if "LIMIT" in p else None
    where = f" WHERE {w}" if w else ""
    stages = []

    def add(title, text, q, clause):
        try:
            cols, rows, trunc = sb.run(q)
            err = None
        except SqlError as e:
            cols, rows, trunc, err = [], [], False, str(e)
        stages.append({"title": title, "text": text, "cols": cols, "rows": rows, "error": err,
                       "span": p[clause][1:] if p.get(clause) else None, "n": len(rows)})
        return len(rows)

    n_from = add("FROM", "SQL starts with the table named in FROM: every row and every column.",
                 f"SELECT * FROM {f}", "FROM")
    prev = n_from
    if w:
        k = add("WHERE", f"WHERE filters ROWS. Only rows where  {w}  is true are kept.",
                f"SELECT * FROM {f}{where}", "WHERE")
        stages[-1]["text"] += f"  ({k} of {prev} rows kept)"
        prev = k
    if g:
        k = add("GROUP BY", f"GROUP BY gathers rows that share the same {g} into groups. Each row below is "
                            f"one group; rows_in_group is how many rows fell into it.",
                f"SELECT {g}, COUNT(*) AS rows_in_group FROM {f}{where} GROUP BY {g} ORDER BY {g}", "GROUP BY")
        stages[-1]["text"] += f"  ({prev} rows -> {k} groups)"
        prev = k
        if h:
            k = add("HAVING", f"HAVING filters GROUPS (after grouping, so it can use aggregates). Only groups where  "
                              f"{h}  is true are kept.",
                    f"SELECT {g}, COUNT(*) AS rows_in_group FROM {f}{where} GROUP BY {g} HAVING {h} ORDER BY {g}", "HAVING")
            stages[-1]["text"] += f"  ({k} of {prev} groups kept)"
            prev = k
    elif AGG_RE.search(sel):
        pass
    tail = f"FROM {f}{where}" + (f" GROUP BY {g}" if g else "") + (f" HAVING {h}" if h else "")
    if g:
        text = f"SELECT now builds the output columns for each remaining group: {sel}. Aggregate functions turn each group into one value."
    elif AGG_RE.search(sel):
        text = (f"There's no GROUP BY, so the aggregate function(s) in  {sel}  collapse ALL remaining rows into a "
                f"single result row.")
    else:
        text = f"SELECT picks which columns / expressions to show: {sel}  (this is where columns are filtered)."
    k = add("SELECT", text, f"SELECT {sel} {tail}", "SELECT")
    prev = k
    if p["DISTINCT"]:
        k = add("DISTINCT", "DISTINCT removes duplicate rows from the result.",
                f"SELECT DISTINCT {sel} {tail}", "DISTINCT")
        stages[-1]["text"] += f"  ({prev} rows -> {k} rows)"
        prev = k
    dist = "DISTINCT " if p["DISTINCT"] else ""
    if o:
        add("ORDER BY", f"ORDER BY sorts the final result set by  {o}.  It always runs last (before LIMIT), "
                        f"so it can sort by any column or alias.",
            f"SELECT {dist}{sel} {tail} ORDER BY {o}", "ORDER BY")
    if lim:
        add("LIMIT", f"LIMIT keeps only the first {lim} row(s) of the sorted result.",
            f"SELECT {dist}{sel} {tail}" + (f" ORDER BY {o}" if o else "") + f" LIMIT {lim}", "LIMIT")
    for i, s in enumerate(stages, 1):
        s["step"], s["of"] = i, len(stages)
    return stages


# ===========================================================================
# Question bank
# ===========================================================================
TOPICS = {
    "W1": "Week 1: Computing",
    "W2": "Week 2: Databases as Socio-Technical Systems",
    "W3": "Week 3: Business Requirements & Rules",
    "W4": "Week 4: Theories (Set & Relational)",
    "W5": "Week 5: SQL Intro",
    "W6": "Week 6: SQL Coding II",
    "AG": "Additional: Data Types & Query Interpretation",
}
PRACTICE_QUOTA = {"W1": 4, "W2": 3, "W3": 5, "W4": 7, "W5": 9, "W6": 7, "AG": 5}

BANK = []
BUILD_ERRORS = []
_DB = None


def db():
    global _DB
    if _DB is None:
        _DB = Sandbox()
    return _DB


def add(topic, prompt, correct, wrong, why, **kw):
    BANK.append({"topic": topic, "prompt": prompt, "choices": [correct] + list(wrong), "answer": [correct],
                 "why": why, "sql": kw.get("sql"), "code": kw.get("code"), "tables": kw.get("tables"),
                 "grid": kw.get("grid"), "mono": kw.get("mono", False),
                 "choice_sql": kw.get("choice_sql", False), "kind": kw.get("kind", "concept")})


def sq(sel, frm, where=None, group=None, having=None, order=None):
    lines = [f"SELECT {sel}", f"FROM {frm}"]
    for kw, val in (("WHERE", where), ("GROUP BY", group), ("HAVING", having), ("ORDER BY", order)):
        if val:
            lines.append(f"{kw} {val}")
    return "\n".join(lines)


def result_text(sql, header=True):
    cols, rows, _ = db().run(sql)
    if not rows:
        return "(no rows returned)"
    if len(cols) == 1 and len(rows) == 1 and not header:
        return fmt(rows[0][0])
    lines = [" | ".join(cols)] if header else []
    lines += [" | ".join(fmt(v) for v in r) for r in rows]
    return "\n".join(lines)


def outcome(sql):
    """Result text, or a marker for a query that errors (used for wrong-answer choices)."""
    try:
        return result_text(sql)
    except SqlError:
        return "ERROR"


def guard(fn):
    def wrapper(*a, **k):
        try:
            fn(*a, **k)
        except Exception as e:  # a bad question must never stop the app from starting
            BUILD_ERRORS.append(f"{fn.__name__}{a[:2]}: {e}")
    return wrapper


@guard
def q_result(topic, intro, sql, wrongs, why, tables, scalar=False):
    """'What does this query return?' - every choice is the real output of a query."""
    correct = result_text(sql, header=not scalar)
    seen = {correct}
    wrong = []
    for w in wrongs:
        try:
            t = result_text(w, header=not scalar)
        except SqlError:
            t = "The query fails with an error"
        if t in seen:
            raise ValueError("duplicate choice: " + t)
        seen.add(t)
        wrong.append(t)
    add(topic, intro, correct, wrong, why + "\n\nActual result set:\n" + result_text(sql),
        code=sql, sql=sql, tables=tables, mono=True, kind="sql_result")


@guard
def q_rows(topic, intro, sql, other_counts, why, tables):
    n = len(db().run(sql)[1])
    wrong = []
    for c in other_counts:
        if str(c) == str(n) or str(c) in wrong:
            raise ValueError("duplicate count")
        wrong.append(str(c))
    add(topic, intro, str(n), wrong, why, code=sql, sql=sql, tables=tables, kind="sql_rows")


@guard
def q_which(topic, intro, correct_sql, wrong_sqls, why, tables):
    """A result set is shown; pick the query that produced it."""
    cols, rows, _ = db().run(correct_sql)
    for w in wrong_sqls:
        try:
            wc, wr, _ = db().run(w)
            if (wc, wr) == (cols, rows):
                raise ValueError("a wrong query produces the same result set")
        except SqlError:
            pass
    add(topic, intro, correct_sql, wrong_sqls, why, sql=correct_sql, tables=tables, grid=(cols, rows),
        mono=True, choice_sql=True, kind="sql_which")


@guard
def q_english(topic, english, correct_sql, wrong_sqls, why, tables):
    cols, rows, _ = db().run(correct_sql)
    for w in wrong_sqls:
        try:
            wc, wr, _ = db().run(w)
            if rows == wr and [c.lower() for c in cols] == [c.lower() for c in wc]:
                raise ValueError("a wrong query gives the same result as the right one")
        except SqlError:
            pass
    add(topic, f'Which query answers this request?\n\n"{english}"', correct_sql, wrong_sqls, why,
        sql=correct_sql, tables=tables, mono=True, choice_sql=True, kind="sql_english")


@guard
def q_error(topic, sql, correct, wrongs, why, tables):
    try:
        db().run(sql)
    except SqlError:
        add(topic, "This query produces an error. What is wrong with it?", correct, wrongs, why,
            code=sql, sql=sql, tables=tables, kind="sql_error")
        return
    raise ValueError("query did not fail")


def C(topic, prompt, correct, wrongs, why):
    add(topic, prompt, correct, wrongs, why)


EMP, PRO, ORD = ["employees"], ["products"], ["orders"]


def build_bank():
    # ----------------------------------------------------------------- Week 1
    C("W1", "What is an operating system (OS)?",
      "Software that manages the computer's hardware and resources and provides services for other programs",
      ["A program used only for creating documents and spreadsheets", "A database engine that stores tables",
       "The physical hardware that stores files permanently"],
      "The OS sits between hardware and applications: it manages memory, processors, storage and devices, and "
      "lets programs run.")
    C("W1", "Which of the following is an operating system?",
      "Windows", ["Microsoft Excel", "MySQL Workbench", "Google Chrome"],
      "Windows, macOS and Linux are operating systems. Excel, Workbench and Chrome are applications that run on one.")
    C("W1", "Which task is a core job of an operating system?",
      "Managing files, memory and running programs",
      ["Designing the tables of a database", "Translating English requests into SQL",
       "Collecting business requirements from stakeholders"],
      "Managing resources (files, memory, processes, devices) is what an OS does.")
    C("W1", "In the file name  sales_2024.csv , what is  .csv ?",
      "The file extension, which tells you the file's type/format",
      ["The file path", "The name of the folder it is stored in", "The owner of the file"],
      "The extension (the part after the last dot) signals the file type so the system knows which program opens it.")
    C("W1", "Which of these is an ABSOLUTE file path?",
      "C:\\Users\\Sam\\Documents\\data.csv", ["data.csv", "..\\data\\data.csv", ".\\reports\\q1.xlsx"],
      "An absolute path starts at the root of the drive (like C:\\ or /) and gives the complete location, no matter "
      "where you are working from.")
    C("W1", "What is a RELATIVE file path?",
      "A location described starting from the current working folder, such as data/sales.csv",
      ["A location that always starts at the root of the drive", "The path that ends with the file extension",
       "A path that only works on one specific computer"],
      "Relative paths depend on the current working directory, so the same relative path can point to different "
      "files in different places.")
    C("W1", "In a relative path, what does  ..  (two dots) mean?",
      "The parent folder of the current folder",
      ["The current folder", "The root of the drive", "The user's home folder"],
      "One dot (.) is the current folder; two dots (..) go up one level to the parent folder.")
    C("W1", "What does a file system do?",
      "Organizes and keeps track of how files are named, stored and located on a storage device",
      ["Compiles code into programs", "Converts SQL queries into result sets",
       "Encrypts every file automatically"],
      "The file system is the OS component that structures storage into files and folders.")
    C("W1", "Which environment is where developers build and change code freely without affecting real users?",
      "Development", ["Production", "Testing", "Archive"],
      "Development is the sandbox for building. Testing verifies the work, and production serves real users.")
    C("W1", "Where is a change typically verified with realistic (non-live) data before it is released?",
      "Testing", ["Development", "Production", "Backup"],
      "The testing (staging) environment checks that things work before they go to production.")
    C("W1", "Which environment serves real users and real business data?",
      "Production", ["Development", "Testing", "Sandbox"],
      "Production is the live environment. Mistakes here affect real people and real data.")
    C("W1", "Why should untested changes NOT be made directly in production?",
      "Errors could disrupt real users and damage real data",
      ["Production computers are slower than development computers", "Production does not allow SQL",
       "It is against the rules of the operating system"],
      "Develop in development, verify in testing, and only then release to production.")
    C("W1", "Which action best reflects data ethics?",
      "Collecting only the data you need and protecting individuals' privacy",
      ["Selling customer data without telling the customers", "Keeping all data forever, just in case",
       "Sharing a dataset with names included because it's only internal"],
      "Data ethics centers on respect for people: minimal collection, consent, privacy, security, and honesty "
      "about how data is used.")
    C("W1", "Which is a core principle of data ethics?",
      "Transparency: being open about how data is collected and used",
      ["Collect as much data as possible", "Keep data practices secret to protect the company",
       "Speed matters more than accuracy"],
      "Common data-ethics principles include transparency, consent, privacy, ownership/fairness and accountability.")
    C("W1", "An app collects users' location data but never tells them. Which principle is most directly violated?",
      "Transparency and consent", ["Normalization", "Scalability", "Availability"],
      "People should know what is collected and agree to it.")
    C("W1", "Which file name is the best practice for sharing data files?",
      "customer_orders_2024.csv", ["Customer Orders (FINAL!!) v2 copy.csv", "stuff.csv", "orders/2024?.csv"],
      "Descriptive names without spaces or special characters work across systems; characters like / ? are not "
      "even allowed in file names.")

    # ----------------------------------------------------------------- Week 2
    C("W2", "What does 'socio-technical' mean in the context of databases?",
      "A database is both technology and people: the software, data and also the users, processes and policies around it",
      ["A database used only on social media sites", "A purely technical system that works independently of people",
       "A database designed only by technical staff"],
      "Databases exist inside organizations, so human needs and practices matter as much as tables and code.")
    C("W2", "Which of these is part of a database's TECHNICAL structure?",
      "Tables, columns, keys and data types",
      ["Whether employees trust the reports", "How departments argue over definitions",
       "Training users to ask good questions"],
      "Technical structure is the design built in the system. Trust, politics and training are human/social factors.")
    C("W2", "Which is a HUMAN (social) need related to a database?",
      "Reports that people can understand and trust well enough to make decisions",
      ["Using the INT data type for whole numbers", "Defining a primary key on every table",
       "Indexing a column for speed"],
      "People need data that is understandable, trustworthy and useful. That need goes beyond the technical design.")
    C("W2", "Two departments define 'active customer' differently, so their reports disagree. This is mainly...",
      "A socio-technical issue: the technology can't settle a disagreement between people's definitions",
      ["A hardware failure", "A SQL syntax error", "A data type mismatch"],
      "Meaning and agreement are social problems. The database stores whatever definition people choose.")
    C("W2", "Which is an example of an INTERNAL data source?",
      "A company's own sales transaction system",
      ["Census data published by the government", "A purchased third-party market study",
       "A public social media feed"],
      "Internal sources come from within the organization's own operations.")
    C("W2", "Census data downloaded from a government website is an example of...",
      "An external (public / open) data source",
      ["An internal transaction system", "Primary data you collected yourself", "A machine-generated log"],
      "External sources come from outside the organization. Government open data is a typical example.")
    C("W2", "A researcher surveys 200 students for their own study. The survey results are...",
      "Primary data (collected first-hand for the purpose)",
      ["Secondary data", "Open government data", "Log data"],
      "Primary data is collected directly by the person who will use it. Secondary data was collected by someone else.")
    C("W2", "A dataset someone else collected and published, which you reuse for your analysis, is...",
      "Secondary data", ["Primary data", "A primary key", "Metadata only"],
      "Reusing data collected by others is secondary data.")
    C("W2", "Web server logs and mobile-app click events are examples of...",
      "Machine-generated (log / event) data",
      ["Survey data", "Hand-entered spreadsheet data", "Business rules"],
      "Systems record this data automatically as people use them.")
    C("W2", "Which statement best describes how widely SQL is used?",
      "SQL appears in database systems, spreadsheets, BI tools, programming languages and cloud services",
      ["SQL only works inside one database product", "SQL is only used by database administrators",
       "SQL has been replaced by spreadsheets"],
      "SQL shows up everywhere data is stored or analyzed.")
    C("W2", "Which of these can use SQL beyond a database management system?",
      "All of the above",
      ["Excel (through data connections)", "Tableau (through custom SQL / data connections)",
       "Python (through database libraries)"],
      "Excel, Tableau, programming languages and cloud platforms can all send SQL to a data source.")
    C("W2", "A Python script runs the SQL statement  SELECT * FROM customers  through a database library. This shows...",
      "SQL embedded in a programming language",
      ["A database engine written in Python", "A spreadsheet formula", "A business rule being enforced"],
      "Programs often include SQL to read and write data in a database.")

    # ----------------------------------------------------------------- Week 3
    C("W3", "Which of these is a BUSINESS REQUIREMENT?",
      "The system must let managers view monthly sales by region",
      ["An order cannot be placed if the customer's account is suspended",
       "Every order ID must be unique", "Discounts above 20% need manager approval"],
      "A requirement states a need or capability the business wants. The others are rules that constrain how the "
      "business operates.")
    C("W3", "Which of these is a BUSINESS RULE?",
      "A customer cannot place an order if the account is suspended",
      ["The system must let managers view monthly sales by region", "The website should have a modern look",
       "The company wants to grow revenue by 10%"],
      "A rule defines or constrains how the business operates. It is a policy or constraint.")
    C("W3", "What is a business requirement?",
      "A statement of what the business needs a solution to accomplish",
      ["A policy that restricts how data may change", "A line of SQL code",
       "A diagram that shows table relationships"],
      "Requirements describe needs, goals and capabilities (the 'what'), usually from stakeholders.")
    C("W3", "What is a business rule?",
      "A statement that defines or constrains some aspect of how the business operates",
      ["A wish list of features users would like", "A type of database table",
       "The estimated project budget"],
      "Rules express policies, definitions and constraints that the business follows.")
    C("W3", "Where do business requirements initially come from?",
      "Stakeholders: users, managers, customers and business goals",
      ["Database column names", "The SQL standard", "The operating system"],
      "Requirements start with the people who need and use the solution.")
    C("W3", "Where do business rules initially come from?",
      "Company policies, laws and regulations, contracts and management decisions",
      ["Random guesses by developers", "The color scheme of the interface", "The speed of the network"],
      "Rules come from policy, law, contracts and decisions made by the organization.")
    C("W3", "'The system must generate an invoice for every completed order.' What kind of requirement is this?",
      "A functional requirement (something the system must do)",
      ["A non-functional requirement", "A feasibility study", "A business rule about data types"],
      "Functional requirements describe behaviors or features. Non-functional ones describe qualities such as "
      "speed, security or usability.")
    C("W3", "'The search page must return results in under 2 seconds.' What kind of requirement is this?",
      "A non-functional requirement (a quality such as performance)",
      ["A functional requirement", "A business rule", "A primary key"],
      "Performance, security, reliability and usability are typical non-functional requirements.")
    C("W3", "What does 'feasibility' ask about a proposed solution?",
      "Whether it can realistically be achieved given technical, financial, time and legal/operational limits",
      ["Whether the database has enough tables", "Whether the users like the idea",
       "Whether the SQL is written correctly"],
      "Feasibility checks that a project is realistic before committing to it.")
    C("W3", "A project is technically possible but would cost far more than the benefit it brings. Which feasibility is lacking?",
      "Economic feasibility", ["Technical feasibility", "Schedule feasibility", "Legal feasibility"],
      "Economic feasibility compares costs with benefits.")
    C("W3", "The team doesn't have the skills or tools needed to build the system. Which feasibility is lacking?",
      "Technical feasibility", ["Economic feasibility", "Legal feasibility", "Operational feasibility"],
      "Technical feasibility asks whether the technology and skills exist to build it.")
    C("W3", "Which is a common way to COLLECT requirements?",
      "Interviews, surveys, observation and workshops with stakeholders",
      ["Running SELECT queries", "Compressing files", "Formatting hard drives"],
      "Requirements are gathered by talking with and watching the people who will use the system.")
    C("W3", "Which activity is requirements ANALYSIS?",
      "Reviewing requirements for conflicts, gaps, ambiguity and priority",
      ["Writing the final SQL queries", "Installing the database engine", "Deleting duplicate rows"],
      "Analysis checks that the collected requirements are clear, consistent, complete and prioritized.")
    C("W3", "Which requirement is best written (clear and testable)?",
      "The system shall generate the monthly sales report within 30 seconds",
      ["The system should be fast", "The report should look nice", "The system must be user-friendly and good"],
      "Good requirements are specific and measurable so you can tell whether they were met.")
    C("W3", "'A preferred customer is a customer who has spent over $5,000 in a year.' This business rule is a...",
      "Definition of a business term", ["Constraint on data values", "Computation", "Action trigger"],
      "Rules can define terms the business uses (definitions), state facts, constrain data, compute values or "
      "trigger actions. (Your lecture slides may name the categories slightly differently.)")
    C("W3", "'A customer can place many orders.' This business rule is a...",
      "Fact about how business terms relate", ["Computation", "Action trigger", "Definition of a term"],
      "A fact rule states how things relate, which later becomes a relationship in the data model.")
    C("W3", "'An order total must never be negative.' This business rule is a...",
      "Constraint", ["Definition of a term", "Fact", "Feasibility study"],
      "Constraints limit allowed values or behavior, and many can be enforced in the database.")
    C("W3", "'Order total = sum of (item price x quantity).' This business rule is a...",
      "Computation (derivation)", ["Constraint", "Definition of a term", "Fact"],
      "Computation rules describe how a value is calculated from others.")
    C("W3", "'If stock falls below 10 units, a reorder is created.' This business rule is a...",
      "Action trigger (action enabler)", ["Definition of a term", "Fact", "Computation"],
      "Action rules say what should happen when a condition becomes true.")
    C("W3", "How are business rules typically collected?",
      "From policy documents, subject-matter experts, interviews and existing procedures",
      ["By running aggregate SQL functions", "By guessing from table names", "From the file system"],
      "Rules are discovered in the places where the business writes down or practices its policies.")

    # ----------------------------------------------------------------- Week 4
    C("W4", "What is a SET?",
      "A collection of distinct objects (elements), where order doesn't matter",
      ["An ordered list that may contain duplicates", "A single value", "A programming loop"],
      "Sets come from mathematics: elements are distinct and have no order.")
    C("W4", "Why is set theory relevant to databases and SQL?",
      "Tables and result sets can be thought of as sets of rows, and SQL operations work on sets of data",
      ["Because databases only store numbers", "Because SQL was designed for drawing diagrams",
       "It isn't relevant"],
      "A table is a set of rows, and a query returns another set (a result set).")
    C("W4", "A = {1, 2, 3, 4} and B = {3, 4, 5, 6}.  What is the INTERSECTION of A and B?",
      "{3, 4}", ["{1, 2, 3, 4, 5, 6}", "{1, 2}", "{5, 6}"],
      "Intersection = elements that are in BOTH sets.")
    C("W4", "A = {1, 2, 3, 4} and B = {3, 4, 5, 6}.  What is the UNION of A and B?",
      "{1, 2, 3, 4, 5, 6}", ["{3, 4}", "{1, 2}", "{1, 2, 3, 4, 3, 4, 5, 6}"],
      "Union = elements in either set. Duplicates are listed once, because sets hold distinct elements.")
    C("W4", "A = {1, 2, 3, 4} and B = {3, 4, 5, 6}.  What is the DIFFERENCE A - B?",
      "{1, 2}", ["{5, 6}", "{3, 4}", "{1, 2, 5, 6}"],
      "Difference A - B = elements in A that are NOT in B. (B - A would be {5, 6}.)")
    C("W4", "A = {1, 2} and B = {1, 2, 3}.  What is the relationship between A and B?",
      "A is a subset of B", ["B is a subset of A", "A and B are disjoint", "A and B are equal"],
      "A subset has all its elements inside the larger set.")
    C("W4", "The rows returned by a query with a WHERE condition are best described as a...",
      "Subset of the table's rows", ["Union of all tables", "Copy of the whole table", "Different database"],
      "Filtering produces a subset of the original set of rows.")
    C("W4", "Customers who ordered online AND also ordered in-store are found with which set concept?",
      "Intersection", ["Union", "Difference", "Subset"],
      "'Both' means intersection.")
    C("W4", "Customers who ordered online but did NOT order in-store are found with which set concept?",
      "Difference (online - in-store)", ["Intersection", "Union", "Complement of the union"],
      "'In one set but not the other' is a difference.")
    C("W4", "All customers who ordered online OR in-store (or both) correspond to which set concept?",
      "Union", ["Intersection", "Difference", "Subset"],
      "'Either or both' is a union.")
    C("W4", "Relational theory is founded in part on...",
      "Set theory", ["Graph drawing", "Spreadsheet formulas", "Network protocols"],
      "The relational model treats a relation (table) as a set of tuples (rows).")
    C("W4", "In relational terms, a TABLE corresponds to a ___ and a ROW corresponds to a ___.",
      "Relation; tuple", ["Attribute; relation", "Tuple; attribute", "Key; entity"],
      "Relation = table, tuple = row, attribute = column.")
    C("W4", "In a Student table, which of these is an ATTRIBUTE?",
      "The student's email address (a column)", ["The Student table itself", "The collection of all students",
                                                 "The relationship between students and courses"],
      "Attributes describe an entity. They become columns.")
    C("W4", "In a database design, which of these is best described as an ENTITY?",
      "Student", ["Email address", "Birth date", "Phone number"],
      "An entity is a thing we store data about (customer, product, order). It becomes a table.")
    C("W4", "What is a primary key?",
      "An attribute (or set of attributes) that uniquely identifies each row and can't be NULL",
      ["A column that links to another table's key", "The first column in any table",
       "A key that allows duplicate values"],
      "Each row must be uniquely identifiable by its primary key.")
    C("W4", "What is a foreign key?",
      "An attribute in one table that refers to the primary key of another table",
      ["A key that uniquely identifies rows in its own table", "A password for the database",
       "The first row of a table"],
      "Foreign keys create the links (relationships) between tables.")
    C("W4", "Which column is the best choice for a primary key of a Student table?",
      "student_id", ["last_name", "birth_date", "city"],
      "It must be unique for every row, which names, dates and cities are not.")
    C("W4", "What is a composite key?",
      "A key made of two or more columns that together identify a row",
      ["A key that has been encrypted", "A foreign key in a different database", "A key that allows NULLs"],
      "Sometimes no single column is unique, but a combination is.")
    C("W4", "Each employee is issued exactly one laptop, and each laptop is assigned to exactly one employee. The relationship is...",
      "One-to-one", ["One-to-many", "Many-to-many", "Many-to-one only"], "One of each on both sides = 1:1.")
    C("W4", "A customer can place many orders, and each order belongs to exactly one customer. The relationship is...",
      "One-to-many", ["One-to-one", "Many-to-many", "No relationship"], "One customer to many orders = 1:M.")
    C("W4", "Students can enroll in many courses, and each course has many students. The relationship is...",
      "Many-to-many", ["One-to-one", "One-to-many", "Many-to-one only"], "Many on both sides = M:M.")
    C("W4", "A department has many employees, and each employee works in exactly one department. The relationship is...",
      "One-to-many", ["One-to-one", "Many-to-many", "Zero-to-zero"], "One department to many employees = 1:M.")
    C("W4", "A book can have several authors, and an author can write several books. The relationship is...",
      "Many-to-many", ["One-to-many", "One-to-one", "Not a valid relationship"], "Many authors per book and many books per author = M:M.")
    C("W4", "How is a many-to-many relationship typically implemented in a relational database?",
      "With an associative (junction/bridge) table that holds a foreign key to each side",
      ["By putting both tables in one column", "By repeating rows in one of the tables", "It can't be implemented"],
      "The junction table turns one M:M into two 1:M relationships.")
    C("W4", "In a one-to-many relationship, where does the foreign key go?",
      "In the table on the 'many' side", ["In the table on the 'one' side", "In both tables", "In neither table"],
      "Each order row stores its customer_id, so the foreign key is in the 'many' table (orders).")
    C("W4", "On an ER diagram, a line with a single bar at one end and a 'crow's foot' at the other typically shows...",
      "A one-to-many relationship", ["A one-to-one relationship", "A many-to-many relationship", "A primary key"],
      "The crow's foot marks the 'many' end.")

    # ----------------------------------------------------------------- Week 5
    C("W5", "What does SQL stand for?",
      "Structured Query Language", ["Standard Question Logic", "Sequential Query Layout", "Simple Quick Language"],
      "SQL = Structured Query Language.")
    C("W5", "What is the general purpose of SQL?",
      "To communicate with relational databases: define, retrieve and manage data",
      ["To design web pages", "To manage operating system files", "To draw ER diagrams"],
      "SQL is the standard language for working with relational data.")
    C("W5", "What is a query?",
      "A request for data (written in SQL) that a database engine processes",
      ["A table that stores data", "A type of key", "A spreadsheet formula"],
      "A query asks the database a question. The answer comes back as a result set.")
    C("W5", "The request 'Show all products that cost more than $100' maps which part of the English to a WHERE condition?",
      "'cost more than $100'  ->  WHERE price > 100", ["'Show all products'  ->  WHERE", "'products'  ->  WHERE", "'Show'  ->  WHERE price"],
      "The filter on rows becomes the WHERE clause. 'Show' becomes SELECT and 'products' becomes FROM.")
    C("W5", "Which statement best describes how a query is processed?",
      "The interface sends the query to the database engine, which parses it, plans it, runs it against the stored data and returns a result set",
      ["The interface stores the data and runs the query itself", "The result set is typed in by the user",
       "The query changes the tables so they match the result"],
      "Interface -> engine -> result set returned to the interface.")
    C("W5", "Which of the following is a database ENGINE?",
      "MySQL Server", ["MySQL Workbench", "Microsoft Excel", "Tableau"],
      "The engine stores the data and executes queries. Workbench, Excel and Tableau are interfaces/clients.")
    C("W5", "Which of the following is an INTERFACE used to write and send queries?",
      "MySQL Workbench", ["MySQL Server", "The storage files on disk", "The query optimizer"],
      "Workbench is a client interface that connects to a database engine.")
    C("W5", "What is the difference between a database engine and an interface?",
      "The engine stores data and executes queries; an interface lets people or tools send queries and view results",
      ["The interface stores the data and the engine displays it", "They are two names for the same thing",
       "The engine is always a spreadsheet"],
      "Examples of interfaces: Workbench, Excel, Tableau and programming languages.")
    C("W5", "Excel, Tableau and a Python script that connect to MySQL are all examples of...",
      "Interfaces (clients) that send queries to the engine", ["Database engines", "Result sets", "Primary keys"],
      "They talk to the engine, which does the real work.")
    C("W5", "What is the minimum requirement for any SELECT query?",
      "SELECT and FROM", ["SELECT and WHERE", "FROM and ORDER BY", "SELECT, FROM and GROUP BY"],
      "Every query must say what to select and where to select it from. Everything else is optional.")
    C("W5", "What does SELECT * return?", "All columns of the table",
      ["Only the first column", "All rows but no columns", "Only the primary key"],
      "* is a wildcard meaning 'all columns'.")
    C("W5", "In the SELECT pattern, which clause chooses which COLUMNS (attributes) or expressions appear in the result?",
      "SELECT", ["FROM", "WHERE", "ORDER BY"], "SELECT filters columns. WHERE filters rows.")
    C("W5", "What does the DISTINCT keyword do?", "Eliminates duplicate rows from the result set",
      ["Sorts the rows", "Removes NULL values only", "Groups rows into categories"],
      "SELECT DISTINCT returns each different row only once.")
    C("W5", "What does the FROM clause specify?", "The base table for the query",
      ["Which columns to show", "How rows are sorted", "Which groups to keep"], "FROM names the table (or tables) to read.")
    C("W5", "What does the WHERE clause filter?", "Rows, based on logical conditions",
      ["Columns", "Groups, after aggregation", "The sort order"], "WHERE keeps only rows where the condition is true.")
    C("W5", "What does GROUP BY do?", "Assembles rows with the same values in the specified columns into groups",
      ["Sorts the final result", "Filters individual rows", "Removes duplicate columns"],
      "GROUP BY is usually used with aggregate functions.")
    C("W5", "What does HAVING do?", "Filters groups after grouping (usually with aggregate functions)",
      ["Filters individual rows before grouping", "Chooses the columns", "Sorts the result"],
      "HAVING is to groups what WHERE is to rows.")
    C("W5", "What does ORDER BY do?", "Sorts the final result set by one or more columns or expressions",
      ["Filters rows", "Groups rows", "Chooses the base table"], "ORDER BY controls the order of the result set (ASC by default).")
    C("W5", "Which shows the correct ORDER in which SELECT clauses are WRITTEN?",
      "SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY",
      ["SELECT, WHERE, FROM, GROUP BY, ORDER BY, HAVING", "FROM, SELECT, WHERE, HAVING, GROUP BY, ORDER BY",
       "SELECT, FROM, GROUP BY, WHERE, HAVING, ORDER BY"],
      "Memorize the query pattern: SELECT [DISTINCT] / FROM / WHERE / GROUP BY / HAVING / ORDER BY.")
    C("W5", "Which list correctly describes the operators a WHERE clause can use?",
      "=, >, <, IN, BETWEEN and LIKE, with compound conditions joined by AND / OR",
      ["Only = and <>", "Only AND and OR", "Only LIKE"],
      "WHERE accepts comparison operators, IN, BETWEEN and LIKE, and compound conditions joined by AND or OR.")
    C("W5", "What is a RESULT SET?",
      "The rows and columns a query returns, a temporary table derived from (a subset of) the database's data",
      ["A permanent copy of the table", "A list of SQL commands", "The database engine's error log"],
      "A result set is not stored in the database. It exists for the answer to your query.")
    C("W5", "Does running a SELECT query change the data stored in the table?",
      "No, it only reads data and returns a result set", ["Yes, it deletes rows not in the result",
                                                          "Yes, it re-sorts the stored rows", "Yes, it removes duplicates from the table"],
      "SELECT never modifies the base table.")
    C("W5", "In a LIKE pattern, what does the % wildcard match?",
      "Any number of characters, including none", ["Exactly one character", "Only digits", "Only a percent sign"],
      "% = zero or more characters.")
    C("W5", "In a LIKE pattern, what does the _ (underscore) wildcard match?",
      "Exactly one character", ["Any number of characters", "Only a space", "Nothing"], "_ = exactly one character.")
    C("W5", "Is BETWEEN 10 AND 20 inclusive of the endpoints 10 and 20?",
      "Yes, both endpoints are included", ["No, neither is included", "Only 10 is included", "Only 20 is included"],
      "BETWEEN a AND b means >= a AND <= b.")

    q_result("W5", "What does this query return?",
             sq("first_name", "employees", "department = 'HR'", order="first_name"),
             [sq("first_name", "employees", "department = 'Finance'", order="first_name"),
              sq("first_name", "employees", "department = 'HR'", order="first_name DESC"),
              sq("first_name", "employees", "department = 'HR' AND salary > 60000", order="first_name")],
             "WHERE keeps only HR rows, SELECT keeps only first_name, ORDER BY sorts A to Z.", EMP)
    q_result("W5", "What does this query return?",
             sq("product_name", "products", "product_name LIKE 'Mo%'", order="product_name"),
             [sq("product_name", "products", "product_name LIKE 'Mo_'", order="product_name"),
              sq("product_name", "products", "product_name LIKE '%er'", order="product_name"),
              sq("product_name", "products", "product_name LIKE 'M%'", order="product_name DESC")],
             "'Mo%' means starts with Mo followed by anything. 'Mo_' needs exactly one more character.", PRO)
    q_result("W5", "What does this query return?",
             sq("product_name", "products", "product_name LIKE '%board'", order="product_name"),
             [sq("product_name", "products", "product_name LIKE 'board%'", order="product_name"),
              sq("product_name", "products", "product_name LIKE '%board%' AND category = 'Electronics'", order="product_name"),
              sq("product_name", "products", "product_name LIKE '_ouse'", order="product_name")],
             "'%board' means ends with 'board' (anything before it).", PRO)
    q_result("W5", "What does this query return?",
             sq("product_name", "products", "price BETWEEN 8.99 AND 19.99", order="product_name"),
             [sq("product_name", "products", "price > 8.99 AND price < 19.99", order="product_name"),
              sq("product_name", "products", "price BETWEEN 5 AND 9", order="product_name"),
              sq("product_name", "products", "price IN (8.99, 19.99)", order="product_name DESC")],
             "BETWEEN includes both endpoints, so the $8.99 and $19.99 items are included.", PRO)
    q_result("W5", "What does this query return?",
             sq("first_name", "employees", "department IN ('HR', 'Finance')", order="first_name"),
             [sq("first_name", "employees", "department = 'HR' AND department = 'Finance'", order="first_name"),
              sq("first_name", "employees", "department = 'HR'", order="first_name"),
              sq("first_name", "employees", "department IN ('HR', 'Finance') AND salary > 62000", order="first_name")],
             "IN matches any value in the list. A row can't be in HR AND Finance at once, so AND would return nothing.", EMP)
    q_result("W5", "What does this query return? (AND is evaluated before OR)",
             sq("first_name", "employees", "department = 'HR' OR department = 'Finance' AND salary > 62000", order="first_name"),
             [sq("first_name", "employees", "(department = 'HR' OR department = 'Finance') AND salary > 62000", order="first_name"),
              sq("first_name", "employees", "department = 'Finance' AND salary > 62000", order="first_name"),
              sq("first_name", "employees", "department = 'HR' AND department = 'Finance'", order="first_name")],
             "AND binds tighter than OR: it reads  HR  OR  (Finance AND salary > 62000). Parentheses change the meaning.", EMP)
    q_rows("W5", "How many rows does this result set contain?",
           sq("first_name, last_name", "employees", "department = 'IT'"), [12, 3, 2, 1],
           "Count the rows that pass WHERE. The number of columns doesn't change the number of rows.", EMP)
    q_rows("W5", "How many rows does this result set contain?",
           sq("*", "products", "stock = 0"), [12, 0, 2, 3],
           "Only the one product with stock = 0 passes the filter.", PRO)
    q_which("W5", "Which query produced this result set?",
            sq("first_name, salary", "employees", "department = 'IT' AND salary > 80000", order="salary DESC"),
            [sq("first_name, salary", "employees", "department = 'IT' AND salary > 80000", order="salary"),
             sq("first_name, salary", "employees", "department = 'IT' AND salary > 60000", order="salary DESC"),
             sq("first_name, salary", "employees", "department = 'IT' OR salary > 80000", order="salary DESC")],
            "Two rows (both IT, salary over 80,000), sorted highest salary first, so DESC.", EMP)
    q_which("W5", "Which query produced this result set?",
            sq("DISTINCT status", "orders", order="status"),
            [sq("status", "orders", order="status"),
             sq("DISTINCT customer_name", "orders", order="customer_name"),
             sq("status", "orders", "status = 'Shipped'")],
            "Three different statuses, each listed once. That is what DISTINCT does.", ORD)
    q_english("W5", "List the names of all products in the Electronics category.",
              sq("product_name", "products", "category = 'Electronics'"),
              [sq("category", "products", "product_name = 'Electronics'"), sq("*", "products"),
               sq("product_name", "products", "category LIKE 'E'")],
              "'List the names' -> SELECT product_name. 'products' -> FROM. 'in the Electronics category' -> WHERE category = 'Electronics'.", PRO)
    q_english("W5", "Show the first and last names of employees hired after January 1, 2020, newest first.",
              sq("first_name, last_name", "employees", "hire_date > '2020-01-01'", order="hire_date DESC"),
              [sq("first_name, last_name", "employees", "hire_date > '2020-01-01'", order="hire_date"),
               sq("first_name, last_name", "employees", "hire_date < '2020-01-01'", order="hire_date DESC"),
               sq("first_name, last_name, hire_date", "employees", "hire_date = '2020'")],
              "'after' -> >, 'newest first' -> ORDER BY hire_date DESC (dates sort chronologically as YYYY-MM-DD).", EMP)
    q_english("W5", "Show the last names of employees whose last name starts with M.",
              sq("last_name", "employees", "last_name LIKE 'M%'"),
              [sq("last_name", "employees", "last_name LIKE 'M_'"), sq("last_name", "employees", "last_name LIKE '%M'"),
               sq("last_name", "employees", "last_name = 'M%'")],
              "'starts with M' -> LIKE 'M%'. (= treats the % as a plain character.)", EMP)
    q_english("W5", "List the product names and prices of items under $10, cheapest first.",
              sq("product_name, price", "products", "price < 10", order="price"),
              [sq("product_name, price", "products", "price < 10", order="price DESC"),
               sq("product_name, price", "products", "price > 10", order="price"),
               sq("product_name", "products", "price < 10", order="price")],
              "'under $10' -> price < 10, 'cheapest first' -> ORDER BY price (ascending).", PRO)
    q_error("W5", "SELECT first_name employees",
            "FROM is missing, so SQL can't tell which table to read",
            ["first_name is not a valid column name", "employees must be spelled in uppercase",
             "SELECT can't be used without WHERE"],
            "The minimum for any query is SELECT and FROM.", EMP)
    q_error("W5", sq("first_name", "employees", order="first_name") + "\nWHERE salary > 50000",
            "The clauses are out of order: WHERE must come before ORDER BY",
            ["ORDER BY can't be used with first_name", "WHERE must be written before SELECT",
             "There is no table called employees"],
            "Write clauses in order: SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY.", EMP)

    # ----------------------------------------------------------------- Week 6
    C("W6", "What does AGGREGATION do in SQL?",
      "Combines many rows into a single summary value (such as a count or total)",
      ["Sorts rows alphabetically", "Deletes duplicate rows", "Renames columns"],
      "Aggregate functions summarize a set of rows.")
    C("W6", "Which aggregate function counts rows?", "COUNT()", ["SUM()", "AVG()", "MAX()"], "COUNT counts; SUM adds; AVG averages.")
    C("W6", "Which aggregate function adds up the values in a column?", "SUM()", ["COUNT()", "MIN()", "AVG()"], "SUM() totals numeric values.")
    C("W6", "Which aggregate function returns the average of a column?", "AVG()", ["SUM()", "COUNT()", "MAX()"], "AVG() = SUM / number of non-NULL values.")
    C("W6", "Which aggregate functions return the smallest and largest values?", "MIN() and MAX()",
      ["LOW() and HIGH()", "SMALL() and LARGE()", "FIRST() and LAST()"], "MIN() and MAX().")
    C("W6", "Why do we use aggregation in queries?", "To summarize large amounts of data (totals, counts, averages) instead of listing every row",
      ["To make queries run slower", "To hide columns from users", "To sort the table permanently"],
      "Aggregates answer questions like 'how many?' and 'what is the total?'.")
    C("W6", "What does GROUP BY do?", "Splits the rows into groups that share the same value(s) so aggregates are computed per group",
      ["Sorts the result alphabetically", "Filters individual rows", "Joins two tables"],
      "With GROUP BY department, COUNT(*) is calculated once per department.")
    C("W6", "When do you typically use GROUP BY?", "When you want an aggregate result per category (for example, total per department)",
      ["When you want to see every individual row", "When you need to rename a column", "When you want to delete rows"],
      "Use it when the question contains 'for each' or 'per'.")
    C("W6", "Which clause can filter on an aggregate such as COUNT(*) > 3?", "HAVING", ["WHERE", "FROM", "ORDER BY"],
      "WHERE filters rows before grouping and can't use aggregates. HAVING filters groups afterwards.")
    C("W6", "What is the difference between WHERE and HAVING?",
      "WHERE filters rows before grouping; HAVING filters groups after grouping",
      ["WHERE filters groups; HAVING filters rows", "They are identical", "HAVING is only used with ORDER BY"],
      "Logical order: FROM, WHERE, GROUP BY, HAVING, SELECT, DISTINCT, ORDER BY.")
    C("W6", "In which order does SQL logically PROCESS the clauses of a query?",
      "FROM, WHERE, GROUP BY, HAVING, SELECT, DISTINCT, ORDER BY",
      ["SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY", "WHERE, FROM, SELECT, GROUP BY, ORDER BY, HAVING",
       "ORDER BY, SELECT, FROM, WHERE, GROUP BY, HAVING"],
      "You write SELECT first, but SQL starts with FROM. Step through any query in the SQL Lab to watch it happen.")
    C("W6", "With  SELECT department, COUNT(*) ... GROUP BY department , what must be true in standard SQL?",
      "Every non-aggregated column in SELECT must appear in GROUP BY",
      ["Every column must be inside an aggregate function", "GROUP BY must come before FROM",
       "Only one column may be selected"],
      "Otherwise SQL can't know which value of the column to show for the group.")
    C("W6", "What is the purpose of the DISTINCT keyword in SELECT?", "To remove duplicate rows from the result set",
      ["To sort the rows", "To count the rows", "To group rows by column"], "SELECT DISTINCT returns unique rows only.")
    C("W6", "What does COUNT(DISTINCT department) return?", "The number of different department values",
      ["The total number of rows", "The largest department", "The departments sorted alphabetically"],
      "DISTINCT inside COUNT counts unique values only.")

    q_result("W6", "What does this query return?", "SELECT COUNT(*)\nFROM employees",
             ["SELECT COUNT(bonus)\nFROM employees", "SELECT COUNT(DISTINCT department)\nFROM employees",
              "SELECT COUNT(DISTINCT salary)\nFROM employees"],
             "COUNT(*) counts all rows. COUNT(column) skips NULLs. COUNT(DISTINCT column) counts different values.", EMP, scalar=True)
    q_result("W6", "What does this query return?", "SELECT COUNT(bonus)\nFROM employees",
             ["SELECT COUNT(*)\nFROM employees", "SELECT COUNT(DISTINCT department)\nFROM employees",
              "SELECT SUM(bonus)\nFROM employees"],
             "COUNT(bonus) counts only the rows where bonus is NOT NULL, while COUNT(*) counts every row.", EMP, scalar=True)
    q_result("W6", "What does this query return?", "SELECT AVG(bonus)\nFROM employees",
             ["SELECT SUM(bonus) / COUNT(*)\nFROM employees", "SELECT SUM(bonus)\nFROM employees",
              "SELECT MAX(bonus)\nFROM employees"],
             "AVG ignores NULLs: 20,500 total / 5 non-NULL bonuses = 4,100. Dividing by all 12 rows would give a different number.", EMP, scalar=True)
    q_result("W6", "What does this query return?", sq("SUM(salary)", "employees", "department = 'IT'"),
             [sq("AVG(salary)", "employees", "department = 'IT'"), sq("MAX(salary)", "employees", "department = 'IT'"),
              sq("SUM(salary)", "employees", "department = 'Sales'")],
             "WHERE keeps the IT rows first, then SUM adds their salaries.", EMP, scalar=True)
    q_result("W6", "What does this query return?", sq("AVG(salary)", "employees", "department = 'Sales'"),
             [sq("SUM(salary)", "employees", "department = 'Sales'"), sq("AVG(salary)", "employees", "department = 'HR'"),
              sq("MIN(salary)", "employees", "department = 'Sales'")],
             "Sales salaries: 52,000 + 78,000 + 49,000 + 52,000 = 231,000, divided by 4 rows.", EMP, scalar=True)
    q_result("W6", "What does this query return?", sq("MIN(price), MAX(price)", "products", "category = 'Furniture'"),
             [sq("MIN(price), MAX(price)", "products", "category = 'Electronics'"),
              sq("MAX(price), MIN(price)", "products", "category = 'Furniture'"),
              sq("MIN(price), MAX(price)", "products", "category = 'Stationery'")],
             "One summary row: the cheapest and the most expensive Furniture item (column order follows SELECT).", PRO)
    q_result("W6", "What does this query return?",
             sq("department, COUNT(*)", "employees", group="department", having="COUNT(*) > 2", order="department"),
             [sq("department, COUNT(*)", "employees", group="department", having="COUNT(*) = 2", order="department"),
              sq("department, COUNT(*)", "employees", "salary > 60000", group="department", having="COUNT(*) > 2", order="department"),
              sq("department, COUNT(*)", "employees", group="department", having="COUNT(*) > 4", order="department")],
             "Groups: IT 4, Sales 4, HR 2, Finance 2. HAVING keeps the groups with more than 2 rows.", EMP)
    q_result("W6", "What does this query return?",
             sq("status, COUNT(*)", "orders", group="status", order="status"),
             [sq("customer_name, COUNT(*)", "orders", group="customer_name", order="customer_name"),
              sq("status, SUM(total)", "orders", group="status", order="status"),
              sq("status, COUNT(*)", "orders", "status <> 'Shipped'", group="status", order="status")],
             "One output row per different status, with the number of orders in each.", ORD)
    q_result("W6", "What does this query return?",
             sq("customer_name, SUM(total)", "orders", "status = 'Shipped'", "customer_name", "SUM(total) > 200", "customer_name"),
             [sq("customer_name, SUM(total)", "orders", None, "customer_name", "SUM(total) > 200", "customer_name"),
              sq("customer_name, SUM(total)", "orders", "status = 'Shipped'", "customer_name", None, "customer_name"),
              sq("customer_name, SUM(total)", "orders", "status = 'Shipped'", "customer_name", "SUM(total) > 500", "customer_name")],
             "WHERE first removes non-shipped orders, GROUP BY totals each customer, HAVING keeps totals over 200.", ORD)
    q_result("W6", "What does this query return?",
             sq("DISTINCT salary", "employees", "department = 'IT'", order="salary"),
             [sq("salary", "employees", "department = 'IT'", order="salary"),
              sq("DISTINCT department", "employees", order="department"),
              sq("DISTINCT salary", "employees", "department = 'IT'", order="salary DESC")],
             "IT salaries are 67,000, 67,000, 91,000 and 95,000. DISTINCT keeps 67,000 only once.", EMP)
    q_rows("W6", "How many rows are in this result set?", "SELECT DISTINCT department\nFROM employees",
           [12, 2, 3, 1], "There are 12 employees but only 4 different departments.", EMP)
    q_rows("W6", "How many rows are in this result set?", sq("department, COUNT(*)", "employees", group="department"),
           [12, 1, 6, 2], "One row per group, one group per different department.", EMP)
    q_rows("W6", "How many rows are in this result set?", "SELECT COUNT(*)\nFROM employees",
           [12, 0, 4, 2], "An aggregate with no GROUP BY collapses everything into a single row (the number inside is 12, but it is ONE row).", EMP)
    q_which("W6", "Which query produced this result set?",
            sq("department, COUNT(*) AS headcount", "employees", group="department", order="department"),
            [sq("department, SUM(salary) AS headcount", "employees", group="department", order="department"),
             sq("job_title, COUNT(*) AS headcount", "employees", group="job_title", order="job_title"),
             sq("department, COUNT(*) AS headcount", "employees", "salary > 60000", "department", order="department")],
            "Each department appears once with its number of employees, which is COUNT(*) grouped by department.", EMP)
    q_which("W6", "Which query produced this result set?",
            sq("customer_name, COUNT(*) AS orders", "orders", group="customer_name", having="COUNT(*) > 2"),
            [sq("customer_name, COUNT(*) AS orders", "orders", group="customer_name", having="COUNT(*) > 1"),
             sq("customer_name, COUNT(*) AS orders", "orders", "total > 2", "customer_name"),
             sq("customer_name, SUM(total) AS orders", "orders", group="customer_name", having="COUNT(*) > 2")],
            "Only one customer has more than 2 orders, so HAVING COUNT(*) > 2 leaves one group.", ORD)
    q_which("W6", "Which query produced this result set?",
            sq("MAX(total) AS biggest", "orders"),
            [sq("MIN(total) AS biggest", "orders"), sq("SUM(total) AS biggest", "orders"), sq("COUNT(total) AS biggest", "orders")],
            "A single value that is the largest order total: MAX.", ORD)
    q_english("W6", "How many employees are in each department?",
              sq("department, COUNT(*)", "employees", group="department"),
              [sq("department, COUNT(*)", "employees"), sq("COUNT(department)", "employees"),
               sq("department, SUM(salary)", "employees", group="department")],
              "'in each department' means GROUP BY department. COUNT(*) counts the rows in each group.", EMP)
    q_english("W6", "Show the departments whose average salary is above 60,000.",
              sq("department", "employees", group="department", having="AVG(salary) > 60000"),
              [sq("department", "employees", "salary > 60000", "department"),
               sq("department", "employees", group="department", having="AVG(salary) < 60000"),
               sq("department, AVG(salary)", "employees")],
              "The condition is about a group's AVERAGE, so it belongs in HAVING (after GROUP BY).", EMP)
    q_english("W6", "Show the highest price in each product category.",
              sq("category, MAX(price)", "products", group="category"),
              [sq("category, MAX(price)", "products"), sq("MAX(price)", "products"),
               sq("category, MIN(price)", "products", group="category")],
              "'in each category' -> GROUP BY category, 'highest' -> MAX.", PRO)
    q_english("W6", "Which customers have placed more than 2 orders?",
              sq("customer_name", "orders", group="customer_name", having="COUNT(*) > 2"),
              [sq("customer_name", "orders", "COUNT(*) > 2", "customer_name"), sq("customer_name", "orders", "total > 2"),
               sq("COUNT(*)", "orders", group="customer_name", having="customer_name > 2")],
              "COUNT(*) per customer needs GROUP BY customer_name and HAVING (WHERE can't use aggregates).", ORD)
    q_english("W6", "How many orders are not cancelled?",
              sq("COUNT(*)", "orders", "status <> 'Cancelled'"),
              [sq("COUNT(*)", "orders", "status = 'Cancelled'"), sq("status", "orders", "status <> 'Cancelled'"),
               sq("SUM(total)", "orders", "status <> 'Cancelled'")],
              "Filter the rows with WHERE, then count what is left with COUNT(*).", ORD)
    q_english("W6", "List each unique job title.",
              sq("DISTINCT job_title", "employees"),
              [sq("job_title", "employees"), sq("COUNT(job_title)", "employees"), sq("DISTINCT department", "employees")],
              "'each unique' -> DISTINCT.", EMP)
    q_error("W6", sq("department, COUNT(*)", "employees", "COUNT(*) > 3", "department"),
            "Aggregate functions like COUNT() can't be used in WHERE: use HAVING after GROUP BY",
            ["department must be inside an aggregate function", "GROUP BY must be written before FROM",
             "COUNT(*) can only be used with DISTINCT"],
            "WHERE runs before grouping, so no counts exist yet. HAVING runs after.", EMP)

    # ------------------------------------------------- Additional: data types
    C("AG", "Which data type is best for a product price such as 19.99?", "DECIMAL", ["INT", "DATE", "CHAR"],
      "DECIMAL stores exact numbers with decimals, which is ideal for money.")
    C("AG", "Which data type is best for the quantity in stock (whole items)?", "INT", ["DECIMAL", "VARCHAR", "DATETIME"],
      "INT stores whole numbers.")
    C("AG", "Which data type is best for a customer's name?", "VARCHAR", ["INT", "DECIMAL", "DATE"],
      "VARCHAR holds variable-length text.")
    C("AG", "What is the difference between CHAR and VARCHAR?",
      "CHAR has a fixed length; VARCHAR's length varies up to a maximum",
      ["CHAR stores numbers and VARCHAR stores dates", "VARCHAR is fixed length and CHAR varies",
       "They are identical in every way"],
      "CHAR(2) always uses 2 characters (good for state abbreviations); VARCHAR(50) uses only as much as needed.")
    C("AG", "Which data type stores a birth date such as 2001-04-17?", "DATE", ["DATETIME", "INT", "CHAR(1)"],
      "DATE holds a calendar date only.")
    C("AG", "Which data type stores a timestamp such as 2024-03-05 14:30:00?", "DATETIME", ["DATE", "INT", "DECIMAL"],
      "DATETIME includes both date and time.")
    C("AG", "Why is a phone number usually stored as text (CHAR/VARCHAR) instead of INT?",
      "It is an identifier, not something you do math on, and may have leading zeros or symbols",
      ["INT cannot store more than 5 digits", "Phone numbers must be sorted alphabetically",
       "Text columns are always faster"],
      "Store data according to how it is used. You never add phone numbers together.")
    C("AG", "Which of these sets matches data types to the right kind of data?",
      "INT: whole numbers; DECIMAL: prices; VARCHAR: text; DATE: calendar dates",
      ["INT: text; DECIMAL: dates; VARCHAR: prices; DATE: whole numbers", "INT: dates; DECIMAL: text; VARCHAR: whole numbers; DATE: prices",
       "INT: prices; DECIMAL: names; VARCHAR: dates; DATE: counts"],
      "Know the four families: INT, DECIMAL, CHAR/VARCHAR, DATE/DATETIME.")

    # ------------------------------------------------- Additional: query interpretation
    qa = sq("first_name, last_name, salary", "employees", "department = 'IT' AND salary > 80000", order="salary DESC")
    add("AG", "Reading this query: which table is being used?", "employees",
        ["salary", "IT", "first_name, last_name, salary"],
        "The table is whatever follows FROM.", code=qa, sql=qa, tables=EMP, kind="interpret")
    add("AG", "Reading this query: which columns appear in the result set?", "first_name, last_name and salary",
        ["department and salary", "Every column in the table", "Only salary"],
        "The columns are whatever follows SELECT. department is used for filtering but is not displayed.",
        code=qa, sql=qa, tables=EMP, kind="interpret")
    add("AG", "Reading this query: which condition(s) are applied?",
        "Rows must be in the IT department AND have a salary above 80,000",
        ["Rows must be in the IT department OR have a salary above 80,000", "Only rows sorted by salary are kept",
         "Salary must be exactly 80,000"],
        "WHERE has two conditions joined with AND, so both must be true.", code=qa, sql=qa, tables=EMP, kind="interpret")
    add("AG", "Reading this query: how are the results sorted?", "By salary, highest to lowest",
        ["By salary, lowest to highest", "By first_name, A to Z", "They are not sorted"],
        "ORDER BY salary DESC sorts from largest to smallest.", code=qa, sql=qa, tables=EMP, kind="interpret")
    q_rows("AG", "Reading this query: how many rows will the result set have?", qa, [12, 4, 3, 1],
           "Only Carla (91,000) and Grace (95,000) are in IT with salary above 80,000.", EMP)
    qb = sq("category, COUNT(*)", "products", "stock > 0", "category", "COUNT(*) > 3", "category")
    add("AG", "Reading this query: what is the HAVING clause doing?",
        "Keeping only the categories that have more than 3 products (after counting the in-stock ones)",
        ["Keeping only products with stock above 3", "Sorting categories by their count", "Removing duplicate categories"],
        "WHERE removed out-of-stock products first, GROUP BY made a group per category, and HAVING kept groups with more than 3 rows.",
        code=qb, sql=qb, tables=PRO, kind="interpret")
    add("AG", "Reading this query: what would the result set look like?",
        "One row: Electronics | 5", ["One row for every product", "Three rows, one per category with counts",
                                      "One row: Furniture | 3"],
        "Only Electronics has more than 3 in-stock products (5). Run it in the SQL Lab to check.",
        code=qb, sql=qb, tables=PRO, kind="interpret")
    q_which("AG", "A result set is shown. Which query produced it?",
            sq("product_name, price", "products", "category = 'Stationery' AND price < 6", order="price"),
            [sq("product_name, price", "products", "category = 'Stationery' OR price < 6", order="price"),
             sq("product_name, price", "products", "category = 'Stationery'", order="price DESC"),
             sq("product_name, stock", "products", "category = 'Stationery' AND price < 6", order="price")],
            "Work backwards: the columns come from SELECT, the rows from WHERE, and the row order from ORDER BY.", PRO)
    q_which("AG", "A result set is shown. Which query produced it?",
            sq("category, AVG(price) AS avg_price", "products", group="category", having="AVG(price) > 100", order="category"),
            [sq("category, AVG(price) AS avg_price", "products", group="category", order="category"),
             sq("category, MAX(price) AS avg_price", "products", group="category", having="MAX(price) > 100", order="category"),
             sq("category, AVG(price) AS avg_price", "products", "price > 100", "category", order="category")],
            "Only the categories whose average price is above 100 remain. A WHERE price > 100 would filter individual rows instead and change the averages.", PRO)

    random.Random(4420).shuffle(BANK)  # fixed order so reports are repeatable; the app reshuffles anyway


build_bank()


# ===========================================================================
# GUI (tkinter ships with Python)
# ===========================================================================
try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
    HAVE_TK = True
except Exception:  # ImportError, or a broken Tcl install
    HAVE_TK = False

if HAVE_TK:
    core = sys.modules[__name__]  # the GUI code below refers to the engine / question bank as `core`
    # palette
    # Every value inside one palette must be unique: switching themes remaps old colors to new ones.
    LIGHT = dict(
        BG="#f4f5f7", CARD="#ffffff", LINE="#d0d5dd", TEXT="#101828", MUTED="#667085", HEAD="#1e3a8a",
        ACCENT="#2563eb", ACCENT_DK="#1d4ed8", GOOD="#15803d", GOOD_BG="#dcfce7", BAD="#b91c1c",
        BAD_BG="#fee2e2", SEL_BG="#dbeafe", CUR_BG="#fff3b0", CHG_BG="#e6f4ea",
        SYN_KW="#008000", SYN_KWOP="#aa22ff", SYN_BUILTIN="#2e8b2e", SYN_STR="#ba2121",
        SYN_NUM="#2255dd", SYN_COMMENT="#408080", SYN_DEF="#0000ff",
        B1="#2f6fed", B2="#0d9488", B3="#ea7a12", B4="#7c3aed", B5="#16a34a", B6="#db2777",
    )
    DARK = dict(
        BG="#0d1117", CARD="#161b22", LINE="#30363d", TEXT="#e6edf3", MUTED="#8b949e", HEAD="#79b8ff",
        ACCENT="#388bfd", ACCENT_DK="#1f6feb", GOOD="#3fb950", GOOD_BG="#14301f", BAD="#f85149",
        BAD_BG="#3d1418", SEL_BG="#1c3358", CUR_BG="#4a4210", CHG_BG="#173824",
        SYN_KW="#7ee787", SYN_KWOP="#d2a8ff", SYN_BUILTIN="#56d364", SYN_STR="#ffa198",
        SYN_NUM="#79c0ff", SYN_COMMENT="#7d8590", SYN_DEF="#a5d6ff",
        B1="#2d6cdf", B2="#14a39a", B3="#d9730d", B4="#8957e5", B5="#2ea043", B6="#d12f7d",
    )
    PALETTES = {"light": LIGHT, "dark": DARK}
    CURRENT = {"name": "light"}


    def apply_palette(name):
        CURRENT["name"] = name
        globals().update(PALETTES[name])  # BG, CARD, TEXT, ... become module-level names


    def system_theme():
        """'dark' if Windows is set to dark app mode, else 'light'."""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
        except Exception:
            return "light"


    apply_palette("light")
    F = {}  # shared fonts (resizing them resizes the whole app)


    def make_fonts(root):
        fam = "Segoe UI"
        mono = "Consolas"
        F["ui"] = tkfont.Font(root=root, family=fam, size=11)
        F["bold"] = tkfont.Font(root=root, family=fam, size=11, weight="bold")
        F["h1"] = tkfont.Font(root=root, family=fam, size=20, weight="bold")
        F["h2"] = tkfont.Font(root=root, family=fam, size=13, weight="bold")
        F["code"] = tkfont.Font(root=root, family=mono, size=12)
        F["codeb"] = tkfont.Font(root=root, family=mono, size=12, weight="bold")
        F["codei"] = tkfont.Font(root=root, family=mono, size=12, slant="italic")


    def shade(color, factor):
        h = color.lstrip("#")
        rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * factor))) for c in rgb)

    APP = {"root": None}


    def row_height():
        return F["ui"].metrics("linespace") + 10


    def scale_trees(widget, ratio):
        """Keep table columns proportional when the text size changes."""
        if isinstance(widget, ttk.Treeview):
            for col in widget["columns"]:
                c = widget.column(col)
                widget.column(col, width=int(c["width"] * ratio), minwidth=int(c["minwidth"] * ratio))
        for child in widget.winfo_children():
            scale_trees(child, ratio)


    def resize_fonts(delta):
        old = abs(F["ui"].cget("size"))
        for f in F.values():
            f.configure(size=max(8, min(26, abs(f.cget("size")) + delta)))
        new = abs(F["ui"].cget("size"))
        root = APP["root"]
        if root is not None and new != old:
            ttk.Style(root).configure("Treeview", rowheight=row_height())  # taller rows for bigger text
            scale_trees(root, new / old)


    def make_tile(parent, title, subtitle, color_key, command):
        """A big colored button whose text WRAPS instead of being cut off at large text sizes."""
        col = globals()[color_key]
        tile = tk.Frame(parent, bg=col, cursor="hand2", padx=16, pady=12)
        top = tk.Label(tile, text=title, font=F["h2"], bg=col, fg="#fefefe", anchor="w", justify="left")
        sub = tk.Label(tile, text=subtitle, font=F["bold"], bg=col, fg="#fefefe", anchor="w", justify="left")
        top.pack(fill="x")
        sub.pack(fill="x")
        parts = (tile, top, sub)

        def paint(factor):
            c = globals()[color_key]
            c = c if factor == 1 else shade(c, factor)
            for w in parts:
                w.configure(bg=c)
        hover = lambda: 0.88 if CURRENT["name"] == "light" else 1.2  # noqa: E731
        for w in parts:
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>", lambda e: paint(hover()))
            w.bind("<Leave>", lambda e: paint(1))
        tile.bind("<Configure>", lambda e: (top.configure(wraplength=max(120, e.width - 40)),
                                            sub.configure(wraplength=max(120, e.width - 40))))
        return tile



    def style_app(root):
        st = ttk.Style(root)
        st.theme_use("clam")
        root.configure(bg=BG)
        root.option_add("*TCombobox*Listbox.background", CARD)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        hover = 0.86 if CURRENT["name"] == "light" else 1.18
        st.configure(".", background=BG, foreground=TEXT, font=F["ui"], bordercolor=LINE,
                     lightcolor=BG, darkcolor=BG, troughcolor=LINE, focuscolor=BG)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=TEXT, font=F["ui"])
        st.configure("TButton", background=CARD, foreground=TEXT, font=F["ui"], padding=(12, 6),
                     bordercolor=LINE, lightcolor=CARD, darkcolor=CARD)
        st.map("TButton", background=[("active", SEL_BG), ("disabled", BG)], foreground=[("disabled", MUTED)])
        st.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", font=F["bold"],
                     padding=(14, 8), bordercolor=ACCENT_DK, lightcolor=ACCENT, darkcolor=ACCENT)
        st.map("Accent.TButton", background=[("active", ACCENT_DK), ("disabled", MUTED)],
               foreground=[("disabled", "#ffffff")])
        for i in range(1, 7):
            col = globals()[f"B{i}"]
            st.configure(f"Big{i}.TButton", background=col, foreground="#ffffff", font=F["h2"],
                         padding=(14, 14), bordercolor=col, lightcolor=col, darkcolor=col)
            st.map(f"Big{i}.TButton", background=[("active", shade(col, hover))])
        st.configure("Treeview", font=F["ui"], rowheight=row_height(), background=CARD, fieldbackground=CARD,
                     foreground=TEXT, bordercolor=LINE)
        st.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        st.configure("Treeview.Heading", font=F["bold"], background=LINE, foreground=TEXT, relief="flat")
        st.map("Treeview.Heading", background=[("active", SEL_BG)])
        st.configure("TLabelframe", background=BG, bordercolor=LINE)
        st.configure("TLabelframe.Label", background=BG, font=F["bold"], foreground=MUTED)
        for name in ("TEntry", "TSpinbox", "TCombobox"):
            st.configure(name, fieldbackground=CARD, foreground=TEXT, insertcolor=TEXT, bordercolor=LINE,
                         arrowcolor=TEXT, background=CARD)
        st.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", TEXT)])
        st.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=CARD, indicatorforeground=TEXT,
                     bordercolor=MUTED, indicatormargin=(0, 0, 8, 0), indicatorsize=18)
        st.map("TCheckbutton", background=[("active", BG)],
               indicatorbackground=[("selected", ACCENT), ("!selected", CARD)])
        st.configure("TScrollbar", background=LINE, troughcolor=BG, bordercolor=BG, arrowcolor=TEXT)
        st.map("TScrollbar", background=[("active", MUTED)])
        st.configure("TSeparator", background=LINE)
        st.configure("TPanedwindow", background=BG)
        st.configure("Sash", background=LINE)
        st.configure("TNotebook", background=BG, bordercolor=LINE)
        st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(14, 6), font=F["bold"])
        st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", TEXT)])


    # --- coloring SQL ---------------------------------------------------------------------------
    SQL_KW = {"SELECT", "DISTINCT", "FROM", "WHERE", "GROUP", "BY", "HAVING", "ORDER", "LIMIT", "AS", "ASC", "DESC",
              "NULL", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "ON", "UNION", "ALL", "CASE", "WHEN", "THEN", "ELSE", "END"}
    SQL_OPS = {"AND", "OR", "NOT", "IN", "LIKE", "BETWEEN", "IS", "EXISTS"}
    SQL_FUNCS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "UPPER", "LOWER", "LENGTH", "COALESCE", "ABS"}
    TOKEN_RE = re.compile(r"(?P<comment>--[^\n]*)|(?P<string>'(?:[^']|'')*'?)|(?P<number>\b\d+(?:\.\d+)?\b)|"
                          r"(?P<word>[A-Za-z_][A-Za-z0-9_]*)")
    SYNTAX_TAGS = ("kw", "kwop", "builtin", "string", "number", "comment", "defname")


    def code_tags(txt):
        txt.tag_configure("kw", foreground=SYN_KW, font=F["codeb"])
        txt.tag_configure("kwop", foreground=SYN_KWOP, font=F["codeb"])
        txt.tag_configure("builtin", foreground=SYN_BUILTIN)
        txt.tag_configure("string", foreground=SYN_STR)
        txt.tag_configure("number", foreground=SYN_NUM)
        txt.tag_configure("comment", foreground=SYN_COMMENT, font=F["codei"])
        txt.tag_configure("defname", foreground=SYN_DEF, font=F["codeb"])
        txt.tag_configure("cur", background=CUR_BG)
        txt.tag_raise("kw")


    def highlight_sql(txt, sql, base="1.0"):
        """Color `sql`, which sits in `txt` starting at index `base`."""
        for m in TOKEN_RE.finditer(sql):
            kind = m.lastgroup
            word = m.group().upper()
            tag = None
            if kind == "comment":
                tag = "comment"
            elif kind == "string":
                tag = "string"
            elif kind == "number":
                tag = "number"
            elif word in SQL_OPS:
                tag = "kwop"
            elif word in SQL_KW:
                tag = "kw"
            elif word in SQL_FUNCS:
                tag = "builtin"
            elif m.group().lower() in core.SCHEMAS:
                tag = "defname"
            if tag:
                txt.tag_add(tag, f"{base}+{m.start()}c", f"{base}+{m.end()}c")


    def clear_syntax(txt):
        for tag in SYNTAX_TAGS:
            txt.tag_remove(tag, "1.0", "end")


    # --- switching theme -------------------------------------------------------------------------
    COLOR_OPTIONS = ("bg", "fg", "background", "foreground", "highlightbackground", "highlightcolor",
                     "insertbackground", "selectbackground", "selectforeground", "activebackground",
                     "activeforeground", "troughcolor", "disabledforeground")


    def recolor(widget, mapping):
        try:
            keys = widget.keys()
        except Exception:
            keys = []
        for opt in COLOR_OPTIONS:
            if opt in keys:
                try:
                    cur = str(widget.cget(opt)).lower()
                    if cur in mapping:
                        widget.configure(**{opt: mapping[cur]})
                except tk.TclError:
                    pass
        if isinstance(widget, tk.Text):
            for tag in widget.tag_names():
                for opt in ("background", "foreground"):
                    try:
                        cur = str(widget.tag_cget(tag, opt)).lower()
                        if cur in mapping:
                            widget.tag_configure(tag, **{opt: mapping[cur]})
                    except tk.TclError:
                        pass
        if getattr(widget, "_theme_btn", False):
            widget.configure(text=theme_button_text())
        for child in widget.winfo_children():
            recolor(child, mapping)


    def theme_button_text():
        return "Light mode" if CURRENT["name"] == "dark" else "Dark mode"


    def set_theme(root, name):
        old, new = PALETTES[CURRENT["name"]], PALETTES[name]
        mapping = {old[k].lower(): new[k] for k in old}
        apply_palette(name)
        style_app(root)
        recolor(root, mapping)


    # --- small widget helpers --------------------------------------------------------------------
    def ro_text(parent, height, font=None, bg=None, **kw):
        """Read-only Text widget with a scrollbar."""
        box = ttk.Frame(parent)
        kw.setdefault("wrap", "word")
        txt = tk.Text(box, height=height, font=font or F["ui"], bg=bg or CARD, fg=TEXT, insertbackground=TEXT,
                      relief="solid", bd=1, highlightthickness=0, padx=8, pady=6, **kw)
        sb = ttk.Scrollbar(box, command=txt.yview)
        txt.configure(yscrollcommand=sb.set, state="disabled")
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        return box, txt


    def make_grid(parent, height=8, hscroll=True):
        """A result-set grid: Treeview with scrollbars. -> (frame, tree)."""
        box = ttk.Frame(parent)
        tree = ttk.Treeview(box, show="headings", height=height)
        vs = ttk.Scrollbar(box, command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        if hscroll:
            hs = ttk.Scrollbar(box, orient="horizontal", command=tree.xview)
            tree.configure(xscrollcommand=hs.set)
            hs.pack(side="bottom", fill="x")
        vs.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return box, tree


    def fill_grid(tree, cols, rows):
        tree.delete(*tree.get_children())
        ids = [f"c{i}" for i in range(len(cols))]
        tree.configure(columns=ids)
        for i, name in enumerate(cols):
            cw = F["bold"].measure("0")
            width = max([len(name) + 2] + [len(core.fmt(r[i])) for r in rows[:50]])
            tree.heading(ids[i], text=name, anchor="w")
            tree.column(ids[i], width=max(cw * 8, min(cw * 34, cw * width + 24)), minwidth=cw * 4, anchor="w", stretch=False)
        for r in rows:
            tree.insert("", "end", values=[core.fmt(v) for v in r])


    def schema_line(name):
        return f"{name}(" + ", ".join(f"{c} {t}" for c, t in core.SCHEMAS[name]) + ")"


    class ScrollFrame(ttk.Frame):
        """A vertically scrollable area. Put content in .body"""

        def __init__(self, parent):
            super().__init__(parent)
            self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
            self.sb = ttk.Scrollbar(self, command=self.canvas.yview)
            self.canvas.configure(yscrollcommand=self.sb.set)
            self.sb.pack(side="right", fill="y")
            self.canvas.pack(side="left", fill="both", expand=True)
            self.body = ttk.Frame(self.canvas, padding=(24, 12))
            self.win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
            self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
            self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))

        def scroll(self, units):
            if self.body.winfo_reqheight() > self.canvas.winfo_height():
                self.canvas.yview_scroll(units, "units")


    def parse_inputs(raw):
        return [v.strip() for v in raw.split(",")] if raw.strip() else []


    # ===========================================================================
    # SQL LAB (the "dev mode" of this tool)
    # ===========================================================================
    EXAMPLES = [
        ("Everything in a table", "SELECT *\nFROM employees"),
        ("WHERE + ORDER BY", core.sq("first_name, salary", "employees", "department = 'IT'", order="salary DESC")),
        ("Aggregate with no GROUP BY", "SELECT COUNT(*), AVG(salary)\nFROM employees"),
        ("COUNT(*) vs COUNT(column) and NULLs", "SELECT COUNT(*), COUNT(bonus), AVG(bonus)\nFROM employees"),
        ("GROUP BY", core.sq("department, COUNT(*)", "employees", group="department")),
        ("GROUP BY + HAVING", core.sq("department, AVG(salary)", "employees", group="department", having="AVG(salary) > 60000")),
        ("WHERE and HAVING together", core.sq("customer_name, SUM(total)", "orders", "status = 'Shipped'", "customer_name",
                                              "SUM(total) > 200", "customer_name")),
        ("DISTINCT", core.sq("DISTINCT department", "employees", order="department")),
        ("LIKE wildcards", core.sq("product_name", "products", "product_name LIKE '%board'")),
        ("BETWEEN and IN", core.sq("product_name, price", "products", "price BETWEEN 8.99 AND 19.99 OR category IN ('Furniture')",
                                   order="price")),
    ]


    class SqlLab(tk.Toplevel):
        def __init__(self, app, sql=None, heading="SQL Lab"):
            super().__init__(app.root)
            self.app, self.sb = app, core.db()
            self.stages, self.k = None, 0
            self.title("SQL Lab  -  " + heading)
            self.geometry("1360x860")
            self.minsize(1000, 680)
            self.configure(bg=BG)
            self._pending = []
            self._build(heading)
            self.editor.insert("1.0", sql or EXAMPLES[1][1])
            self.recolor_editor()
            self.run_query()
            self.lift()
            self.focus_force()

        # --- layout ------------------------------------------------------------
        def _build(self, heading):
            top = ttk.Frame(self, padding=(14, 10, 14, 4))
            top.pack(fill="x")
            ttk.Label(top, text="SQL Lab  -  " + heading, font=F["h2"], foreground=HEAD, wraplength=900,
                      justify="left").pack(side="left")
            self.app.theme_button(top).pack(side="right", padx=8)
            ttk.Button(top, text="A+", width=3, command=lambda: resize_fonts(1)).pack(side="right", padx=2)
            ttk.Button(top, text="A-", width=3, command=lambda: resize_fonts(-1)).pack(side="right", padx=2)
            hint = tk.Label(self, bg=BG, fg=MUTED, font=F["ui"], anchor="w", justify="left", wraplength=1200,
                            text="Run any SELECT against the sample database.   Ctrl+Enter = run    F6 = step through    "
                                 "Right / Left = next / back step    Esc = close")
            hint.pack(fill="x", padx=14)
            self.bind("<Configure>", lambda e: hint.configure(wraplength=max(300, self.winfo_width() - 40))
                      if e.widget is self else None)
            main = ttk.PanedWindow(self, orient="horizontal")
            main.pack(fill="both", expand=True, padx=14, pady=8)

            left = ttk.Frame(main)
            main.add(left, weight=1)
            ttk.Label(left, text="QUERY", foreground=MUTED, font=F["bold"]).pack(anchor="w")
            ebox = ttk.Frame(left)
            self.editor = tk.Text(ebox, height=9, font=F["code"], bg=CARD, fg=TEXT, insertbackground=TEXT, relief="solid",
                                  bd=1, highlightthickness=0, padx=8, pady=6, wrap="none", undo=True)
            esb = ttk.Scrollbar(ebox, command=self.editor.yview)
            self.editor.configure(yscrollcommand=esb.set)
            esb.pack(side="right", fill="y")
            self.editor.pack(side="left", fill="both", expand=True)
            ebox.pack(fill="x")
            code_tags(self.editor)
            self.editor.bind("<KeyRelease>", self._schedule)
            self.editor.bind("<Control-Return>", lambda e: (self.run_query(), "break")[1])
            self.editor.bind("<Tab>", lambda e: (self.editor.insert("insert", "    "), "break")[1])
            self.bind("<F5>", lambda e: self.run_query())
            self.bind("<F6>", lambda e: self.start_steps())
            self.bind("<Escape>", lambda e: self.destroy())
            self.bind("<Right>", lambda e: self._key(self.next))
            self.bind("<Left>", lambda e: self._key(self.prev))
            self.bind("<Control-equal>", lambda e: resize_fonts(1))
            self.bind("<Control-minus>", lambda e: resize_fonts(-1))
            row = ttk.Frame(left)
            row.pack(fill="x", pady=8)
            ttk.Button(row, text="Run  (Ctrl+Enter)", style="Accent.TButton", command=self.run_query).pack(side="left")
            ttk.Button(row, text="Step through it (F6)", command=self.start_steps).pack(side="left", padx=8)
            self.example = ttk.Combobox(row, state="readonly", width=34, values=[n for n, _ in EXAMPLES])
            self.example.set("Load an example query...")
            self.example.bind("<<ComboboxSelected>>", self._load_example)
            self.example.pack(side="right")

            ttk.Label(left, text="SAMPLE DATABASE", foreground=MUTED, font=F["bold"]).pack(anchor="w", pady=(6, 0))
            nb = ttk.Notebook(left)
            nb.pack(fill="both", expand=True)
            for name in core.SCHEMAS:
                page = ttk.Frame(nb, padding=6)
                nb.add(page, text=name)
                tk.Label(page, text=schema_line(name), font=F["code"], bg=BG, fg=MUTED, anchor="w", justify="left",
                         wraplength=560).pack(fill="x", pady=(0, 4))
                box, tree = make_grid(page, height=7)
                box.pack(fill="both", expand=True)
                cols, rows, _ = self.sb.table_rows(name)
                fill_grid(tree, cols, rows)

            right = ttk.Frame(main)
            main.add(right, weight=1)
            self.tabs = ttk.Notebook(right)
            self.tabs.pack(fill="both", expand=True)
            # result tab
            res = ttk.Frame(self.tabs, padding=8)
            self.tabs.add(res, text="Result")
            self.status = tk.Label(res, text="", font=F["bold"], bg=BG, fg=TEXT, anchor="w", justify="left", wraplength=640)
            self.status.pack(fill="x", pady=(0, 6))
            res.bind("<Configure>", lambda e: self.status.configure(wraplength=max(300, e.width - 30)))
            box, self.grid = make_grid(res, height=14)
            box.pack(fill="both", expand=True)
            # step tab
            st = ttk.Frame(self.tabs, padding=8)
            self.tabs.add(st, text="Steps")
            self.step_title = tk.Label(st, text="", font=F["h2"], bg=BG, fg=HEAD, anchor="w", justify="left", wraplength=640)
            self.step_title.pack(fill="x")
            self.step_text = tk.Label(st, text="", font=F["ui"], bg=BG, fg=TEXT, anchor="w", justify="left", wraplength=640)
            self.step_text.pack(fill="x", pady=(2, 8))
            st.bind("<Configure>", lambda e: (self.step_title.configure(wraplength=max(300, e.width - 30)),
                                              self.step_text.configure(wraplength=max(300, e.width - 30))))
            nav = ttk.Frame(st)
            nav.pack(side="bottom", fill="x", pady=(8, 0))
            self.btn_prev = ttk.Button(nav, text="<  Back", command=self.prev)
            self.btn_next = ttk.Button(nav, text="Next step  >", style="Accent.TButton", command=self.next)
            self.btn_prev.pack(side="left")
            self.btn_next.pack(side="left", padx=8)
            self.counter = ttk.Label(nav, text="", font=F["bold"])
            self.counter.pack(side="left", padx=8)
            self.step_note = ttk.Label(st, text="Rows after this step:", foreground=MUTED, font=F["bold"])
            self.step_note.pack(anchor="w")
            box, self.step_grid = make_grid(st, height=12)
            box.pack(fill="both", expand=True)
            # read tab
            rd = ttk.Frame(self.tabs, padding=8)
            self.tabs.add(rd, text="Read query")
            box, self.read = ro_text(rd, 12)
            self.read.tag_configure("h", font=F["bold"], foreground=HEAD, spacing1=8)
            box.pack(fill="both", expand=True)

        def _key(self, fn):
            if isinstance(self.focus_get(), (tk.Text, tk.Entry, ttk.Entry, ttk.Combobox)):
                return
            fn()

        def _load_example(self, _):
            sql = dict(EXAMPLES)[self.example.get()]
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", sql)
            self.recolor_editor()
            self.run_query()
            self.example.selection_clear()

        # --- editor ------------------------------------------------------------
        def _schedule(self, _=None):
            if not self._pending:
                self._pending.append(self.after(120, self.recolor_editor))

        def recolor_editor(self):
            self._pending.clear()
            clear_syntax(self.editor)
            highlight_sql(self.editor, self.editor.get("1.0", "end-1c"))

        def sql_text(self):
            return self.editor.get("1.0", "end-1c").rstrip().rstrip(";")

        # --- running -----------------------------------------------------------
        def run_query(self):
            self.stages = None
            self.editor.tag_remove("cur", "1.0", "end")
            sql = self.sql_text()
            try:
                cols, rows, trunc = self.sb.run(sql)
                fill_grid(self.grid, cols, rows)
                msg = f"{len(rows)} row{'s' if len(rows) != 1 else ''} x {len(cols)} column{'s' if len(cols) != 1 else ''}"
                if trunc:
                    msg += "   (showing the first 500)"
                self.status.configure(text=msg, fg=TEXT)
            except core.SqlError as e:
                fill_grid(self.grid, [], [])
                self.status.configure(text="Error: " + str(e), fg=BAD)
            txt = self.read
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            for head, body in core.read_query(self.sb, sql):
                txt.insert("end", head + "\n", "h")
                txt.insert("end", body + "\n")
            txt.configure(state="disabled")
            self.tabs.select(0)
            self.step_title.configure(text="")
            self.step_text.configure(text="Press  'Step through it'  to watch this query run clause by clause.")
            fill_grid(self.step_grid, [], [])
            self.counter.configure(text="")
            self.btn_prev.state(["disabled"])
            self.btn_next.state(["disabled"])

        def start_steps(self):
            sql = self.sql_text()
            self.stages = core.plan_stages(self.sb, sql)
            if not self.stages:
                self.tabs.select(1)
                self.step_title.configure(text="No steps for this query")
                self.step_text.configure(text="Step-by-step works for a single SELECT ... FROM ... query with its clauses "
                                              "in the usual order. Check the Result tab for the message.")
                return
            self.k = 0
            self.tabs.select(1)
            self.render()

        def next(self):
            if self.stages and self.k < len(self.stages) - 1:
                self.k += 1
                self.render()

        def prev(self):
            if self.stages and self.k > 0:
                self.k -= 1
                self.render()

        def render(self):
            s, n = self.stages[self.k], len(self.stages)
            self.step_title.configure(text=f"Step {s['step']} of {s['of']}:  {s['title']}")
            self.step_text.configure(text=s["error"] and ("This step fails: " + s["error"]) or s["text"])
            fill_grid(self.step_grid, s["cols"], s["rows"])
            self.step_note.configure(text=f"Rows after this step: {s['n']}" if not s["error"] else "")
            self.counter.configure(text=f"{self.k + 1} / {n}")
            self.btn_prev.state(["!disabled"] if self.k > 0 else ["disabled"])
            self.btn_next.state(["!disabled"] if self.k < n - 1 else ["disabled"])
            self.editor.tag_remove("cur", "1.0", "end")
            if s["span"]:
                a, b = s["span"]
                self.editor.tag_add("cur", f"1.0+{a}c", f"1.0+{b}c")
                self.editor.see(f"1.0+{a}c")


    # ===========================================================================
    # MAIN APP
    # ===========================================================================
    SQL_KINDS = {"sql_result", "sql_rows", "sql_which", "sql_english", "sql_error", "interpret"}
    SHORT = {"W1": "Week 1", "W2": "Week 2", "W3": "Week 3", "W4": "Week 4", "W5": "Week 5", "W6": "Week 6",
             "AG": "Additional"}
    BUTTON_NAMES = {"W1": "Week 1: Computing", "W2": "Week 2: Socio-Technical", "W3": "Week 3: Reqs & Rules",
                    "W4": "Week 4: Theories", "W5": "Week 5: SQL Intro", "W6": "Week 6: SQL Coding II",
                    "AG": "Types & Reading Queries"}
    LETTERS = "ABCDEFGH"


    class App:
        def __init__(self):
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
            self.root = tk.Tk()
            self.root.title("IS 4420 - Midterm Practice Exam")
            self.root.geometry("1120x860")
            self.root.minsize(860, 660)
            self.root.report_callback_exception = self._report
            APP["root"] = self.root
            apply_palette(system_theme())
            make_fonts(self.root)
            style_app(self.root)
            self.mode, self.frame, self.scroller = "home", None, None
            self.wrap_labels, self.card_labels = [], []
            self.shuffle_q = tk.BooleanVar(value=True)
            self.shuffle_c = tk.BooleanVar(value=True)
            self.exam_n = tk.IntVar(value=40)
            self.root.bind("<Key>", self._on_key)
            self.root.bind("<F2>", lambda e: self.open_lab())
            self.root.bind("<Control-equal>", lambda e: resize_fonts(1))
            self.root.bind("<Control-minus>", lambda e: resize_fonts(-1))
            self.root.bind("<Configure>", self._on_resize)
            self.root.bind_all("<MouseWheel>", self._wheel)
            self.root.bind_all("<Button-4>", lambda e: self._wheel(e, 1))
            self.root.bind_all("<Button-5>", lambda e: self._wheel(e, -1))
            self.show_home()

        # --- helpers -----------------------------------------------------------
        def _report(self, exc, val, tb):
            import traceback
            detail = "".join(traceback.format_exception(exc, val, tb))
            try:
                messagebox.showerror("Something went wrong", "The app hit an unexpected error but is still running.\n\n"
                                     + detail[-1500:])
            except Exception:
                pass

        def _wheel(self, e, direction=None):
            sc = self.scroller
            if sc is None or not sc.winfo_exists():
                return
            w = self.root.winfo_containing(e.x_root, e.y_root)
            if w is None or isinstance(w, (tk.Text, ttk.Treeview, tk.Listbox, ttk.Combobox)) or not str(w).startswith(str(sc)):
                return
            sc.scroll(direction * -1 if direction else int(-e.delta / 120))

        def theme_button(self, parent):
            btn = ttk.Button(parent, text=theme_button_text(), command=self.toggle_theme)
            btn._theme_btn = True
            return btn

        def toggle_theme(self):
            set_theme(self.root, "light" if CURRENT["name"] == "dark" else "dark")

        def clear(self):
            if self.frame is not None:
                self.frame.destroy()
            self.frame = ttk.Frame(self.root, padding=(24, 16))
            self.frame.pack(fill="both", expand=True)
            self.wrap_labels, self.card_labels, self.scroller = [], [], None

        def wlabel(self, parent, text, font=None, fg=None, bg=None, **kw):
            lbl = tk.Label(parent, text=text, font=font or F["ui"], fg=fg or TEXT, bg=bg or BG, justify="left",
                           anchor="w", **kw)
            self.wrap_labels.append(lbl)
            lbl.configure(wraplength=max(300, self.root.winfo_width() - 110))
            return lbl

        def _on_resize(self, e):
            if e.widget is self.root:
                for lbl in self.wrap_labels:
                    try:
                        lbl.configure(wraplength=max(300, e.width - 110))
                    except tk.TclError:
                        pass
                for lbl in self.card_labels:
                    try:
                        lbl.configure(wraplength=max(300, e.width - 190))
                    except tk.TclError:
                        pass

        def _typing(self):
            return isinstance(self.root.focus_get(), (tk.Text, tk.Entry, ttk.Entry, tk.Spinbox, ttk.Spinbox, ttk.Combobox))

        def _on_key(self, e):
            if self.mode != "quiz" or self._typing():
                return
            ch = e.char.upper()
            if not self.answered and ch and ch in LETTERS[:len(self.cur_choices)]:
                self.select(LETTERS.index(ch))
            elif e.keysym in ("Return", "KP_Enter"):
                (self.next_q if self.answered else self.submit)()

        def open_lab(self, sql=None, heading="free practice"):
            if sql is None and self.mode == "quiz":
                q = self.current_q()
                sql, heading = q.get("sql"), f"{core.TOPICS[q['topic']].split(':')[0]} question"
            SqlLab(self, sql, heading)

        # --- home --------------------------------------------------------------
        def show_home(self):
            self.mode = "home"
            self.clear()
            self.frame.configure(padding=0)
            sf = ScrollFrame(self.frame)
            sf.pack(fill="both", expand=True)
            self.scroller = sf
            f = sf.body
            head = ttk.Frame(f)
            head.pack(fill="x")
            ttk.Label(head, text="IS 4420  -  Midterm Practice Exam", font=F["h1"], foreground=HEAD).pack(side="left")
            self.theme_button(head).pack(side="right")
            self.wlabel(f, "Practice by week, take a full mixed exam, or open the SQL Lab (F2) any time to run a query "
                           "and watch it execute clause by clause.", fg=MUTED).pack(fill="x", pady=(2, 10))
            opts = ttk.LabelFrame(f, text="Options", padding=10)
            opts.pack(fill="x")
            ttk.Checkbutton(opts, text="Shuffle question order", variable=self.shuffle_q).grid(row=0, column=0, sticky="w", padx=6)
            ttk.Checkbutton(opts, text="Shuffle answer letters", variable=self.shuffle_c).grid(row=0, column=1, sticky="w", padx=6)
            ttk.Label(opts, text="Questions in the full practice exam:").grid(row=0, column=2, padx=(24, 4))
            ttk.Spinbox(opts, from_=5, to=len(core.BANK), width=5, textvariable=self.exam_n).grid(row=0, column=3)

            grid = ttk.Frame(f)
            grid.pack(fill="x", pady=14)
            for c in range(3):
                grid.columnconfigure(c, weight=1, uniform="a")
            by = self.by_topic()
            sql_n = sum(1 for q in core.BANK if q["kind"] in SQL_KINDS)
            items = [("Full Practice Exam\nmixed, by topic weight", self.start_exam),
                     (f"SQL Query Skills\n{sql_n} query questions", self.start_sql),
                     ("SQL Lab\nrun and step through", lambda: self.open_lab(None, "free practice"))]
            for key in core.TOPICS:
                items.append((f"{BUTTON_NAMES[key]}\n{len(by[key])} questions", lambda k=key: self.start_topic(k)))
            items.append(("Study Reference\npattern + cheat sheets", self.show_reference))
            for i, (txt, cmd) in enumerate(items):
                title, _, sub = txt.partition("\n")
                make_tile(grid, title, sub, f"B{i % 6 + 1}", cmd).grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)
            ttk.Label(f, text="Tips:  F2 = SQL Lab   |   A-F = pick an answer   |   Enter = submit / next   |   Ctrl +/- = text size",
                      foreground=MUTED).pack(anchor="w")
            self.wlabel(f, "Heads-up: concept questions use standard textbook wording, so double-check terms against your "
                           "lecture slides. SQL runs on SQLite (the course uses MySQL; these queries behave the same).",
                        fg=MUTED).pack(fill="x", pady=(6, 0))

        @staticmethod
        def by_topic():
            out = {k: [] for k in core.TOPICS}
            for q in core.BANK:
                out[q["topic"]].append(q)
            return out

        def start_exam(self):
            try:
                n = max(5, min(len(core.BANK), int(self.exam_n.get())))
            except (tk.TclError, ValueError):
                n = 40
            by, total, pool = self.by_topic(), sum(core.PRACTICE_QUOTA.values()), []
            for key, share in core.PRACTICE_QUOTA.items():
                pool += random.sample(by[key], min(len(by[key]), max(1, round(n * share / total))))
            random.shuffle(pool)
            self.start_quiz(pool[:n], "Full Practice Exam")

        def start_sql(self):
            self.start_quiz([q for q in core.BANK if q["kind"] in SQL_KINDS], "SQL Query Skills")

        def start_topic(self, key):
            self.start_quiz(list(self.by_topic()[key]), core.TOPICS[key])

        # --- quiz --------------------------------------------------------------
        def start_quiz(self, pool, title, shuffle_q=None):
            self.title_text = title
            self.order = pool[:]
            if self.shuffle_q.get() if shuffle_q is None else shuffle_q:
                random.shuffle(self.order)
            self.i, self.score, self.answered_count, self.missed = 0, 0, 0, []
            self.stats = {}
            self.show_question()

        def current_q(self):
            return self.order[self.i]

        def show_question(self):
            self.mode = "quiz"
            self.clear()
            q = self.current_q()
            self.answered, self.selected = False, None
            choices = q["choices"][:]
            if self.shuffle_c.get():
                random.shuffle(choices)
            self.cur_choices = choices
            self.correct_idx = [i for i, c in enumerate(choices) if c in q["answer"]]
            self.frame.configure(padding=0)
            sf = ScrollFrame(self.frame)
            sf.pack(fill="both", expand=True)
            self.scroller = sf
            f = sf.body

            info = ttk.Frame(f)
            info.pack(fill="x")
            ttk.Label(info, text=f"Question {self.i + 1} of {len(self.order)}   |   {SHORT[q['topic']]}",
                      font=F["bold"], foreground=HEAD).pack(side="left")
            self.score_lbl = ttk.Label(info, text=self._score_text(), foreground=MUTED, font=F["bold"])
            self.score_lbl.pack(side="right")
            bar = ttk.Frame(f)
            bar.pack(fill="x", pady=(6, 0))
            ttk.Button(bar, text="SQL Lab  (F2)", style="Accent.TButton", command=self.open_lab).pack(side="right")
            ttk.Button(bar, text="Home", command=self.confirm_home).pack(side="right", padx=8)
            self.theme_button(bar).pack(side="right")
            ttk.Separator(f).pack(fill="x", pady=8)
            self.wlabel(f, q["prompt"], font=F["h2"]).pack(fill="x", pady=(0, 8))

            if q["code"]:
                lines = q["code"].split("\n")
                txt = tk.Text(f, height=len(lines), font=F["code"], bg=CARD, fg=TEXT, insertbackground=TEXT,
                              relief="solid", bd=1, highlightthickness=0, padx=10, pady=8, wrap="none")
                code_tags(txt)
                txt.insert("1.0", q["code"])
                highlight_sql(txt, q["code"])
                txt.configure(state="disabled")
                txt.pack(fill="x", pady=(0, 8))
            if q["grid"]:
                ttk.Label(f, text="RESULT SET", foreground=MUTED, font=F["bold"]).pack(anchor="w")
                cols, rows = q["grid"]
                box, tree = make_grid(f, height=min(max(len(rows), 1), 8) + 1, hscroll=False)
                fill_grid(tree, cols, rows)
                box.pack(fill="x", pady=(0, 8))
            if q["tables"]:
                self._tables_panel(f, q["tables"])

            self.cards = []
            cf = ttk.Frame(f)
            cf.pack(fill="x", pady=10)
            for i, ch in enumerate(choices):
                card = tk.Frame(cf, bg=CARD, bd=1, relief="solid", cursor="hand2")
                card.pack(fill="x", pady=3)
                letter = tk.Label(card, text=LETTERS[i], font=F["h2"], bg=CARD, width=3, fg=ACCENT)
                letter.pack(side="left")
                body = tk.Label(card, text=ch, font=F["code"] if q["mono"] else F["ui"], bg=CARD, fg=TEXT,
                                justify="left", anchor="w", wraplength=max(300, self.root.winfo_width() - 190))
                body.pack(side="left", fill="x", expand=True, pady=6)
                self.card_labels.append(body)
                for w in (card, letter, body):
                    w.bind("<Button-1>", lambda e, i=i: self.select(i))
                self.cards.append((card, letter, body))
            self.btn_row = ttk.Frame(f)
            self.btn_row.pack(fill="x", pady=4)
            self.submit_btn = ttk.Button(self.btn_row, text="Submit answer", style="Accent.TButton",
                                         command=self.submit, state="disabled")
            self.submit_btn.pack(side="left")
            ttk.Button(self.btn_row, text="Skip", command=self.skip).pack(side="left", padx=8)
            self.result_holder = ttk.Frame(f)
            self.result_holder.pack(fill="both", expand=True)

        def _tables_panel(self, parent, names):
            box = ttk.Frame(parent)
            box.pack(fill="x", pady=(0, 6))
            for name in names:
                self.wlabel(box, schema_line(name), font=F["code"], fg=MUTED).pack(fill="x")
            holder = ttk.Frame(box)
            state = {"open": False}
            btn = ttk.Button(box, text="Show table data")

            def toggle():
                if state["open"]:
                    holder.pack_forget()
                    btn.configure(text="Show table data")
                else:
                    if not holder.winfo_children():
                        nb = ttk.Notebook(holder)
                        nb.pack(fill="x")
                        for name in names:
                            page = ttk.Frame(nb, padding=4)
                            nb.add(page, text=name)
                            g, tree = make_grid(page, height=6)
                            g.pack(fill="x")
                            cols, rows, _ = core.db().table_rows(name)
                            fill_grid(tree, cols, rows)
                    holder.pack(fill="x", pady=4)
                    btn.configure(text="Hide table data")
                state["open"] = not state["open"]
            btn.configure(command=toggle)
            btn.pack(anchor="w", pady=(4, 0))

        def _score_text(self):
            return f"Score {self.score} / {self.answered_count}"

        def select(self, i):
            if self.answered:
                return
            self.selected = i
            for j, (card, letter, body) in enumerate(self.cards):
                col = SEL_BG if j == i else CARD
                for w in (card, letter, body):
                    w.configure(bg=col)
            self.submit_btn.configure(state="normal")

        def _color_cards(self):
            for j, (card, letter, body) in enumerate(self.cards):
                col = GOOD_BG if j in self.correct_idx else (BAD_BG if j == self.selected else CARD)
                for w in (card, letter, body):
                    w.configure(bg=col, cursor="arrow")

        def submit(self):
            if not self.answered and self.selected is not None:
                self._finish_question(self.selected)

        def skip(self):
            if not self.answered:
                self._finish_question(None)

        def _finish_question(self, guess):
            q = self.current_q()
            self.answered = True
            for w in self.btn_row.winfo_children():
                w.destroy()
            letters = "/".join(LETTERS[i] for i in self.correct_idx)
            stat = self.stats.setdefault(q["topic"], [0, 0])
            stat[1] += 1
            if guess is None:
                self.missed.append(q)
                msg, col = f"Skipped. The answer is {letters}.", MUTED
            else:
                self.answered_count += 1
                if guess in self.correct_idx:
                    self.score += 1
                    stat[0] += 1
                    msg, col = "Correct!", GOOD
                else:
                    self.missed.append(q)
                    msg, col = f"Not quite. The answer is {letters}.", BAD
            self.score_lbl.configure(text=self._score_text())
            self.selected = guess
            self._color_cards()
            last = self.i == len(self.order) - 1
            tk.Label(self.btn_row, text=msg, font=F["h2"], fg=col, bg=BG).pack(side="left", padx=(0, 16))
            ttk.Button(self.btn_row, text="See results" if last else "Next question  >", style="Accent.TButton",
                       command=self.next_q).pack(side="left")
            if q["sql"]:
                ttk.Button(self.btn_row, text="Run it in the SQL Lab", command=self.open_lab).pack(side="left", padx=8)
            if q["choice_sql"]:
                for (card, letter, body), ch in zip(self.cards, self.cur_choices):
                    ttk.Button(card, text="Try in lab", command=lambda s=ch: self.open_lab(s, "try this choice")).pack(
                        side="right", padx=8)
            rf = self.result_holder
            ttk.Label(rf, text="WHY", foreground=MUTED, font=F["bold"]).pack(anchor="w", pady=(10, 0))
            why = q["why"]
            if "\n\nActual result set:\n" in why:
                why, actual = why.split("\n\nActual result set:\n", 1)
                self.wlabel(rf, why).pack(fill="x")
                ttk.Label(rf, text="ACTUAL RESULT SET", foreground=MUTED, font=F["bold"]).pack(anchor="w", pady=(8, 0))
                box, txt = ro_text(rf, min(8, actual.count("\n") + 1), font=F["code"])
                txt.configure(state="normal")
                txt.insert("1.0", actual)
                txt.configure(state="disabled")
                box.pack(fill="x")
            else:
                self.wlabel(rf, why).pack(fill="x")

        def next_q(self):
            if not self.answered:
                return
            if self.i >= len(self.order) - 1:
                self.show_results()
            else:
                self.i += 1
                self.show_question()

        def confirm_home(self):
            if messagebox.askyesno("Leave quiz?", "Go back to the home screen? Your progress in this quiz will be lost."):
                self.show_home()

        def show_results(self):
            self.mode = "results"
            self.clear()
            f = self.frame
            top = ttk.Frame(f)
            top.pack(fill="x")
            ttk.Label(top, text="Results", font=F["h1"], foreground=HEAD).pack(side="left")
            self.theme_button(top).pack(side="right")
            if self.answered_count:
                pct = round(100 * self.score / self.answered_count)
                ttk.Label(f, text=f"{self.score} / {self.answered_count} answered correctly  ({pct}%)",
                          font=F["h2"]).pack(anchor="w", pady=6)
            if self.stats:
                ttk.Label(f, text="BY TOPIC (focus your studying on the low ones)", foreground=MUTED,
                          font=F["bold"]).pack(anchor="w", pady=(6, 2))
                for key, (good, total) in sorted(self.stats.items()):
                    tk.Label(f, text=f"{good}/{total}   {core.TOPICS[key]}", font=F["ui"], bg=BG, anchor="w",
                             fg=GOOD if good == total else (BAD if good / total < 0.6 else TEXT)).pack(fill="x")
            ttk.Label(f, text="MISSED OR SKIPPED  (double-click to open in the SQL Lab)", foreground=MUTED,
                      font=F["bold"]).pack(anchor="w", pady=(12, 2))
            tree = ttk.Treeview(f, columns=("t", "p"), show="headings", height=8)
            tree.heading("t", text="Topic")
            tree.heading("p", text="Question")
            tree.column("t", width=110, stretch=False)
            tree.column("p", width=700)
            for idx, q in enumerate(self.missed):
                tree.insert("", "end", iid=str(idx), values=(SHORT[q["topic"]], q["prompt"].split("\n")[0]))
            tree.pack(fill="both", expand=True)

            def open_sel(_=None):
                sel = tree.selection()
                if sel:
                    q = self.missed[int(sel[0])]
                    self.open_lab(q.get("sql"), "missed question")
            tree.bind("<Double-1>", open_sel)
            row = ttk.Frame(f)
            row.pack(fill="x", pady=12)
            if self.missed:
                ttk.Button(row, text="Retry missed questions", style="Accent.TButton",
                           command=lambda: self.start_quiz(self.missed[:], "Retry", shuffle_q=True)).pack(side="left")
            ttk.Button(row, text="Home", command=self.show_home).pack(side="right")

        # --- study reference ---------------------------------------------------
        def show_reference(self):
            self.mode = "reference"
            self.clear()
            f = self.frame
            top = ttk.Frame(f)
            top.pack(fill="x")
            ttk.Label(top, text="Study Reference", font=F["h1"], foreground=HEAD).pack(side="left")
            ttk.Button(top, text="Home", command=self.show_home).pack(side="right")
            self.theme_button(top).pack(side="right", padx=8)
            box, txt = ro_text(f, 20, wrap="word")
            box.pack(fill="both", expand=True, pady=8)
            code_tags(txt)
            txt.tag_configure("h", font=F["h2"], foreground=HEAD, spacing1=14, spacing3=4)
            txt.tag_configure("b", font=F["bold"])
            txt.tag_configure("m", font=F["code"])
            txt.configure(state="normal")
            for kind, text in REFERENCE:
                if kind == "h":
                    txt.insert("end", text + "\n", "h")
                elif kind == "sql":
                    start = txt.index("end-1c")
                    txt.insert("end", text + "\n", "m")
                    highlight_sql(txt, text, start)
                else:
                    txt.insert("end", text + "\n")
            txt.configure(state="disabled")
            ttk.Button(f, text="Open the SQL Lab", style="Accent.TButton", command=lambda: self.open_lab(None, "free practice")).pack(anchor="w")

        def run(self):
            self.root.mainloop()


    REFERENCE = [
        ("h", "The SELECT statement pattern"),
        ("sql", "SELECT [DISTINCT] columns   -- which COLUMNS to show (* = all)\n"
                "FROM table                  -- the base table (SELECT + FROM = minimum)\n"
                "WHERE row condition         -- filters ROWS (before grouping)\n"
                "GROUP BY columns            -- gathers rows into groups\n"
                "HAVING group condition      -- filters GROUPS (after grouping)\n"
                "ORDER BY columns [ASC|DESC] -- sorts the final result set"),
        ("t", "SELECT picks columns or expressions.  * returns all columns.  DISTINCT eliminates duplicate rows.  "
              "WHERE can use =, >, <, IN, BETWEEN, LIKE; compound conditions use AND / OR."),
        ("h", "Written order is NOT processing order"),
        ("t", "You WRITE:  SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY.\n"
              "SQL PROCESSES:  FROM -> WHERE -> GROUP BY -> HAVING -> SELECT -> DISTINCT -> ORDER BY.\n"
              "That is why WHERE can't use aggregates (no groups exist yet) but HAVING can, and why ORDER BY can use "
              "a column alias defined in SELECT.  Watch it happen: SQL Lab -> 'Step through it'."),
        ("h", "WHERE vs HAVING"),
        ("sql", "SELECT customer_name, SUM(total)\nFROM orders\nWHERE status = 'Shipped'  -- rows first\n"
                "GROUP BY customer_name\nHAVING SUM(total) > 200   -- then groups"),
        ("t", "WHERE filters individual rows BEFORE grouping.  HAVING filters whole groups AFTER grouping."),
        ("h", "LIKE wildcards"),
        ("sql", "WHERE last_name LIKE 'M%'   -- starts with M\n"
                "WHERE last_name LIKE '%son' -- ends with son\n"
                "WHERE last_name LIKE '_ee'  -- one character, then ee (Lee)"),
        ("t", "% matches any number of characters (even none).  _ matches exactly one character."),
        ("t", "BETWEEN a AND b is inclusive of both ends.  IN (...) matches any value in the list."),
        ("h", "Aggregate functions"),
        ("t", "COUNT(*)  counts rows  |  COUNT(column) counts non-NULL values  |  SUM(column) adds  |  "
              "AVG(column) averages (ignores NULL)  |  MIN / MAX  smallest / largest.\n"
              "With no GROUP BY, an aggregate collapses ALL rows into ONE row.  With GROUP BY, you get one row per group.  "
              "Every non-aggregated column in SELECT must be in GROUP BY."),
        ("h", "Reading a query (and a result set)"),
        ("t", "1. Which table(s)?  (FROM)    2. Which columns?  (SELECT)    3. Which rows / groups are kept?  "
              "(WHERE / HAVING)    4. How is it sorted?  (ORDER BY)    5. What would the result set look like?\n"
              "Going backwards from a result set: its column headings come from SELECT, its row count from WHERE / "
              "GROUP BY / HAVING / DISTINCT, and its order from ORDER BY."),
        ("h", "Query processing: engine vs interface"),
        ("t", "ENGINE (MySQL Server): stores the data and executes queries.   INTERFACE / CLIENT (MySQL Workbench, Excel, "
              "Tableau, Python...): sends your query to the engine and shows the result set.   A result set is a temporary "
              "table of the rows and columns you asked for; SELECT never changes the stored data."),
        ("h", "Data types"),
        ("t", "INT whole numbers  |  DECIMAL numbers with decimals (prices)  |  CHAR fixed-length text / VARCHAR variable-length "
              "text  |  DATE calendar dates  |  DATETIME dates + times."),
        ("h", "Set theory & relational theory"),
        ("t", "Set: distinct elements, no order.   Union = in either.   Intersection = in both.   Difference A - B = in A but not B.   "
              "Subset = all elements inside another set.   A table / result set is a set of rows.\n"
              "Relation = table, tuple = row, attribute = column, entity = a thing we store data about.   "
              "Primary key uniquely identifies rows (no NULLs).   Foreign key points to another table's primary key (goes on "
              "the MANY side).   Composite key = 2+ columns.\n"
              "Cardinality: one-to-one, one-to-many, many-to-many (resolved with a junction table)."),
        ("h", "Business requirements vs business rules"),
        ("t", "REQUIREMENT = a need / capability the solution must provide (functional: what it does; non-functional: quality "
              "such as speed or security).  Comes from stakeholders.  Checked for feasibility (technical, economic, legal, "
              "operational, schedule).\n"
              "RULE = a statement that defines or constrains how the business operates (definitions, facts, constraints, "
              "computations, action triggers).  Comes from policy, law, contracts and management decisions."),
        ("h", "Computing basics"),
        ("t", "OS: manages hardware, memory, files and programs (Windows, macOS, Linux).   Absolute path = from the root "
              "(C:\\Users\\Sam\\data.csv).   Relative path = from the current folder (data/sales.csv;  .. = parent folder).   "
              "Environments: development (build) -> testing (verify) -> production (real users).   "
              "Data ethics: transparency, consent, privacy, fairness, accountability."),
        ("h", "Sample database used in this tool"),
        ("sql", "\n".join(schema_line(n) for n in core.SCHEMAS)),
        ("t", "This tool runs queries on SQLite. For these query types MySQL returns the same rows (MySQL shows more decimal "
              "places for averages)."),
    ]


# ===========================================================================
# Entry point
# ===========================================================================
def entry():
    if sys.version_info < (3, 8):
        print("This tool needs Python 3.8 or newer. You have " + sys.version.split()[0] + ".")
        return
    if not HAVE_TK:
        print("tkinter isn't available in this Python, so the window can't open. "
              "Reinstall Python from python.org and keep 'tcl/tk and IDLE' ticked.")
        return
    try:
        App().run()
    except tk.TclError as e:
        print(f"The window could not open ({e}).")


if __name__ == "__main__":
    entry()
