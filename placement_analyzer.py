"""Placement Drive Analyzer
Track candidates through placement rounds, see where they drop out,
export data for Excel / Power BI and generate an HTML dashboard.

Skills shown: Python, OOP-free modular functions, SQL (SQLite), argparse CLI,
data cleaning, CSV export, HTML/CSS reporting.

Usage:
    python placement_analyzer.py seed                 # fill with DUMMY data
    python placement_analyzer.py add-company "Acme"
    python placement_analyzer.py add-candidate "Asha K" A
    python placement_analyzer.py record 1 1 Aptitude Passed
    python placement_analyzer.py funnel
    python placement_analyzer.py sections
    python placement_analyzer.py export
    python placement_analyzer.py dashboard
"""
import argparse
import csv
import html
import random
import sqlite3

DB = "placement.db"
ROUNDS = ["Aptitude", "GD", "Technical", "HR"]
STATUSES = ["Passed", "Failed", "Absent"]
DUMMY_NAMES = [
    "Asha K", "Ravi S", "Meera P", "Kiran D", "Divya R", "Arjun N", "Sneha T",
    "Rohit M", "Pooja V", "Varun G", "Nisha B", "Akash L", "Kavya H", "Manoj C",
    "Ritu J", "Sanjay F", "Lakshmi E", "Harsh Y", "Tanya W", "Vivek Q",
    "Anita Z", "Deepak U", "Isha O", "Naveen I", "Pallavi A", "Suresh X",
    "Bhavana K", "Chetan R", "Disha M", "Eshwar P",
]


def connect():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            section TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL
                REFERENCES candidates(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL
                REFERENCES companies(id) ON DELETE CASCADE,
            round TEXT NOT NULL
                CHECK (round IN ('Aptitude','GD','Technical','HR')),
            status TEXT NOT NULL
                CHECK (status IN ('Passed','Failed','Absent')),
            UNIQUE (candidate_id, company_id, round));
        """
    )
    return conn


ROUND_ORDER = "CASE r.round WHEN 'Aptitude' THEN 1 WHEN 'GD' THEN 2 WHEN 'Technical' THEN 3 ELSE 4 END"


def funnel_rows(conn):
    """Per company and round: how many appeared and how many passed."""
    return conn.execute(
        f"""SELECT co.name, r.round, COUNT(*) AS appeared,
                   SUM(r.status = 'Passed') AS passed
            FROM results r JOIN companies co ON co.id = r.company_id
            GROUP BY co.id, r.round
            ORDER BY co.name, {ROUND_ORDER}"""
    ).fetchall()


def section_rows(conn):
    """Per section: applications and final selections (passed HR)."""
    return conn.execute(
        """SELECT ca.section,
                  COUNT(DISTINCT ca.id || '-' || r.company_id) AS applications,
                  SUM(r.round = 'HR' AND r.status = 'Passed') AS selected
           FROM results r JOIN candidates ca ON ca.id = r.candidate_id
           GROUP BY ca.section ORDER BY ca.section"""
    ).fetchall()


def cmd_seed(conn, _args):
    rng = random.Random(42)  # same dummy data every run
    conn.executescript("DELETE FROM results; DELETE FROM candidates; DELETE FROM companies;")
    for company in ("Demo Corp", "Sample Tech"):
        conn.execute("INSERT INTO companies (name) VALUES (?)", (company,))
    for name in DUMMY_NAMES:
        conn.execute(
            "INSERT INTO candidates (name, section) VALUES (?, ?)",
            (name, rng.choice("ABCD")),
        )
    cand_ids = [r[0] for r in conn.execute("SELECT id FROM candidates")]
    comp_ids = [r[0] for r in conn.execute("SELECT id FROM companies")]
    for comp in comp_ids:
        for cand in cand_ids:
            for rnd in ROUNDS:
                roll = rng.random()
                status = "Absent" if roll < 0.04 else "Passed" if roll < 0.66 else "Failed"
                conn.execute(
                    "INSERT INTO results (candidate_id, company_id, round, status) VALUES (?,?,?,?)",
                    (cand, comp, rnd, status),
                )
                if status != "Passed":
                    break  # candidate is out, no further rounds
    conn.commit()
    print(f"Seeded {len(cand_ids)} dummy candidates and {len(comp_ids)} companies.")


def cmd_add_company(conn, args):
    name = args.name.strip()
    try:
        cur = conn.execute("INSERT INTO companies (name) VALUES (?)", (name,))
        conn.commit()
        print("Company added. ID =", cur.lastrowid)
    except sqlite3.IntegrityError:
        print("That company already exists.")


def cmd_add_candidate(conn, args):
    cur = conn.execute(
        "INSERT INTO candidates (name, section) VALUES (?, ?)",
        (args.name.strip().title(), args.section.strip().upper()),
    )
    conn.commit()
    print("Candidate added. ID =", cur.lastrowid)


def cmd_record(conn, args):
    try:
        conn.execute(
            "INSERT INTO results (candidate_id, company_id, round, status) VALUES (?,?,?,?)",
            (args.candidate_id, args.company_id, args.round, args.status),
        )
        conn.commit()
        print("Result saved.")
    except sqlite3.IntegrityError as err:
        print("Could not save:", err)


def cmd_funnel(conn, _args):
    rows = funnel_rows(conn)
    if not rows:
        print("No data yet. Try: python placement_analyzer.py seed")
        return
    current = None
    for company, rnd, appeared, passed in rows:
        if company != current:
            print(f"\n{company}")
            print(f"{'Round':<11}{'Appeared':>9}{'Passed':>8}{'Pass %':>8}")
            current = company
        pct = round(100 * passed / appeared, 1) if appeared else 0
        print(f"{rnd:<11}{appeared:>9}{passed:>8}{pct:>8}")


def cmd_sections(conn, _args):
    print(f"{'Section':<9}{'Applications':>13}{'Selected':>10}{'Rate %':>8}")
    for section, apps, sel in section_rows(conn):
        print(f"{section:<9}{apps:>13}{sel:>10}{round(100 * sel / apps, 1):>8}")


def cmd_export(conn, _args):
    rows = conn.execute(
        """SELECT ca.id, ca.name, ca.section, co.name, r.round, r.status
           FROM results r
           JOIN candidates ca ON ca.id = r.candidate_id
           JOIN companies co ON co.id = r.company_id
           ORDER BY co.name, ca.id"""
    ).fetchall()
    with open("placement_export.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "name", "section", "company", "round", "status"])
        writer.writerows(rows)
    print(f"Exported {len(rows)} rows to placement_export.csv")


def cmd_dashboard(conn, _args):
    parts = []
    current = None
    for company, rnd, appeared, passed in funnel_rows(conn):
        if company != current:
            if current is not None:
                parts.append("</div>")
            parts.append(f"<div class='card'><h2>{html.escape(company)}</h2>")
            current = company
        pct = round(100 * passed / appeared) if appeared else 0
        parts.append(
            f"<div class='row'><span class='lbl'>{rnd}</span>"
            f"<div class='track'><div class='bar' style='width:{pct}%'></div></div>"
            f"<span class='val'>{passed}/{appeared} passed</span></div>"
        )
    if current is not None:
        parts.append("</div>")
    parts.append("<div class='card'><h2>Selection rate by section</h2>")
    for section, apps, sel in section_rows(conn):
        pct = round(100 * sel / apps) if apps else 0
        parts.append(
            f"<div class='row'><span class='lbl'>Section {html.escape(section)}</span>"
            f"<div class='track'><div class='bar alt' style='width:{pct}%'></div></div>"
            f"<span class='val'>{sel}/{apps} selected</span></div>"
        )
    parts.append("</div>")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Placement Drive Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f4f1fa;color:#2b2540;margin:0;padding:24px}}
h1{{margin-top:0}} .card{{background:#fff;border-radius:12px;padding:16px 20px;margin-bottom:16px;box-shadow:0 1px 4px #0001;max-width:720px}}
.row{{display:flex;align-items:center;gap:12px;margin:10px 0}} .lbl{{width:100px}}
.track{{flex:1;background:#e7e1f3;border-radius:6px;height:18px}} .bar{{background:#5b3fa0;height:100%;border-radius:6px}}
.bar.alt{{background:#d9822b}} .val{{width:110px;text-align:right;font-size:.9rem}}
</style></head><body>
<h1>Placement Drive Dashboard</h1>
{''.join(parts)}
</body></html>"""
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(page)
    print("Dashboard written to dashboard.html (open it in your browser).")


def build_parser():
    p = argparse.ArgumentParser(description="Placement Drive Analyzer")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="fill the database with dummy data").set_defaults(func=cmd_seed)
    s = sub.add_parser("add-company", help="add a company")
    s.add_argument("name")
    s.set_defaults(func=cmd_add_company)
    s = sub.add_parser("add-candidate", help="add a candidate")
    s.add_argument("name")
    s.add_argument("section")
    s.set_defaults(func=cmd_add_candidate)
    s = sub.add_parser("record", help="record a round result")
    s.add_argument("candidate_id", type=int)
    s.add_argument("company_id", type=int)
    s.add_argument("round", choices=ROUNDS)
    s.add_argument("status", choices=STATUSES)
    s.set_defaults(func=cmd_record)
    sub.add_parser("funnel", help="round-wise pass counts").set_defaults(func=cmd_funnel)
    sub.add_parser("sections", help="selection rate per section").set_defaults(func=cmd_sections)
    sub.add_parser("export", help="export CSV for Excel / Power BI").set_defaults(func=cmd_export)
    sub.add_parser("dashboard", help="generate dashboard.html").set_defaults(func=cmd_dashboard)
    return p


def main():
    args = build_parser().parse_args()
    conn = connect()
    args.func(conn, args)
    conn.close()


if __name__ == "__main__":
    main()
