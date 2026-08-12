"""dim_date 채우기 및 날짜 파싱 공통 유틸."""
import sqlite3
from datetime import date, timedelta


def ensure_dim_date(conn: sqlite3.Connection, target_date: date) -> str:
    """target_date가 dim_date에 없으면 추가하고 date_id('YYYY-MM-DD')를 반환."""
    date_id = target_date.isoformat()
    row = conn.execute("SELECT 1 FROM dim_date WHERE date_id = ?", (date_id,)).fetchone()
    if row is None:
        iso_year, iso_week, _ = target_date.isocalendar()
        conn.execute(
            """INSERT INTO dim_date (date_id, year, month, day, week_of_year, weekday)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                date_id,
                target_date.year,
                target_date.month,
                target_date.day,
                iso_week,
                target_date.strftime("%a"),
            ),
        )
    return date_id


def parse_date(value: str) -> date:
    """'YYYY-MM-DD' 또는 'YYYY.MM.DD' 등 흔한 포맷을 date로 파싱."""
    value = value.strip().replace(".", "-").replace("/", "-")
    parts = [int(p) for p in value.split("-") if p]
    return date(parts[0], parts[1], parts[2])
