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


def _load_gold(
    conn: sqlite3.Connection,
    table: str,
    gold_table: str,
    path: Path,
    insert_sql: str,
    row_to_params,
) -> int:
    """
    풀 리프레시(full refresh) 방식: 적재 전에 해당 fact 테이블을 비우고 staging 전체를 다시 채운다.
    -> run_pipeline.py를 여러 번 재실행해도 중복이 쌓이지 않는다.
    (staging CSV는 raw_to_staging이 매번 raw 전체에서 재생성하는 "현재 시점 전체 스냅샷"이므로,
     gold도 그 스냅샷으로 통째로 맞춰 쓰는 게 부분 upsert보다 단순하고 안전하다.)
    """
    conn.execute(f"DELETE FROM {gold_table}")

    if not path.exists() or path.stat().st_size == 0:
        conn.commit()
        print(f"[staging_to_gold] {table} 0건 적재 (staging 파일 없음/비어있음)")
        return 0
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        conn.commit()
        print(f"[staging_to_gold] {table} 0건 적재 (staging 파일 비어있음)")
        return 0
    if df.empty:
        conn.commit()
        print(f"[staging_to_gold] {table} 0건 적재 (staging 파일 비어있음)")
        return 0

    count = 0
    skipped = 0
    for _, row in df.iterrows():
        try:
            d = parse_date(str(row["date"]))
        except Exception:
            skipped += 1
            continue
        date_id = ensure_dim_date(conn, d)
        try:
            conn.execute(insert_sql, row_to_params(row, date_id))
            count += 1
        except sqlite3.IntegrityError as e:
            # preprocess.py가 이미 걸러줬어야 하지만, 이중 안전장치로 여기서도 죽지 않고 건너뛴다.
            skipped += 1
            print(f"[staging_to_gold][경고] {table} 행 적재 실패({e}) -> 건너뜀: {dict(row)}")
    conn.commit()
    print(f"[staging_to_gold] {table} {count}건 적재 (건너뜀 {skipped}건)")
    return count


def load_daily_work(conn: sqlite3.Connection) -> int:
    return _load_gold(
        conn,
        "fact_daily_work",
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
    """
    fact_erp_crm 테이블은 erp/crm 두 소스를 함께 담으므로,
    둘 중 하나만 리프레시하면 다른 쪽 데이터가 같이 지워진다.
    그래서 이 함수는 DELETE를 하지 않고, run_all()에서 erp+crm을 합쳐
    한 번만 리프레시한 뒤 두 소스를 순서대로 채운다.
    """
    if not STAGING_DIR.joinpath(f"{source}.csv").exists():
        print(f"[staging_to_gold] fact_erp_crm[{source}] 0건 적재 (staging 파일 없음)")
        return 0
    try:
        df = pd.read_csv(STAGING_DIR / f"{source}.csv")
    except pd.errors.EmptyDataError:
        print(f"[staging_to_gold] fact_erp_crm[{source}] 0건 적재 (staging 파일 비어있음)")
        return 0
    if df.empty:
        print(f"[staging_to_gold] fact_erp_crm[{source}] 0건 적재 (staging 파일 비어있음)")
        return 0

    insert_sql = """INSERT INTO fact_erp_crm
        (date_id, category_id, project_id, source_id, metric_type,
         dimension_1, dimension_2, metric_value, metric_unit, origin_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    count = skipped = 0
    for _, row in df.iterrows():
        try:
            d = parse_date(str(row["date"]))
        except Exception:
            skipped += 1
            continue
        date_id = ensure_dim_date(conn, d)
        try:
            conn.execute(
                insert_sql,
                (
                    date_id, row["category_id"], row.get("project_id"), row["source_id"],
                    row["metric_type"], row.get("dimension_1"), row.get("dimension_2"),
                    row.get("metric_value"), row.get("metric_unit"), row.get("origin_file"),
                ),
            )
            count += 1
        except sqlite3.IntegrityError as e:
            skipped += 1
            print(f"[staging_to_gold][경고] fact_erp_crm[{source}] 행 적재 실패({e}) -> 건너뜀")
    conn.commit()
    print(f"[staging_to_gold] fact_erp_crm[{source}] {count}건 적재 (건너뜀 {skipped}건)")
    return count


def load_mail_insight(conn: sqlite3.Connection) -> int:
    return _load_gold(
        conn,
        "fact_mail_insight",
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
        conn.execute("DELETE FROM fact_erp_crm")  # erp+crm 공용 테이블: 합쳐서 한 번만 리프레시
        conn.commit()
        load_erp_crm(conn, "erp")
        load_erp_crm(conn, "crm")
        load_mail_insight(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    run_all()
