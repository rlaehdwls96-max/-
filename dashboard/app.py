"""
app.py — VENUS DATA-analysis 대시보드 (Streamlit + Plotly)

실행: streamlit run app.py
전제: pipelines/staging_to_gold.py 실행이 끝나서 data/warehouse.db에
      fact_dept_metric / fact_daily_work / fact_mail_insight가 채워져 있어야 함.

탭 구성 (PROJECT_HANDOFF.md §3 우선순위대로):
  1) 일/주/월 리포트
  2) 실적 추이 (시계열)
  3) 리피트(REPEAT) SKU 관리
"""

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import db

st.set_page_config(page_title="VENUS MD 대시보드", layout="wide")

# ---------------------------------------------------------------------------
# 사이드바: DB 경로
# ---------------------------------------------------------------------------
st.sidebar.title("설정")
db_path = st.sidebar.text_input("warehouse.db 경로", value=db.DEFAULT_DB_PATH)

if st.sidebar.button("🔄 데이터 새로고침 (파이프라인 재실행 후 누르세요)"):
    db.clear_all_caches()
    st.sidebar.success("캐시를 비웠습니다. 최신 데이터를 다시 불러옵니다.")

try:
    tables = db.list_tables(db_path)
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

if "fact_dept_metric" not in tables:
    st.warning(
        "fact_dept_metric 테이블이 없습니다. "
        "pipelines/staging_to_gold.py를 먼저 실행했는지 확인해주세요."
    )

st.sidebar.caption(f"인식된 테이블: {', '.join(tables)}")

st.title("VENUS 국내영업1부1과 MD 업무 대시보드")

tab1, tab2, tab3, tab4 = st.tabs([
    "📅 일/주/월 리포트", "📈 실적 추이", "🔁 리피트(REPEAT) SKU 관리", "🏷️ 군별 실적",
])

# ---------------------------------------------------------------------------
# 공통: source_id 한글 라벨
# ---------------------------------------------------------------------------
SOURCE_LABELS = {
    "repeat_br": "REPEAT BR",
    "repeat_pt": "REPEAT PT",
    "repeat_sl": "REPEAT SL",
    "sangpan_qty": "상판수량",
    "prod_sales": "생산/매출/실매출/재고",
    "inventory_plan": "재고계획",
    "sangpan_snapshot": "상판(스냅샷)",
    "supply_plan": "공급계획서",
    "prod_plan": "생산계획서",
    "operating_items": "운영품번/폐기예상",
    "weekly_sales": "주간 군별 실매출",
}


def label_source(sid: str) -> str:
    return SOURCE_LABELS.get(sid, sid)


# ===========================================================================
# TAB 1 — 일/주/월 리포트
# ===========================================================================
with tab1:
    st.subheader("기간별 업무·데이터 요약")

    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        granularity = st.radio("집계 단위", ["일", "주", "월"], horizontal=True, key="t1_gran")
    with col_b:
        default_start = date.today() - timedelta(days=30)
        start_d = st.date_input("시작일", value=default_start, key="t1_start")
    with col_c:
        end_d = st.date_input("종료일", value=date.today(), key="t1_end")

    st.markdown("#### 🗓️ 일일 업무 (노션)")
    if "fact_daily_work" in tables:
        work_df = db.get_fact_with_dims(db_path, "fact_daily_work")
        if work_df.empty:
            st.info("일일 업무 기록이 없습니다.")
        else:
            work_df = work_df[
                (work_df["report_date"] >= pd.to_datetime(start_d))
                & (work_df["report_date"] <= pd.to_datetime(end_d))
            ]
            if work_df.empty:
                st.info("선택한 기간에 일일 업무 기록이 없습니다.")
            else:
                freq = {"일": "D", "주": "W", "월": "M"}[granularity]
                bucket = work_df.set_index("report_date").resample(freq).size().reset_index(name="건수")
                fig = px.bar(bucket, x="report_date", y="건수", title="업무 건수 추이")
                st.plotly_chart(fig, use_container_width=True)

                col1, col2 = st.columns(2)
                with col1:
                    cat_summary = work_df["카테고리"].value_counts().reset_index()
                    cat_summary.columns = ["카테고리", "건수"]
                    st.plotly_chart(
                        px.pie(cat_summary, names="카테고리", values="건수", title="카테고리별 비중"),
                        use_container_width=True,
                    )
                with col2:
                    status_col = db.resolve_column(db_path, "fact_daily_work", db.CANDIDATE_WORK_STATUS_COLS)
                    if status_col:
                        status_summary = work_df[status_col].value_counts().reset_index()
                        status_summary.columns = ["상태", "건수"]
                        st.dataframe(status_summary, use_container_width=True, hide_index=True)

                with st.expander("일일 업무 상세"):
                    name_col = db.resolve_column(db_path, "fact_daily_work", db.CANDIDATE_WORK_NAME_COLS)
                    show_cols = [c for c in [name_col, "카테고리", status_col, "report_date"] if c and c in work_df.columns]
                    st.dataframe(
                        work_df[show_cols].rename(columns={"report_date": "날짜"}),
                        use_container_width=True, hide_index=True,
                    )
    else:
        st.info("fact_daily_work 테이블이 아직 없습니다.")

    st.markdown("#### 📧 메일 인사이트")
    if "fact_mail_insight" in tables:
        mail_df = db.get_fact_with_dims(db_path, "fact_mail_insight")
        if mail_df.empty:
            st.info("메일 인사이트 기록이 없습니다.")
        else:
            mail_df = mail_df[
                (mail_df["report_date"] >= pd.to_datetime(start_d))
                & (mail_df["report_date"] <= pd.to_datetime(end_d))
            ]
            st.metric("선택 기간 메일 인사이트 건수", len(mail_df))
            if not mail_df.empty:
                if "importance" in mail_df.columns:
                    imp_summary = mail_df["importance"].value_counts().reset_index()
                    imp_summary.columns = ["중요도", "건수"]
                    st.dataframe(imp_summary, use_container_width=True, hide_index=True)
                with st.expander("메일 인사이트 상세"):
                    show_cols = [c for c in ["report_date", "sender_domain", "subject", "summary", "카테고리"] if c in mail_df.columns]
                    st.dataframe(
                        mail_df[show_cols].rename(columns={"report_date": "날짜", "sender_domain": "발신도메인", "subject": "제목", "summary": "요약"}),
                        use_container_width=True, hide_index=True,
                    )
    else:
        st.info("fact_mail_insight 테이블이 아직 없습니다.")

    st.markdown("#### 🏭 부서 결재 데이터 (fact_dept_metric) 요약")
    if "fact_dept_metric" in tables:
        dm_df = db.get_dept_metric_df(db_path, date_from=str(start_d), date_to=str(end_d))
        if dm_df.empty or dm_df["report_date"].isna().all():
            st.info(
                "선택 기간에 매칭되는 날짜 데이터가 없습니다. "
                "(date_id ↔ dim_date 매핑이 예상과 다를 수 있습니다 — db.py 참고)"
            )
        else:
            summary = (
                dm_df.dropna(subset=["report_date"])
                .groupby("source_id")["metric_value"]
                .agg(건수="count", 합계="sum")
                .reset_index()
            )
            summary["소스"] = summary["source_id"].map(label_source)
            st.dataframe(summary[["소스", "건수", "합계"]], use_container_width=True, hide_index=True)
    else:
        st.info("fact_dept_metric 테이블이 없습니다.")

# ===========================================================================
# TAB 2 — 실적 추이
# ===========================================================================
with tab2:
    st.subheader("핵심 지표 시계열 추이")

    if "fact_dept_metric" not in tables:
        st.info("fact_dept_metric 테이블이 없어 추이를 그릴 수 없습니다.")
    else:
        all_sources = db.get_distinct_values(db_path, "fact_dept_metric", "source_id")
        default_sources = [s for s in ["prod_sales", "weekly_sales"] if s in all_sources] or all_sources[:1]

        col1, col2 = st.columns([1, 2])
        with col1:
            picked_sources = st.multiselect(
                "데이터 소스",
                options=all_sources,
                default=default_sources,
                format_func=label_source,
                key="t2_sources",
            )
        with col2:
            metric_options = db.get_distinct_values(db_path, "fact_dept_metric", "metric_type")
            picked_metrics = st.multiselect("지표(metric_type)", options=metric_options, key="t2_metrics")

        col3, col4 = st.columns(2)
        with col3:
            t2_start = st.date_input("시작일", value=date.today() - timedelta(days=180), key="t2_start")
        with col4:
            t2_end = st.date_input("종료일", value=date.today(), key="t2_end")

        if not picked_sources:
            st.warning("최소 하나 이상의 데이터 소스를 선택해주세요.")
        else:
            trend_df = db.get_dept_metric_df(
                db_path,
                source_ids=picked_sources,
                metric_types=picked_metrics or None,
                date_from=str(t2_start),
                date_to=str(t2_end),
            )
            trend_df = trend_df.dropna(subset=["report_date"])

            if trend_df.empty:
                st.info("조건에 맞는 데이터가 없습니다.")
            else:
                trend_df["metric_value"] = pd.to_numeric(trend_df["metric_value"], errors="coerce")
                trend_df = trend_df.dropna(subset=["metric_value"])
                years_available = sorted(trend_df["report_date"].dt.year.dropna().unique().tolist())

                col5, col6 = st.columns(2)
                with col5:
                    group_freq = st.radio("집계 단위", ["일", "주", "월"], horizontal=True, key="t2_gran")
                with col6:
                    yoy_mode = st.checkbox(
                        "전년 대비 비교 (연도별로 겹쳐보기)",
                        key="t2_yoy",
                        disabled=len(years_available) < 2,
                        help=None if len(years_available) >= 2 else "선택한 기간에 2개 연도 이상의 데이터가 있어야 사용할 수 있습니다.",
                    )
                freq_map = {"일": "D", "주": "W", "월": "M"}

                if yoy_mode:
                    # 월 단위로 고정 — 연도별 같은 달끼리 겹쳐서 비교
                    trend_df["연도"] = trend_df["report_date"].dt.year.astype(str)
                    trend_df["월"] = trend_df["report_date"].dt.month
                    agg = (
                        trend_df.groupby(["연도", "월", "source_id"])["metric_value"]
                        .sum()
                        .reset_index()
                    )
                    agg["소스"] = agg["source_id"].map(label_source)
                    agg["계열"] = agg["소스"] + " · " + agg["연도"]

                    fig = px.line(
                        agg.sort_values("월"), x="월", y="metric_value", color="계열",
                        markers=True, title="전년 대비 월별 추이",
                        labels={"월": "월", "metric_value": "값"},
                    )
                    fig.update_xaxes(dtick=1)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    agg = (
                        trend_df.set_index("report_date")
                        .groupby([pd.Grouper(freq=freq_map[group_freq]), "source_id"])["metric_value"]
                        .sum()
                        .reset_index()
                    )
                    agg["소스"] = agg["source_id"].map(label_source)

                    fig = px.line(
                        agg, x="report_date", y="metric_value", color="소스",
                        markers=True, title="지표 추이", labels={"report_date": "날짜", "metric_value": "값"},
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with st.expander("원본 데이터 보기"):
                    st.dataframe(trend_df, use_container_width=True, hide_index=True)

# ===========================================================================
# TAB 3 — 리피트(REPEAT) SKU 관리 (브랜드별 리드타임 기준 발주판단으로 재설계)
# ===========================================================================
with tab3:
    st.subheader("REPEAT SKU 재고 현황")

    repeat_wide = db.get_dash_repeat_sku(db_path)

    if repeat_wide.empty:
        st.warning(
            "dash_repeat_sku 테이블이 없습니다. "
            "pipelines/parse_repeat.py를 먼저 실행해서 REPEAT(BR/PT/SL).xlsx 원본을 "
            "직접 읽어와야 이 탭이 채워집니다 (기존 9종 파서와 별개의 스크립트입니다)."
        )
    else:
        # --- 필터 ---------------------------------------------------------
        colf1, colf2, colf3, colf4 = st.columns(4)
        with colf1:
            brands = sorted(repeat_wide["brand"].dropna().unique().tolist())
            picked_brand = st.multiselect("브랜드", options=brands, default=brands, key="t3_brand")
        with colf2:
            seasons = sorted(repeat_wide["season"].dropna().unique().tolist())
            picked_season = st.multiselect("시즌", options=seasons, default=seasons, key="t3_season")
        with colf3:
            categories = sorted(repeat_wide["category"].dropna().unique().tolist())
            picked_category = st.multiselect("카테고리 (중요품번/중점SET = 기간품)", options=categories, key="t3_category")
        with colf4:
            sku_query = st.text_input("품번 검색", key="t3_sku")

        view = repeat_wide[repeat_wide["brand"].isin(picked_brand) & repeat_wide["season"].isin(picked_season)]
        if picked_category:
            view = view[view["category"].isin(picked_category)]
        if sku_query:
            view = view[view["품번"].astype(str).str.contains(sku_query, case=False, na=False)]

        if view.empty:
            st.info("조건에 맞는 SKU가 없습니다.")
        else:
            view = view.copy()
            # --- 소진 예상 계산 -------------------------------------------
            # 전년 같은 기간 월평균 판매량을 이번 시즌 수요 예측치로 사용
            # (REPEAT 계획서 자체가 전년 실적 기반 발주 계획용으로 설계된 파일이라
            #  이 값을 그대로 수요 예측 프록시로 쓰는 게 이 파일의 원래 용도와 일치함)
            view["월평균판매(전년기준)"] = view["전년실매출_최근3개월평균"]
            view["총재고(현재+추가생산)"] = view["current_stock"].fillna(0) + view["추가생산_합계"].fillna(0)

            def calc_runway(row):
                monthly = row["월평균판매(전년기준)"]
                stock = row["current_stock"]
                if pd.isna(stock):
                    return None
                if not monthly or monthly <= 0:
                    return float("inf")  # 작년 판매 이력이 없으면 소진 걱정 없음(또는 신품)
                return stock / monthly

            view["소진예상개월"] = view.apply(calc_runway, axis=1)

            # --- 발주 판단: 브랜드별 리드타임(parse_repeat.py에서 부여) 기준 -----
            # 브라(BR) 3개월 / 팬티(PT) 2개월처럼 브랜드마다 최소 확보해야 하는
            # 리드타임이 다르므로, 고정된 개월 수 대신 SKU별 리드타임_개월/발주기준_개월
            # 컬럼(dash_repeat_sku에 이미 포함)과 비교해서 상태를 매긴다.
            has_lead_time_cols = {"리드타임_개월", "발주기준_개월"}.issubset(view.columns)

            def order_status(row):
                m = row["소진예상개월"]
                if m is None:
                    return "현재고 없음"
                if m == float("inf"):
                    return "판매이력없음"
                if not has_lead_time_cols:
                    # parse_repeat.py를 아직 재실행하지 않아 리드타임 컬럼이 없는 경우 대비 폴백
                    if m < 1:
                        return "🔴 1개월 미만"
                    if m < 2:
                        return "🟡 1~2개월"
                    return "🟢 2개월 이상"
                lead = row["리드타임_개월"]
                threshold = row["발주기준_개월"]
                if m <= lead:
                    return "🔴 즉시발주 필요"
                if m <= threshold:
                    return "🟠 발주 준비"
                return "🟢 여유"

            view["발주상태"] = view.apply(order_status, axis=1)

            st.caption(
                "소진예상개월 = 현재고 ÷ 전년 동기 월평균 실매출. "
                "발주상태는 브랜드별 최소 리드타임(브라 3개월 · 팬티 2개월, "
                "pipelines/parse_repeat.py의 LEAD_TIME_MONTHS)에 안전마진 0.5개월을 더한 "
                "기준과 소진예상개월을 비교해 판정합니다."
            )

            display_cols = {
                "brand": "브랜드", "season": "시즌", "category": "카테고리",
                "품번": "품번", "컵범위": "컵범위", "color": "색상",
                "current_stock": "현재고", "월평균판매(전년기준)": "월평균판매(전년)",
                "소진예상개월": "소진예상(개월)",
            }
            if has_lead_time_cols:
                display_cols["리드타임_개월"] = "리드타임(개월)"
            display_cols["발주상태"] = "발주상태"
            display_cols.update({
                "추가생산_합계": "추가생산예정", "총재고(현재+추가생산)": "총재고",
            })
            show_df = view[list(display_cols.keys())].rename(columns=display_cols)
            show_df = show_df.sort_values("소진예상(개월)", na_position="last")

            st.dataframe(
                show_df, use_container_width=True, hide_index=True,
                column_config={
                    "소진예상(개월)": st.column_config.NumberColumn(format="%.1f"),
                },
            )
            st.caption(f"총 {len(show_df):,}행")

            csv = show_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("CSV로 내보내기", data=csv, file_name="repeat_sku_inventory.csv", mime="text/csv")

            # --- 발주 필요 SKU 알림 -----------------------------------------
            # 브랜드별 리드타임 기준(발주기준_개월)을 넘긴 SKU만 골라낸다.
            # (기존에는 브랜드 상관없이 '2개월 미만'으로 고정돼 있었음)
            st.markdown("##### ⚠️ 발주 필요 SKU")
            if has_lead_time_cols:
                urgent = view[
                    view["소진예상개월"].notna()
                    & (view["소진예상개월"] != float("inf"))
                    & (view["소진예상개월"] <= view["발주기준_개월"])
                ]
            else:
                urgent = view[view["소진예상개월"].notna() & (view["소진예상개월"] < 2)]

            if urgent.empty:
                st.success("발주 기준을 넘긴 SKU가 없습니다.")
            else:
                urgent_show = urgent[list(display_cols.keys())].rename(columns=display_cols).sort_values("소진예상(개월)")
                st.warning(f"발주 필요 SKU {len(urgent_show):,}건 (브랜드별 리드타임 기준)")
                st.dataframe(urgent_show, use_container_width=True, hide_index=True)

    # --- 세트비 --------------------------------------------------------------
    st.markdown("---")
    st.subheader("세트비 (브라·팬티 세트 판매/재고 비중)")

    st.markdown("---")
    st.markdown("**세트 조회 (BR ↔ PT 품번 대조)**")
    st.caption(
        "품번을 선택하면 코어 번호(접두사 3글자 제거 후 숫자 블록)가 같은 "
        "반대 브랜드 품번을 찾아 비교합니다. 매칭되는 품번이 없으면 단품으로 판단합니다."
    )
    all_skus = sorted(repeat_wide["품번"].dropna().astype(str).unique().tolist())
    if not all_skus:
        st.info("조회할 품번이 없습니다.")
    else:
        picked_sku = st.selectbox("품번 선택", options=all_skus, key="t3_set_sku")
        core = db.extract_core_sku(picked_sku)
        matched = repeat_wide[repeat_wide["품번"].astype(str).apply(db.extract_core_sku) == core].copy()

        if matched["brand"].nunique() < 2:
            st.warning(f"'{picked_sku}'(코어: {core})와 매칭되는 반대 브랜드 품번이 없습니다 - 단품으로 추정됩니다.")

        show_cols = [c for c in [
            "brand", "품번", "color", "current_stock",
            "전년실매출_연합계", "전년실매출_최근3개월평균", "추가생산_합계",
        ] if c in matched.columns]
        st.dataframe(matched[show_cols], use_container_width=True, hide_index=True)

        if matched["brand"].nunique() >= 2 and "전년실매출_연합계" in matched.columns and "current_stock" in matched.columns:
            by_brand = matched.groupby("brand").agg(
                총판매=("전년실매출_연합계", "sum"),
                총재고=("current_stock", "sum"),
            )
            total_sales = by_brand["총판매"].sum()
            total_stock = by_brand["총재고"].sum()
            if total_sales > 0 and total_stock > 0:
                by_brand["판매비"] = (by_brand["총판매"] / total_sales * 100).round(1)
                by_brand["재고비"] = (by_brand["총재고"] / total_stock * 100).round(1)
                st.dataframe(by_brand, use_container_width=True)
                imbalance = (by_brand["판매비"] - by_brand["재고비"]).abs().max()
                if imbalance > 15:
                    st.caption(f"참고: 판매비-재고비 차이가 최대 {imbalance:.0f}%p - 세트 내 브랜드 간 재고 쏠림 가능성")

# ===========================================================================
# TAB 4 — 군별 실적 (FY26_주간_군별_실매출_현황 기반)
# ===========================================================================
with tab4:
    st.subheader("군별 실적 (BR / PT / 임부복)")
    st.caption(
        "원본이 '월중 누적 스냅샷'(예: 4/1~4/12 누적) 구조라, "
        "주간 단위는 스냅샷 간 차감으로 계산한 증분값을 사용합니다."
    )

    kpi_df = db.get_dash_group_kpi(db_path)
    cum_df = db.get_dash_group_sales_cumulative(db_path)
    weekly_df = db.get_dash_group_sales_weekly(db_path)

    if cum_df.empty:
        st.warning(
            "군별 실적 테이블이 없습니다. "
            "pipelines/parse_weekly_group.py를 먼저 실행해서 "
            "FY26_주간_군별_실매출_현황.xlsx를 읽어와야 이 탭이 채워집니다."
        )
    else:
        # --- 부서 KPI 헤드라인 (최신 스냅샷) -------------------------------
        if not kpi_df.empty:
            kpi_df = kpi_df.copy()
            kpi_df["snapshot_date"] = pd.to_datetime(kpi_df["snapshot_date"], errors="coerce")
            latest_date = kpi_df["snapshot_date"].max()
            latest_kpi = kpi_df[kpi_df["snapshot_date"] == latest_date]

            st.markdown(f"##### 최신 스냅샷 기준 ({latest_date.date() if pd.notna(latest_date) else '?'})")
            kpi_cols = st.columns(len(latest_kpi)) if len(latest_kpi) > 0 else [st]
            for col, (_, row) in zip(kpi_cols, latest_kpi.iterrows()):
                with col:
                    st.metric(
                        row["kpi_name"],
                        f"{row['실적']:,.0f}" if pd.notna(row["실적"]) else "-",
                        delta=f"달성비 {row['달성비']*100:.1f}%" if pd.notna(row["달성비"]) else None,
                    )
                    st.caption(f"목표 {row['목표']:,.0f} · 전년비 {row['전년비']*100:.1f}%" if pd.notna(row["전년비"]) else "")

        st.markdown("---")

        # --- 필터 -----------------------------------------------------------
        # is_total_row=True(소계/합계 행)는 필터 옵션에서 제외 — 실제 군/품목이 아님
        real_rows = cum_df[~cum_df["is_total_row"].astype(bool)]

        colf1, colf2, colf3 = st.columns(3)
        with colf1:
            categories = sorted(real_rows["대분류"].dropna().unique().tolist())
            picked_category = st.multiselect("대분류", options=categories, default=categories, key="t4_category")
        with colf2:
            granularity = st.radio("단위", ["주간(증분)", "월간(누적)"], horizontal=True, key="t4_gran")
        with colf3:
            metric_kind = st.radio("지표", ["금액", "수량"], horizontal=True, key="t4_metric_kind")

        seasons = sorted(real_rows["season"].dropna().unique().tolist())
        picked_seasons = st.multiselect("시즌(월)", options=seasons, default=seasons, key="t4_season")

        group_options = sorted(real_rows[real_rows["대분류"].isin(picked_category)]["군"].dropna().unique().tolist())
        picked_group = st.multiselect(
            "군 (VBR=일반브라·HBR=홈브라 / VPT=일반팬티(세트+단품)·HPT=홈PT / VFS·VDW·VHS=임부복)",
            options=group_options, default=group_options, key="t4_group",
        )

        if granularity == "주간(증분)":
            src = weekly_df[~weekly_df.get("is_total_row", False).astype(bool)] if not weekly_df.empty else weekly_df
            value_col = f"{'금액' if metric_kind == '금액' else '수량'}_26년_주간증분"
            prev_col = None
        else:
            src = cum_df[(~cum_df["is_total_row"]) & (cum_df["is_month_final"] == 1)]
            value_col = f"{'금액' if metric_kind == '금액' else '수량'}_26년"
            prev_col = f"{'금액' if metric_kind == '금액' else '수량'}_25년"

        view = src[src["군"].isin(picked_group) & src["season"].isin(picked_seasons)].copy()

        if view.empty or value_col not in view.columns:
            st.info("조건에 맞는 데이터가 없습니다.")
        else:
            view["snapshot_date"] = pd.to_datetime(view["snapshot_date"], errors="coerce")
            view[value_col] = pd.to_numeric(view[value_col], errors="coerce")

            agg = view.groupby(["snapshot_date", "군"])[value_col].sum().reset_index()
            fig = px.bar(
                agg, x="snapshot_date", y=value_col, color="군", barmode="group",
                title=f"군별 {metric_kind} 추이 ({granularity})",
                labels={"snapshot_date": "날짜", value_col: metric_kind},
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("##### 군별 비중")
            sub_agg = view.groupby("군")[value_col].sum().reset_index().sort_values(value_col, ascending=False)
            fig2 = px.bar(
                sub_agg, x="군", y=value_col, title=f"군별 {metric_kind} 합계",
                labels={value_col: metric_kind},
            )
            st.plotly_chart(fig2, use_container_width=True)

            if granularity == "월간(누적)" and prev_col in view.columns:
                view[prev_col] = pd.to_numeric(view[prev_col], errors="coerce")
                yoy = view.groupby(["season", "군"])[[value_col, prev_col]].sum().reset_index()
                yoy["전년비(%)"] = (yoy[value_col] / yoy[prev_col].replace(0, pd.NA) * 100).round(1)
                st.markdown("##### 전년 대비 (군별)")
                st.dataframe(
                    yoy.rename(columns={value_col: f"{metric_kind}(올해)", prev_col: f"{metric_kind}(전년)"}),
                    use_container_width=True, hide_index=True,
                )

            with st.expander("품목별 상세"):
                item_col = "품목"
                detail_cols = [c for c in ["season", "군", item_col, "snapshot_date", value_col] if c in view.columns]
                st.dataframe(
                    view[detail_cols].sort_values(["군", "snapshot_date"]),
                    use_container_width=True, hide_index=True,
                )
