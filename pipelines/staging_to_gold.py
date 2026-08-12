"""
data/staging/*.csv 를 읽어 warehouse.db의 fact 테이블에 적재한다.
적재 전 dim_date를 자동으로 채운다 (date_utils.ensure_dim_date).

실행: python pipelines/staging_to_gold.py
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from date_utils import ensure_dim_date, parse_date  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = BASE_DIR / "data" / "staging"
DB_PATH = BASE_DIR / "data" / "warehouse.db"


def _load_gold(conn: sqlite3.Connection, table: str, path: Path, insert_sql: str, row_to_params) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return 0
    if df.empty:
        return 0

    count = 0
    for _, row in df.iterrows():
        try:
            d = parse_date(str(row["date"]))
        except Exception:
            continue
        date_id = ensure_dim_date(conn, d)
        conn.execute(insert_sql, row_to_params(row, date_id))
        count += 1
    conn.commit()
    print(f"[staging_to_gold] {table} {count}건 적재")
    return count


def load_daily_work(conn: sqlite3.Connection) -> int:
    return _load_gold(
        conn,
        "fact_daily_work",
        STAGING_DIR / "daily_work.csv",
        """INSERT INTO fact_daily_work
           (date_id, category_id, project_id, source_id, title, status, notion_page_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        lambda r, date_id: (
            date_id, r["category_id"], r.get("project_id"), r["source_id"],
            r["title"], r.get("status"), r.get("notion_page_id"),
        ),
    )


def load_erp_crm(conn: sqlite3.Connection, source: str) -> int:
    return _load_gold(
        conn,
        f"fact_erp_crm[{source}]",
        STAGING_DIR / f"{source}.csv",
        """INSERT INTO fact_erp_crm
           (date_id, category_id, project_id, source_id, metric_type,
            dimension_1, dimension_2, metric_value, metric_unit, origin_file)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        lambda r, date_id: (
            date_id, r["category_id"], r.get("project_id"), r["source_id"],
            r["metric_type"], r.get("dimension_1"), r.get("dimension_2"),
            r.get("metric_value"), r.get("metric_unit"), r.get("origin_file"),
        ),
    )


def load_mail_insight(conn: sqlite3.Connection) -> int:
    return _load_gold(
        conn,
        "fact_mail_insight",
        STAGING_DIR / "mail_insight.csv",
        """INSERT INTO fact_mail_insight
           (date_id, category_id, project_id, source_id, sender_domain, subject, summary, importance)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        lambda r, date_id: (
            date_id, r["category_id"], r.get("project_id"), r["source_id"],
            r.get("sender_domain"), r.get("subject"), r["summary"], r.get("importance"),
        ),
    )


def run_all() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        load_daily_work(conn)
        load_erp_crm(conn, "erp")
        load_erp_crm(conn, "crm")
        load_mail_insight(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    run_all()
