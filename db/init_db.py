"""
warehouse.db(SQLite)를 생성하고 schema.sql을 적용한 뒤,
dim_source / dim_category 기본값을 시딩한다.

실행: python db/init_db.py
"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "warehouse.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# 자비스 로그 카테고리 체계와 정합성을 맞춘 기본 카테고리
DEFAULT_CATEGORIES = [
    ("work_automation", "업무자동화", "업무"),
    ("daily_work", "일일업무", "업무"),
    ("career", "경력·성과", "경력"),
    ("erp_supply", "ERP 공급계획", "ERP"),
    ("erp_inventory", "ERP 재고", "ERP"),
    ("crm_sales", "CRM 매출", "CRM"),
    ("crm_customer", "CRM 고객", "CRM"),
    ("mail_insight", "메일 인사이트", "메일"),
    ("market_trend", "시장동향", "시장동향"),
    ("etc", "기타", "기타"),
]

DEFAULT_SOURCES = [
    ("notion", "Notion (업무일지·경력)", "api"),
    ("erp", "사내 ERP", "manual_upload"),
    ("crm", "사내 CRM", "manual_upload"),
    ("mail", "메일 아카이빙 시스템", "manual_upload"),
]


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        conn.executemany(
            "INSERT OR IGNORE INTO dim_category (category_id, category_name, category_group) VALUES (?, ?, ?)",
            DEFAULT_CATEGORIES,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO dim_source (source_id, source_name, ingest_mode) VALUES (?, ?, ?)",
            DEFAULT_SOURCES,
        )
        conn.commit()
        print(f"[init_db] warehouse.db 초기화 완료 -> {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
