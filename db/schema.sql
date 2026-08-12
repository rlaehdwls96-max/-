-- =========================================================
-- DATA-analysis 스키마
-- 계층: Staging(정제) -> 이 스키마(Gold: dim/fact/view)
-- 4개 소스: 노션 업무일지 / 경력·성과 / ERP·CRM / 메일 인사이트
-- =========================================================

PRAGMA foreign_keys = ON;

-- ---------- 차원(dimension) 테이블 ----------

CREATE TABLE IF NOT EXISTS dim_date (
    date_id      TEXT PRIMARY KEY,      -- 'YYYY-MM-DD'
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    day          INTEGER NOT NULL,
    week_of_year INTEGER NOT NULL,
    weekday      TEXT NOT NULL          -- 'Mon'..'Sun'
);

CREATE TABLE IF NOT EXISTS dim_category (
    category_id   TEXT PRIMARY KEY,     -- slug, e.g. 'work_automation'
    category_name TEXT NOT NULL,        -- '업무자동화' 등
    category_group TEXT NOT NULL        -- '업무' | '경력' | 'ERP' | 'CRM' | '메일' | '시장동향'
);

CREATE TABLE IF NOT EXISTS dim_project (
    project_id   TEXT PRIMARY KEY,      -- 노션 프로젝트 페이지 ID
    project_name TEXT NOT NULL,
    status       TEXT                   -- 발의/진행중/보류/종료 등
);

CREATE TABLE IF NOT EXISTS dim_source (
    source_id   TEXT PRIMARY KEY,       -- 'notion' | 'erp' | 'crm' | 'mail'
    source_name TEXT NOT NULL,
    ingest_mode TEXT NOT NULL           -- 'api' | 'manual_upload'
);

-- ---------- 팩트(fact) 테이블: 소스별로 분리 유지 ----------

CREATE TABLE IF NOT EXISTS fact_daily_work (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date_id      TEXT NOT NULL REFERENCES dim_date(date_id),
    category_id  TEXT NOT NULL REFERENCES dim_category(category_id),
    project_id   TEXT REFERENCES dim_project(project_id),
    source_id    TEXT NOT NULL DEFAULT 'notion' REFERENCES dim_source(source_id),
    title        TEXT NOT NULL,
    status       TEXT,                  -- 완료/미완료 등
    notion_page_id TEXT,                -- 원본 추적용
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fact_career_achievement (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    date_id        TEXT NOT NULL REFERENCES dim_date(date_id),
    category_id    TEXT NOT NULL REFERENCES dim_category(category_id),
    project_id     TEXT REFERENCES dim_project(project_id),
    source_id      TEXT NOT NULL DEFAULT 'notion' REFERENCES dim_source(source_id),
    achievement    TEXT NOT NULL,
    metric_value   REAL,                -- 정량 성과 수치
    metric_unit    TEXT,
    evidence       TEXT,                -- 검증 근거
    resume_ready   INTEGER DEFAULT 0,   -- 경력기술서 반영 체크박스 (0/1)
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fact_erp_crm (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date_id       TEXT NOT NULL REFERENCES dim_date(date_id),
    category_id   TEXT NOT NULL REFERENCES dim_category(category_id),
    project_id    TEXT REFERENCES dim_project(project_id),
    source_id     TEXT NOT NULL REFERENCES dim_source(source_id), -- 'erp' | 'crm'
    metric_type   TEXT NOT NULL,        -- '공급계획'|'매출'|'재고' 등
    dimension_1   TEXT,                 -- 예: 품번/거래처 등 자유 컬럼
    dimension_2   TEXT,
    metric_value  REAL NOT NULL,
    metric_unit   TEXT,
    origin_file   TEXT,                 -- 원본 파일명 (pdf/xlsx 추적)
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fact_mail_insight (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date_id      TEXT NOT NULL REFERENCES dim_date(date_id),
    category_id  TEXT NOT NULL REFERENCES dim_category(category_id),
    project_id   TEXT REFERENCES dim_project(project_id),
    source_id    TEXT NOT NULL DEFAULT 'mail' REFERENCES dim_source(source_id),
    sender_domain TEXT,
    subject      TEXT,
    summary      TEXT NOT NULL,
    importance   TEXT,                  -- 상/중/하
    origin_file  TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);

-- ---------- 리포트용 뷰 (일/주/월) ----------
-- fact 테이블에 date_id/category_id가 공통으로 있어서 UNION으로 묶어 집계

CREATE VIEW IF NOT EXISTS v_activity_union AS
    SELECT date_id, category_id, source_id, 'daily_work' AS fact_type, title AS label FROM fact_daily_work
    UNION ALL
    SELECT date_id, category_id, source_id, 'career' AS fact_type, achievement AS label FROM fact_career_achievement
    UNION ALL
    SELECT date_id, category_id, source_id, 'erp_crm' AS fact_type, metric_type AS label FROM fact_erp_crm
    UNION ALL
    SELECT date_id, category_id, source_id, 'mail' AS fact_type, subject AS label FROM fact_mail_insight;

CREATE VIEW IF NOT EXISTS v_daily_summary AS
    SELECT date_id, category_id, fact_type, COUNT(*) AS item_count
    FROM v_activity_union
    GROUP BY date_id, category_id, fact_type;

CREATE VIEW IF NOT EXISTS v_weekly_summary AS
    SELECT d.year, d.week_of_year, u.category_id, u.fact_type, COUNT(*) AS item_count
    FROM v_activity_union u
    JOIN dim_date d ON u.date_id = d.date_id
    GROUP BY d.year, d.week_of_year, u.category_id, u.fact_type;

CREATE VIEW IF NOT EXISTS v_monthly_summary AS
    SELECT d.year, d.month, u.category_id, u.fact_type, COUNT(*) AS item_count
    FROM v_activity_union u
    JOIN dim_date d ON u.date_id = d.date_id
    GROUP BY d.year, d.month, u.category_id, u.fact_type;
