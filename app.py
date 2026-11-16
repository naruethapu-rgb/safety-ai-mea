"""AI Accident Intelligence — Phase 1 & 2
Safety Document Intelligence, Full-Text Search, and Incident AI Analyzer
Designed for Safety Department on Windows 10 (100% Offline Capable & GPT Enabled)
"""

import os
import sys
import json
from pathlib import Path
import datetime
import streamlit as st
import altair as alt

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    BASE_DIR, DOCUMENTS_DIR, DATABASE_DIR, DB_PATH, BACKUP_DIR,
    CATEGORY_MAP
)
from src.database import (
    init_db, sync_documents, search_documents, get_database_stats,
    get_page_detail, get_file_pages, backup_database, list_backups,
    get_connection
)
from src.pdf_parser import extract_pdf_data
from src.analyzer import (
    find_similar_past_incidents, match_relevant_wi,
    generate_offline_analysis, generate_gpt_analysis,
    save_analysis_record, list_saved_analyses, init_analysis_table
)
from src.analytics import get_incident_analytics_data
from src.docx_exporter import create_safety_report_docx
from src.ocr_vision import extract_text_with_vision
from src.usage_tracker import get_usage_summary

# Page configuration
st.set_page_config(
    page_title="AI Accident Intelligence — ฝ่ายความปลอดภัย",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1a365d;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4a5568;
        margin-bottom: 1.2rem;
    }
    .result-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 5px solid #3182ce;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 14px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .snippet-box {
        background-color: #f7fafc;
        border: 1px solid #edf2f7;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.95rem;
        line-height: 1.6;
        color: #2d3748;
        margin: 10px 0;
    }
    .category-badge {
        display: inline-block;
        background-color: #ebf8ff;
        color: #2b6cb0;
        font-weight: 600;
        font-size: 0.8rem;
        padding: 3px 8px;
        border-radius: 4px;
        margin-right: 8px;
    }
    .page-badge {
        display: inline-block;
        background-color: #feebc8;
        color: #c05621;
        font-weight: 600;
        font-size: 0.8rem;
        padding: 3px 8px;
        border-radius: 4px;
    }
    .score-badge {
        display: inline-block;
        background-color: #c6f6d5;
        color: #22543d;
        font-weight: 700;
        font-size: 0.85rem;
        padding: 3px 10px;
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize database on app load
init_db(DB_PATH)
init_analysis_table(DB_PATH)


def check_password():
    """Returns True if user is authenticated or if no password is configured."""
    app_pwd = None
    try:
        if hasattr(st, "secrets") and "APP_PASSWORD" in st.secrets:
            app_pwd = st.secrets["APP_PASSWORD"]
    except Exception:
        pass
    if not app_pwd:
        app_pwd = os.environ.get("APP_PASSWORD", None)

    # If no password set, bypass check (e.g. running offline/locally)
    if not app_pwd:
        return True

    if st.session_state.get("authenticated", False):
        return True

    st.markdown("<div class='main-header'>🛡️ AI Accident Intelligence — เข้าสู่ระบบ</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>กรุณาใส่รหัสผ่านเพื่อเข้าใช้งานระบบฐานข้อมูลและวิเคราะห์อุบัติเหตุ (ฝปภ. กฟน.)</div>", unsafe_allow_html=True)

    c1, _ = st.columns([1, 1])
    with c1:
        pwd = st.text_input("🔑 รหัสผ่านเข้าสู่ระบบ (Security Passcode):", type="password")
        if st.button("เข้าสู่ระบบ (Login)", type="primary"):
            if pwd == app_pwd:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ รหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")
    return False


if not check_password():
    st.stop()


def load_stats():
    return get_database_stats(DB_PATH)


# Initialize Session State
if "selected_page_id" not in st.session_state:
    st.session_state.selected_page_id = None
if "openai_api_key" not in st.session_state:
    secret_key = ""
    try:
        if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
            secret_key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    st.session_state.openai_api_key = os.environ.get("OPENAI_API_KEY", secret_key)
if "gpt_enabled" not in st.session_state:
    st.session_state.gpt_enabled = bool(st.session_state.openai_api_key)
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# Sidebar Configuration
with st.sidebar:
    st.markdown("### ⚙️ การตั้งค่า AI Copilot (GPT)")
    enable_gpt = st.toggle(
        "🤖 เปิดใช้งาน GPT AI Copilot",
        value=st.session_state.gpt_enabled,
        help="เปิดเพื่อส่งข้อความให้ OpenAI GPT ช่วยวิเคราะห์ 5 Whys และแผน CAPA / ปิดเพื่อใช้วิเคราะห์แบบออฟไลน์ 100% ฟรี"
    )
    st.session_state.gpt_enabled = enable_gpt

    if enable_gpt:
        key_input = st.text_input(
            "OpenAI API Key (ถ้ามี):",
            value=st.session_state.openai_api_key,
            type="password",
            placeholder="sk-proj-...",
            help="นำรหัส API Key จาก https://platform.openai.com/api-keys มาใส่ที่นี่ เพื่อให้ GPT ช่วยวิเคราะห์ 5 Whys และเขียนแผน CAPA"
        )
        if key_input != st.session_state.openai_api_key:
            st.session_state.openai_api_key = key_input

        if st.session_state.openai_api_key:
            st.success("🟢 เชื่อมต่อ GPT พร้อมใช้งาน (Online Mode)")
            model_choice = st.selectbox("เลือกรุ่นโมเดล AI:", ["gpt-4o-mini", "gpt-4o"], index=0)
        else:
            st.warning("⚠️ โปรดใส่ API Key หรือปิดสวิตช์เพื่อใช้วิเคราะห์ออฟไลน์")
            model_choice = "offline"
    else:
        st.info("🟡 โหมดวิเคราะห์ในเครื่อง (Offline Mode)\n*ประมวลผลฟรี 100% ไม่ส่งข้อมูลออกนอกระบบ*")
        model_choice = "offline"

    # API Usage & Cost Tracker Widget
    if st.session_state.gpt_enabled:
        st.markdown("---")
        st.markdown("### 💳 ข้อมูลการใช้ API & ค่าใช้จ่าย")
        try:
            usage = get_usage_summary(DB_PATH)
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                st.metric(
                    label="📅 ยอดใช้เดือนนี้",
                    value=f"{usage['monthly_cost_thb']:.2f} ฿",
                    help="ยอดรวมค่าบริการ OpenAI ประจำเดือนปัจจุบัน คำนวณเป็นเงินบาทไทย"
                )
            with col_u2:
                st.metric(
                    label="⚡ เรียกใช้",
                    value=f"{usage['monthly_calls']} ครั้ง",
                    help=f"โทเค็นสะสมเดือนนี้: {usage['monthly_tokens']:,} tokens"
                )

            st.caption(f"สะสมตลอดกาล: **{usage['all_time_thb']:.2f} บาท** (~${usage['monthly_cost_usd']:.4f} USD)")

            with st.expander("📜 ดูประวัติการใช้ 5 ครั้งล่าสุด"):
                if not usage["recent_logs"]:
                    st.write("ยังไม่มีประวัติการเรียกใช้ API ในระบบ")
                else:
                    for log in usage["recent_logs"]:
                        st.markdown(f"• **{log['time'][:16]}** | `{log['feature']}`\n  {log['tokens']:,} tokens (~{log['cost_thb']:.2f} ฿) — _{log['title'][:25]}_")

            st.markdown("[🔗 เช็คยอดเงินคงเหลือจริงในกระเป๋า OpenAI](https://platform.openai.com/settings/organization/billing/overview)")
        except Exception as e:
            st.caption(f"ระบบติดตามค่าบริการ: พร้อมทำงาน")

    st.markdown("---")
    st.markdown("### 📁 โครงสร้างเอกสารความปลอดภัย")
    st.write("• **อบ.ปอ. 1-2:** คนบาดเจ็บ + ของเสียหาย")
    st.write("• **อบ.ปอ. 3:** อุบัติเหตุยานพาหนะและจราจร")
    st.write("• **อบ.ปอ. 4:** ประชาชน/บุคคลภายนอกบาดเจ็บ")
    st.write("• **WI:** คู่มือขั้นตอนการปฏิบัติงาน")

    # Logout button if password protection is active
    if st.session_state.get("authenticated", False):
        st.markdown("---")
        if st.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

# Header Section
st.markdown("<div class='main-header'>🛡️ AI Accident Intelligence — ระบบจัดการและวิเคราะห์อุบัติเหตุ</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>ระบบฐานข้อมูลเอกสารความปลอดภัย ค้นหา และวิเคราะห์เปรียบเทียบเคส อบ.ปอ. 1-4 & WI</div>", unsafe_allow_html=True)

# Top Metrics Row
stats = load_stats()
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric(label="📄 เอกสารทั้งหมดในระบบ", value=f"{stats['total_files']} ไฟล์")
with col_m2:
    st.metric(label="📑 จำนวนหน้ารวม", value=f"{stats['total_pages']} หน้า")
with col_m3:
    st.metric(label="💾 ขนาดฐานข้อมูล", value=f"{stats['db_size_kb']} KB")
with col_m4:
    backups = list_backups(BACKUP_DIR)
    st.metric(label="📦 ไฟล์สำรองข้อมูล", value=f"{len(backups)} ชุด")

st.markdown("---")

# Main Navigation Tabs
tab_analytics, tab_analyzer, tab_search, tab_reader, tab_sync, tab_backup = st.tabs([
    "📊 แดชบอร์ดและสถิติอุบัติเหตุ (Incident Analytics & Trends)",
    "🧠 วิเคราะห์เคสใหม่เทียบเคสเก่า & WI (Incident AI Analyzer)",
    "🔍 ค้นหาเอกสาร (Search)",
    "📖 เปิดอ่านข้อความต้นฉบับ (Document Reader)",
    "🔄 สแกนและซิงค์เอกสาร (Sync & Ingestion)",
    "💾 สำรองและดูแลฐานข้อมูล (Backup & Health)"
])

# ==============================================================================
# TAB 0: INCIDENT ANALYTICS & STATISTICAL DASHBOARD (NEW FEATURE)
# ==============================================================================
with tab_analytics:
    st.subheader("📊 แดชบอร์ดสถิติอุบัติเหตุและการเจาะลึกข้อมูล (Incident Analytics Dashboard)")
    st.caption("ระบบอ่าน 'ไส้ใน' ของเอกสารทั้งหมดเพื่อจำแนกสถิติรายปี, ประเภท อบ.ปอ. 1-4, และลักษณะการเกิดเหตุ (เฉี่ยวชน, ลื่นล้ม, ประชาชนบาดเจ็บ) พร้อมกดดูและดาวน์โหลดเอกสารได้ทันที")

    df_incidents = get_incident_analytics_data(DB_PATH)

    if df_incidents.empty:
        st.info("ℹ️ ยังไม่มีข้อมูลอุบัติเหตุในระบบ กรุณานำเข้าเอกสารในแท็บ 'สแกนและซิงค์เอกสาร'")
    else:
        # Quick Filter Section with clear, readable labels
        st.markdown("#### 🎯 ตัวกรองข้อมูลด่วน (เลือกปี พ.ศ. หรือลักษณะเหตุการณ์ได้ทันที)")
        f_col1, f_col2, f_col3 = st.columns([1.5, 2.5, 2])
        with f_col1:
            all_years = sorted(df_incidents["year"].unique(), reverse=True)
            sel_year_str = st.selectbox(
                "📅 เลือกปี พ.ศ. ที่เกิดเหตุ:",
                ["ทั้งหมด (ทุกปี)"] + [f"ปี พ.ศ. {y}" for y in all_years],
                key="filter_year_box"
            )
        with f_col2:
            all_natures = sorted(df_incidents["nature"].unique())
            sel_nature_str = st.selectbox(
                "🔎 เลือกลักษณะเหตุการณ์ (ไส้ใน):",
                ["ทั้งหมด (ทุกประเภท)"] + all_natures,
                key="filter_nature_box",
                help="กรองเฉพาะเคสเฉี่ยวชน, พลัดตกหกล้ม, โดนไฟดูด/ประกายไฟ, สารเคมี หรือของตกใส่"
            )
        with f_col3:
            all_cats = list(df_incidents["category"].unique())
            sel_cat_str = st.selectbox(
                "📁 เลือกแบบฟอร์ม อบ.ปอ.:",
                ["ทั้งหมด (All)"] + [CATEGORY_MAP.get(c, c) for c in all_cats],
                key="filter_cat_box"
            )

        # Apply Filters
        filtered_df = df_incidents.copy()
        if "ทั้งหมด" not in sel_year_str:
            target_y = int(sel_year_str.replace("ปี พ.ศ. ", ""))
            filtered_df = filtered_df[filtered_df["year"] == target_y]

        if "ทั้งหมด" not in sel_nature_str:
            filtered_df = filtered_df[filtered_df["nature"] == sel_nature_str]

        if "ทั้งหมด" not in sel_cat_str:
            filtered_df = filtered_df[filtered_df["category_th"] == sel_cat_str]

        # Top KPI Metric Cards
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.metric("📌 อุบัติเหตุรวมตามตัวกรอง", f"{len(filtered_df)} เคส")
        with kpi2:
            count_ob3 = len(filtered_df[filtered_df["category"] == "OB_PO_3"])
            st.metric("🚗 อบ.ปอ. 3 (ยานพาหนะ/เฉี่ยวชน)", f"{count_ob3} เคส")
        with kpi3:
            count_ob12 = len(filtered_df[filtered_df["category"] == "OB_PO_1_2"])
            st.metric("🚶‍♂️ อบ.ปอ. 1-2 (พนักงาน/ทรัพย์สิน)", f"{count_ob12} เคส")
        with kpi4:
            count_ob4 = len(filtered_df[filtered_df["category"] == "OB_PO_4"])
            st.metric("👥 อบ.ปอ. 4 (ประชาชนบาดเจ็บ)", f"{count_ob4} เคส")

        st.markdown("---")

        # Visual Analytics Charts Row (Horizontal Bar Charts for Clear Reading)
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.markdown("##### 📁 สัดส่วนอุบัติเหตุตามแบบฟอร์ม อบ.ปอ. (แนวนอน อ่านง่าย)")
            cat_counts = filtered_df["category_th"].value_counts().reset_index()
            cat_counts.columns = ["แบบฟอร์ม", "จำนวนเคส"]
            if not cat_counts.empty:
                chart_cat = alt.Chart(cat_counts).mark_bar(color="#3182ce", cornerRadiusEnd=4).encode(
                    x=alt.X("จำนวนเคส:Q", title="จำนวนเคส", axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y("แบบฟอร์ม:N", title=None, sort="-x", axis=alt.Axis(labelLimit=300)),
                    tooltip=["แบบฟอร์ม", "จำนวนเคส"]
                ).properties(height=180)
                text_cat = chart_cat.mark_text(align="left", baseline="middle", dx=5, color="#e2e8f0", fontWeight="bold").encode(text="จำนวนเคส:Q")
                st.altair_chart(chart_cat + text_cat, use_container_width=True)
            else:
                st.info("ไม่มีข้อมูลตามเงื่อนไขที่เลือก")

        with chart_col2:
            st.markdown("##### 🔍 การจำแนกลักษณะการเกิดเหตุจริงจากไส้ใน (แนวนอน อ่านง่าย)")
            nature_counts = filtered_df["nature"].value_counts().reset_index()
            nature_counts.columns = ["ลักษณะเหตุการณ์", "จำนวนเคส"]
            if not nature_counts.empty:
                chart_nat = alt.Chart(nature_counts).mark_bar(color="#dd6b20", cornerRadiusEnd=4).encode(
                    x=alt.X("จำนวนเคส:Q", title="จำนวนเคส", axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y("ลักษณะเหตุการณ์:N", title=None, sort="-x", axis=alt.Axis(labelLimit=300)),
                    tooltip=["ลักษณะเหตุการณ์", "จำนวนเคส"]
                ).properties(height=220)
                text_nat = chart_nat.mark_text(align="left", baseline="middle", dx=5, color="#e2e8f0", fontWeight="bold").encode(text="จำนวนเคส:Q")
                st.altair_chart(chart_nat + text_nat, use_container_width=True)
            else:
                st.info("ไม่มีข้อมูลตามเงื่อนไขที่เลือก")

        st.markdown("---")

        # Interactive Drill-down Table & Document Downloader
        st.markdown(f"#### 📋 รายการอุบัติเหตุตามเงื่อนไขที่เลือก ({len(filtered_df)} เคส)")
        st.caption("💡 เลื่อนดูรายการด้านล่าง และเลือกเคสเพื่อเปิดอ่านเนื้อหาไส้ในฉบับเต็ม หรือกดดาวน์โหลดไฟล์ PDF ได้ทันที")

        # Format table for display
        display_df = filtered_df[["year", "category_th", "nature", "filename", "summary"]].copy()
        display_df.columns = ["ปี พ.ศ.", "แบบฟอร์ม", "ลักษณะเหตุการณ์ (ไส้ใน)", "ชื่อไฟล์เอกสาร", "สรุปพฤติการณ์สั้นๆ"]
        display_df.insert(0, "ลำดับ", range(1, len(display_df) + 1))

        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            height=280
        )

        # Drill-down Inspection Panel
        st.markdown("##### 🔎 เจาะลึกและดาวน์โหลดเอกสารต้นฉบับ:")
        file_options = {r["file_id"]: f"#{idx+1} [{r['nature']}] {r['filename']} (ปี {r['year']})" for idx, r in filtered_df.iterrows()}

        if file_options:
            drill_col1, drill_col2 = st.columns([3, 1])
            with drill_col1:
                selected_fid = st.selectbox(
                    "เลือกเคสที่ต้องการเปิดดูและดาวน์โหลด:",
                    options=list(file_options.keys()),
                    format_func=lambda x: file_options[x]
                )

            chosen_record = filtered_df[filtered_df["file_id"] == selected_fid].iloc[0]

            with drill_col2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                actual_path = DOCUMENTS_DIR / chosen_record["filepath"]
                if actual_path.exists():
                    with open(actual_path, "rb") as f_down:
                        st.download_button(
                            label=f"📥 โหลด PDF เคสนี้",
                            data=f_down.read(),
                            file_name=chosen_record["filename"],
                            mime="application/pdf",
                            key=f"drill_dl_{selected_fid}",
                            use_container_width=True
                        )

            with st.expander(f"📖 เปิดอ่านเนื้อหา 'ไส้ใน' ฉบับเต็มของ {chosen_record['filename']}"):
                # Retrieve all pages text from DB
                conn_d = get_connection(DB_PATH)
                try:
                    cur_d = conn_d.cursor()
                    cur_d.execute("SELECT page_number, raw_text FROM document_pages WHERE file_id = ? ORDER BY page_number ASC", (int(selected_fid),))
                    pages_d = cur_d.fetchall()
                    for p_d in pages_d:
                        st.markdown(f"**--- หน้า {p_d['page_number']} ---**")
                        st.text_area(f"หน้า {p_d['page_number']}", value=p_d["raw_text"], height=160, disabled=True, key=f"drill_pg_{selected_fid}_{p_d['page_number']}", label_visibility="collapsed")
                finally:
                    conn_d.close()

        # CSV Export Button
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        csv_data = filtered_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📊 ส่งออกตารางสถิตินี้เป็นไฟล์ Excel/CSV",
            data=csv_data,
            file_name=f"Safety_Incidents_Statistics_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

# ==============================================================================
# TAB 1: INCIDENT AI ANALYZER (NEW CORE FEATURE)
# ==============================================================================
with tab_analyzer:
    st.subheader("🧠 ระบบวิเคราะห์อุบัติเหตุใหม่ เทียบเคสเก่าในอดีต (อบ.ปอ. 1-4) และตรวจจับการผิด WI")
    st.caption("นำรายงานอุบัติเหตุที่เกิดขึ้นใหม่มาวิเคราะห์ โปรแกรมจะค้นหาเคสเก่าที่คล้ายกัน ตรวจสอบว่าผิดข้อกำหนด WI ใด พร้อมวิเคราะห์สาเหตุรากเหง้า (Root Cause) และวิธีป้องกัน")

    input_mode = st.radio(
        "เลือกวิธีนำเข้าข้อมูลเคสใหม่:",
        ["✍️ พิมพ์หรือวางข้อความรายงานเหตุการณ์", "📄 อัปโหลดไฟล์ PDF รายงานอุบัติเหตุ"],
        horizontal=True
    )

    incident_text = ""
    incident_title = ""
    source_filename = ""

    if input_mode == "✍️ พิมพ์หรือวางข้อความรายงานเหตุการณ์":
        col_t1, col_t2 = st.columns([3, 1])
        with col_t1:
            incident_title = st.text_input("หัวข้อหรือเลขที่รายงานเหตุการณ์:", value="รายงานอุบัติเหตุเคสใหม่ (ทดสอบ)")
        with col_t2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("📋 ลองโหลดเคสตัวอย่าง (Sample)"):
                st.session_state["sample_incident_text"] = (
                    "รายงานอุบัติเหตุ: วันที่ 15 ตุลาคม 2567 เวลา 14:15 น. "
                    "ช่างซ่อมบำรุงฝ่ายผลิตกำลังเดินตรวจเช็กปั๊มน้ำมันไฮดรอลิกในอาคาร 2 "
                    "ได้เกิดลื่นไถลจากคราบน้ำมันหล่อลื่นที่รั่วซึมอยู่บนพื้นคอนกรีต เสียหลักล้มกระแทกแท่นเครื่องจักร "
                    "ข้อเท้าขวาเคล็ดและฟกช้ำ และฝาครอบมอเตอร์แตกเสียหาย พนักงานสวมรองเท้าผ้าใบธรรมดา ไม่ได้สวมรองเท้านิรภัย "
                    "และบริเวณดังกล่าวยังไม่ได้มีการเช็ดคราบน้ำมันหรือตั้งป้ายเตือนระวังพื้นลื่น"
                )

        default_txt = st.session_state.get("sample_incident_text", "")
        incident_text = st.text_area(
            "รายละเอียดพฤติการณ์การเกิดเหตุ (Incident Description):",
            value=default_txt,
            height=140,
            placeholder="พิมพ์หรือคัดลอกรายละเอียดอุบัติเหตุ วันที่ แผนก สถานที่ พฤติการณ์การเกิดเหตุ และอาการบาดเจ็บที่นี่..."
        )

    else:
        uploaded_file = st.file_uploader("เลือกไฟล์ PDF รายงานอุบัติเหตุเคสใหม่:", type=["pdf"])
        if uploaded_file:
            source_filename = uploaded_file.name
            incident_title = Path(uploaded_file.name).stem
            # Save temporarily and extract text
            temp_path = BASE_DIR / "documents" / "New_Incidents" / uploaded_file.name
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            extracted = extract_pdf_data(temp_path)
            if extracted.get("error"):
                st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์ PDF: {extracted['error']}")
            else:
                extracted_pages_text = "\n\n".join([p["raw_text"] for p in extracted["pages"] if p["raw_text"].strip()])
                total_chars = sum([p["char_count"] for p in extracted["pages"]])

                if total_chars > 0:
                    st.success(f"อ่านไฟล์ `{uploaded_file.name}` สำเร็จ ({extracted['total_pages']} หน้า, {total_chars} ตัวอักษร)")
                    if "uploaded_pdf_text" not in st.session_state or st.session_state.get("last_uploaded_file") != uploaded_file.name:
                        st.session_state["uploaded_pdf_text"] = extracted_pages_text
                        st.session_state["last_uploaded_file"] = uploaded_file.name
                else:
                    st.warning(f"⚠️ ไฟล์ `{uploaded_file.name}` เป็น **ภาพสแกนจากเอกสารกระดาษ (Scanned PDF)** ซึ่งยังไม่มีตัวหนังสือดิจิทัลฝังอยู่ในไฟล์")
                    
                    st.markdown("""
                    <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 12px; border-radius: 4px; margin-bottom: 15px;">
                        <p style="margin: 0; font-size: 0.95rem; color: #1e293b;">
                            <b>📌 ทางเลือกในการวิเคราะห์สำหรับเอกสารภาพสแกน:</b><br>
                            1. <b>ใช้ AI Vision สแกนอ่านทุกหน้า:</b> กดปุ่มด้านล่างเพื่อให้ AI อ่านข้อความและภาพสรุปพฤติการณ์ออกมาอัตโนมัติ (มีค่าบริการ OpenAI ~0.20 - 0.50 บาท/เคส)<br>
                            2. <b>พิมพ์หรือวางข้อความสรุปเอง:</b> พิมพ์รายละเอียดพฤติการณ์ลงในช่องข้อความด้านล่างโดยตรง (<b>ฟรี 100%</b> ไม่เสียค่าใช้จ่าย)
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("👁️ วิเคราะห์และสรุปข้อเท็จจริงจากเอกสารสแกนด้วย AI Vision (GPT)", type="primary", use_container_width=True, help="AI Vision จะอ่านภาพสแกนทุกหน้าและสรุปพฤติการณ์ วันเวลา ผู้บาดเจ็บ และสาเหตุให้อัตโนมัติ"):
                        if not st.session_state.openai_api_key:
                            st.error("❌ กรุณาใส่ OpenAI API Key ในแถบซ้ายมือก่อนใช้งาน AI Vision")
                        else:
                            with st.spinner(f"👁️ AI Vision กำลังอ่านและสรุปพฤติการณ์จากภาพสแกนทุกหน้า (พร้อมข้ามภาพแผลสดอัตโนมัติ)..."):
                                try:
                                    v_model = model_choice if model_choice in ["gpt-4o", "gpt-4o-mini"] else "gpt-4o-mini"
                                    extracted_vision, v_cost = extract_text_with_vision(
                                        temp_path,
                                        api_key=st.session_state.openai_api_key,
                                        model_name=v_model,
                                        max_pages=6
                                    )
                                    st.session_state["uploaded_pdf_text"] = extracted_vision
                                    st.session_state["last_uploaded_file"] = uploaded_file.name
                                    st.success(f"✅ AI Vision สรุปเนื้อหาจากเอกสารสำเร็จ! (ค่าบริการเคสนี้: ~{v_cost['cost_thb']:.2f} บาท | {v_cost['total_tokens']:,} tokens)")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"เกิดข้อผิดพลาดในการเรียก AI Vision: {e}")

                incident_text = st.text_area(
                    "รายละเอียดพฤติการณ์การเกิดเหตุ (สำหรับส่งไปวิเคราะห์):",
                    value=st.session_state.get("uploaded_pdf_text", extracted_pages_text),
                    height=140,
                    placeholder="พิมพ์หรือคัดลอกรายละเอียดอุบัติเหตุ วันที่ แผนก สถานที่ พฤติการณ์การเกิดเหตุ..."
                )

    # Form Selection & Analyst Name
    st.markdown("#### 📋 การกำหนดรูปแบบรายงานและผู้วิเคราะห์")
    col_form, col_analyst = st.columns([2, 2])
    with col_form:
        target_form = st.selectbox(
            "เลือกประเภทแบบฟอร์มรายงานที่ต้องการสร้าง:",
            [
                "อุบัติภัยสำหรับพนักงาน (อบ.ปอ. 1-2)",
                "อุบัติภัยสำหรับพนักงานขับยานพาหนะ (อบ.ปอ. 3)",
                "อุบัติภัยสำหรับประชาชน/บุคคลภายนอก (อบ.ปอ. 4)"
            ],
            index=st.session_state.get("default_form_choice", 0),
            help="เลือกว่าต้องการให้ระบบร่างผลวิเคราะห์ออกมาตามแบบฟอร์ม อบ.ปอ. 1-2, 3 หรือ 4"
        )
    with col_analyst:
        analyst_name = st.text_input(
            "ชื่อ-สกุล ผู้วิเคราะห์ (ลงชื่อท้ายรายงาน):",
            value="นายนฤเทพ อุบลรัศมี",
            help="ระบุชื่อที่จะปรากฏท้ายรายงานผลการวิเคราะห์"
        )

    # Trigger Analysis Button
    st.markdown("---")
    btn_col1, btn_col2 = st.columns([2, 5])
    with btn_col1:
        start_analysis = st.button("🚀 เริ่มวิเคราะห์อุบัติเหตุ (Analyze Now)", type="primary", use_container_width=True)

    if start_analysis:
        if not incident_text.strip():
            st.warning("⚠️ กรุณาระบุรายละเอียดเหตุการณ์ก่อนเริ่มวิเคราะห์")
        else:
            with st.spinner("🔍 กำลังอ่านไส้ในของเหตุการณ์, ค้นหาเคสแม่แบบที่คล้ายคลึง, และจัดทำแบบฟอร์ม..."):
                # Map form choice to specific document category
                form_cat_map = {
                    "อุบัติภัยสำหรับพนักงาน (อบ.ปอ. 1-2)": "OB_PO_1_2",
                    "อุบัติภัยสำหรับพนักงานขับยานพาหนะ (อบ.ปอ. 3)": "OB_PO_3",
                    "อุบัติภัยสำหรับประชาชน/บุคคลภายนอก (อบ.ปอ. 4)": "OB_PO_4"
                }
                target_cat = form_cat_map.get(form_choice)

                # Step 1: Find similar past incidents (filtered to same form category)
                similar_cases = find_similar_past_incidents(
                    incident_text, 
                    top_n=3, 
                    db_path=DB_PATH,
                    target_category=target_cat
                )

                # Step 2: Match relevant WI safety rules
                matched_wi = match_relevant_wi(incident_text, top_n=3, db_path=DB_PATH)

                # Step 3: Generate Analysis (GPT if enabled and key available, else Offline Engine)
                if st.session_state.gpt_enabled and st.session_state.openai_api_key:
                    analysis_md, engine_used, g_cost = generate_gpt_analysis(
                        incident_text=incident_text,
                        similar_cases=similar_cases,
                        matched_wi=matched_wi,
                        api_key=st.session_state.openai_api_key,
                        model_name=model_choice,
                        target_form=target_form,
                        analyst_name=analyst_name
                    )
                else:
                    analysis_md = generate_offline_analysis(
                        incident_text=incident_text,
                        similar_cases=similar_cases,
                        matched_wi=matched_wi,
                        target_form=target_form,
                        analyst_name=analyst_name
                    )
                    engine_used = "Offline Safety Matcher (ระบบออฟไลน์)"
                    g_cost = None

                # Save record to session state
                st.session_state.analysis_result = {
                    "title": incident_title or "รายงานอุบัติเหตุ",
                    "text": incident_text,
                    "filename": source_filename,
                    "similar_cases": similar_cases,
                    "matched_wi": matched_wi,
                    "analysis_md": analysis_md,
                    "engine_used": engine_used,
                    "cost_info": g_cost,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

    # Display Analysis Results
    if st.session_state.analysis_result:
        res = st.session_state.analysis_result

        st.markdown(f"### 📑 ผลการวิเคราะห์: {res['title']}")
        cost_txt = f" | 💵 ค่าบริการเคสนี้: **~{res['cost_info']['cost_thb']:.2f} บาท** ({res['cost_info']['total_tokens']:,} tokens)" if res.get("cost_info") else " | 💵 ค่าบริการ: **ฟรี (ระบบออฟไลน์)**"
        st.caption(f"🤖 ประมวลผลโดย: **{res['engine_used']}** | เวลา: {res['timestamp']}{cost_txt}")

        # Top 2 Columns for Side-by-side Evidence (Similar Cases & Matched WI)
        c_left, c_right = st.columns(2)

        with c_left:
            st.markdown("#### 🔄 เคสเก่าในอดีตที่คล้ายที่สุด (อบ.ปอ.)")
            if not res["similar_cases"]:
                st.info("ไม่พบเคสในอดีตที่ตรงกัน")
            else:
                for idx_c, c in enumerate(res["similar_cases"]):
                    st.markdown(f"""
                    <div class='result-card'>
                        <div>
                            <span class='score-badge'>ดัชนีคำค้นหาตรงกัน {c['similarity_score']}%</span>
                            <span class='category-badge'>{c['category_th']}</span>
                        </div>
                        <h5 style='margin:6px 0; color:#2b6cb0;'>{c['filename']} (หน้า {c['page_number']})</h5>
                        <div class='snippet-box'>{c['snippet']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Expandable Full Text Reader
                    with st.expander(f"📖 เปิดอ่านเนื้อหาฉบับเต็ม ({c['filename']} หน้า {c['page_number']})"):
                        st.text_area("เนื้อหาหน้าเอกสาร:", value=c["raw_text"], height=160, disabled=True, key=f"full_txt_c_{idx_c}")

                    # Download Original PDF Button
                    actual_pdf_path = DOCUMENTS_DIR / c.get("filepath", "")
                    if actual_pdf_path.exists():
                        with open(actual_pdf_path, "rb") as f_pdf:
                            st.download_button(
                                label=f"📥 ดาวน์โหลดไฟล์ PDF ({c['filename']})",
                                data=f_pdf.read(),
                                file_name=c["filename"],
                                mime="application/pdf",
                                key=f"dl_pdf_c_{idx_c}",
                                use_container_width=True
                            )
                    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        with c_right:
            st.markdown("#### ⚠️ คู่มือ WI และข้อกำหนดที่เกี่ยวข้อง")
            if not res["matched_wi"]:
                st.info("ไม่พบคู่มือ WI ที่ตรงกัน")
            else:
                for idx_w, w in enumerate(res["matched_wi"]):
                    st.markdown(f"""
                    <div class='result-card'>
                        <div>
                            <span class='score-badge'>ความเกี่ยวข้อง {w['relevance_score']}%</span>
                            <span class='category-badge'>คู่มือ WI</span>
                        </div>
                        <h5 style='margin:6px 0; color:#2b6cb0;'>{w['filename']} (หน้า {w['page_number']})</h5>
                        <div class='snippet-box'>{w['snippet']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Expandable Full Text Reader
                    with st.expander(f"📖 เปิดอ่านข้อกำหนดฉบับเต็ม ({w['filename']} หน้า {w['page_number']})"):
                        st.text_area("เนื้อหาข้อกำหนด:", value=w["raw_text"], height=160, disabled=True, key=f"full_txt_w_{idx_w}")

                    # Download Original PDF Button
                    actual_wi_path = DOCUMENTS_DIR / w.get("filepath", "")
                    if actual_wi_path.exists():
                        with open(actual_wi_path, "rb") as f_wi:
                            st.download_button(
                                label=f"📥 ดาวน์โหลดไฟล์ PDF คู่มือ ({w['filename']})",
                                data=f_wi.read(),
                                file_name=w["filename"],
                                mime="application/pdf",
                                key=f"dl_pdf_w_{idx_w}",
                                use_container_width=True
                            )
                    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Prompt for ChatGPT Plus
        st.markdown("---")
        with st.expander("📋 คัดลอกข้อมูลสรุปเพื่อนำไปถาม ChatGPT Plus (ที่สมัครรายเดือนไว้)"):
            st.caption("หากท่านมี ChatGPT Plus อยู่แล้ว สามารถคัดลอกข้อความด้านล่างนี้ไปวางในหน้าเว็บ ChatGPT เพื่อให้ช่วยวิเคราะห์ต่อได้ทันทีครับ:")
            chatgpt_prompt = f"""ช่วยวิเคราะห์อุบัติเหตุนี้ตามหลักความปลอดภัยและอาชีวอนามัย (Safety Specialist):

[รายละเอียดอุบัติเหตุใหม่]:
{res['text']}

[เคสในอดีตที่ระบบตรวจพบว่าคล้ายกัน]:
"""
            for i, c in enumerate(res["similar_cases"][:2]):
                chatgpt_prompt += f"- เคสที่ {i+1}: {c['filename']} (หมวด {c['category_th']}) ดัชนีคำตรงกัน {c['similarity_score']}%\n  เนื้อหา: {c['snippet']}\n"

            chatgpt_prompt += "\n[คู่มือขั้นตอนการปฏิบัติงาน (WI) ที่เกี่ยวข้อง]:\n"
            for i, w in enumerate(res["matched_wi"][:2]):
                chatgpt_prompt += f"- คู่มือ: {w['filename']} ความสอดคล้อง {w['relevance_score']}%\n  ข้อกำหนด: {w['snippet']}\n"

            chatgpt_prompt += """
กรุณาวิเคราะห์:
1. พฤติการณ์การเกิดเหตุและผลกระทบ
2. เปรียบเทียบกับเคสเก่า ซ้ำรอยเดิมหรือไม่
3. สันนิษฐานว่าผิด WI ข้อไหน อย่างไร
4. หาสาเหตุรากเหง้า (5 Whys / Unsafe Acts / Unsafe Conditions)
5. เสนอแนะมาตรการป้องกันการเกิดซ้ำ (CAPA)
"""
            st.code(chatgpt_prompt, language="markdown")

        # Full Analysis Report Markdown
        st.markdown("---")
        st.markdown("### 📊 รายงานวิเคราะห์หาสาเหตุรากเหง้าและวิธีป้องกัน (Full Report)")
        st.markdown(res["analysis_md"])

        # Action Buttons: Save to DB & Export
        st.markdown("---")
        act_col1, act_col2, act_col3 = st.columns([2, 2.5, 2.5])
        with act_col1:
            if st.button("💾 บันทึกผลวิเคราะห์ลงฐานข้อมูล", type="primary", use_container_width=True):
                rec_id = save_analysis_record(
                    incident_title=res["title"],
                    incident_text=res["text"],
                    source_filename=res["filename"],
                    similar_cases=res["similar_cases"],
                    matched_wi=res["matched_wi"],
                    analysis_markdown=res["analysis_md"],
                    ai_engine=res["engine_used"],
                    db_path=DB_PATH
                )
                st.success(f"✅ บันทึกผลวิเคราะห์ลงฐานข้อมูลเรียบร้อยแล้ว (ID: #{rec_id})")

        with act_col2:
            # Generate Word Document (.docx)
            past_comp_txt = ""
            if res.get("similar_cases"):
                c0 = res["similar_cases"][0]
                past_comp_txt = f"เคสในอดีตที่ตรวจพบคำสำคัญใกล้เคียง: {c0['filename']} (ดัชนีคำค้นหาตรงกัน {c0['similarity_score']}%)\nพฤติการณ์เคสเดิม: {c0['snippet']}"

            wi_eval_txt = ""
            if res.get("matched_wi"):
                w0 = res["matched_wi"][0]
                wi_eval_txt = f"คู่มือ WI ที่เกี่ยวข้อง: {w0['filename']} (ความสอดคล้อง {w0['relevance_score']}%)\nข้อกำหนด: {w0['snippet']}"

            docx_data = create_safety_report_docx(
                report_title=res["title"],
                target_form=target_form,
                incident_meta=f"อุบัติภัยราย: {res['title']} (วันเวลาเกิดเหตุ: ตามแบบฟอร์มที่ส่งมา)",
                incident_text=res["text"],
                past_comparison=past_comp_txt,
                causes_text="",
                wi_evaluation=wi_eval_txt,
                prevention_text="",
                analyst_name=analyst_name,
                analysis_markdown=res.get("analysis_md", "")
            )

            st.download_button(
                label="📥 ดาวน์โหลดไฟล์ Word (.docx) พร้อมพิมพ์",
                data=docx_data,
                file_name=f"Safety_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )

        with act_col3:
            st.download_button(
                label="📄 ดาวน์โหลดข้อความ (Markdown)",
                data=f"# {res['title']}\n\n" + res["analysis_md"],
                file_name=f"Safety_Analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True
            )

    # History of past analyses
    st.markdown("---")
    with st.expander("📚 ประวัติผลการวิเคราะห์อุบัติเหตุที่เคยบันทึกไว้ในระบบ"):
        past_analyses = list_saved_analyses(DB_PATH)
        if not past_analyses:
            st.info("ยังไม่มีประวัติการวิเคราะห์ที่บันทึกไว้")
        else:
            for pa in past_analyses:
                st.markdown(f"**#{pa['id']} - {pa['incident_title']}** | สร้างเมื่อ: {pa['created_at']} | เครื่องมือ: `{pa['ai_engine']}`")
                with st.expander(f"ดูรายงานของ #{pa['id']}"):
                    st.markdown(pa["analysis_markdown"])

# ==============================================================================
# TAB 2: SEARCH (Full-Text Search)
# ==============================================================================
with tab_search:
    st.subheader("🔍 ค้นหาเอกสารความปลอดภัย (Full-Text Search)")
    st.caption("ค้นหาข้อความภาษาไทยและอังกฤษจากคลัง อบ.ปอ. 1-4, WI, และ Work Permit")

    search_col1, search_col2, search_col3 = st.columns([3, 1.5, 1.5])
    with search_col1:
        query_input = st.text_input(
            "พิมพ์คำค้นหา (Keyword):",
            placeholder="เช่น ที่อับอากาศ, สารเคมี, รถโฟล์กลิฟต์, รองเท้านิรภัย...",
            key="search_query"
        )
    with search_col2:
        category_options = ["ทั้งหมด (All Categories)"] + list(CATEGORY_MAP.keys())
        selected_cat_raw = st.selectbox(
            "หมวดหมู่เอกสาร:",
            category_options,
            format_func=lambda x: "ทั้งหมด (All Categories)" if "All" in x else CATEGORY_MAP.get(x, x),
            key="search_category"
        )
        selected_cat = None if "All" in selected_cat_raw else selected_cat_raw

    with search_col3:
        sort_choice = st.selectbox(
            "จำนวนผลลัพธ์สูงสุด:",
            [20, 50, 100],
            key="search_limit"
        )

    if query_input and query_input.strip():
        with st.spinner("กำลังค้นหาข้อมูล..."):
            results = search_documents(
                query=query_input,
                category=selected_cat,
                limit=sort_choice,
                db_path=DB_PATH
            )

        st.markdown(f"**พบผลลัพธ์ทั้งหมด {len(results)} รายการ**")

        if not results:
            st.info("ℹ️ ไม่พบเอกสารที่ตรงกับคำค้นหา ลองตรวจสอบคำสะกด หรือเปลี่ยนหมวดหมู่เอกสาร")
        else:
            for idx, res in enumerate(results):
                with st.container():
                    st.markdown(f"""
                    <div class='result-card'>
                        <div>
                            <span class='category-badge'>📁 {res['category_th']}</span>
                            <span class='page-badge'>📄 หน้า {res['page_number']} / {res['total_pages']}</span>
                        </div>
                        <h4 style='margin: 8px 0 4px 0; color:#2b6cb0;'>{res['filename']}</h4>
                        <div class='snippet-box'>
                            {res['snippet']}
                        </div>
                        <div style='font-size: 0.8rem; color:#718096; margin-top: 6px;'>
                            📅 นำเข้าเมื่อ: {res['imported_at']} | 🔒 SHA-256: <code>{res['sha256'][:16]}...</code>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    btn_col1, btn_col2 = st.columns([2, 8])
                    with btn_col1:
                        if st.button(f"📖 เปิดอ่านหน้านี้", key=f"view_btn_{idx}_{res['page_id']}"):
                            st.session_state.selected_page_id = res["page_id"]
                            st.success(f"โหลดข้อมูลหน้า {res['page_number']} เรียบร้อย! กรุณาคลิกแท็บ '📖 เปิดอ่านข้อความต้นฉบับ'")
    else:
        st.info("💡 กรุณาพิมพ์คำค้นหาเพื่อเริ่มค้นหาเอกสาร")

# ==============================================================================
# TAB 3: DOCUMENT READER
# ==============================================================================
with tab_reader:
    st.subheader("📖 เปิดดูข้อความต้นฉบับของแต่ละหน้า (Original Page Reader)")
    st.caption("อ่านเนื้อหาข้อความฉบับเต็มของแต่ละหน้า โดยคงความถูกต้อง 100% ตามไฟล์ PDF ต้นฉบับ")

    conn = get_connection(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, category, total_pages, sha256, file_size, imported_at, filepath FROM files WHERE is_active = 1 ORDER BY filename ASC")
        all_active_files = cursor.fetchall()
    finally:
        conn.close()

    if not all_active_files:
        st.warning("ยังไม่มีเอกสารในฐานข้อมูล กรุณาสแกนเอกสารในแท็บ 'สแกนและซิงค์เอกสาร'")
    else:
        file_map = {row["id"]: row for row in all_active_files}
        
        default_file_idx = 0
        default_page_num = 1
        if st.session_state.selected_page_id:
            detail = get_page_detail(st.session_state.selected_page_id, DB_PATH)
            if detail and detail["file_id"] in file_map:
                file_ids = list(file_map.keys())
                default_file_idx = file_ids.index(detail["file_id"])
                default_page_num = detail["page_number"]

        sel_col1, sel_col2 = st.columns([3, 1])
        with sel_col1:
            selected_file_id = st.selectbox(
                "เลือกเอกสาร:",
                options=list(file_map.keys()),
                index=default_file_idx,
                format_func=lambda fid: f"{file_map[fid]['filename']} ({CATEGORY_MAP.get(file_map[fid]['category'], file_map[fid]['category'])})"
            )
        
        target_file = file_map[selected_file_id]
        total_p = target_file["total_pages"]

        with sel_col2:
            selected_page_num = st.number_input(
                "เลขหน้า:",
                min_value=1,
                max_value=max(1, total_p),
                value=min(default_page_num, max(1, total_p)),
                step=1
            )

        conn = get_connection(DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, page_number, raw_text, char_count, created_at
                FROM document_pages
                WHERE file_id = ? AND page_number = ?
            """, (selected_file_id, selected_page_num))
            page_data = cursor.fetchone()
        finally:
            conn.close()

        st.markdown(f"""
        <div style='background-color:#edf2f7; padding:12px; border-radius:6px; margin: 10px 0;'>
            <b>📁 หมวดหมู่:</b> {CATEGORY_MAP.get(target_file['category'], target_file['category'])} &nbsp;|&nbsp;
            <b>📄 หน้า:</b> {selected_page_num} จากทั้งหมด {total_p} หน้า &nbsp;|&nbsp;
            <b>📦 ขนาดไฟล์:</b> {round(target_file['file_size']/1024, 2)} KB &nbsp;|&nbsp;
            <b>🔒 SHA-256:</b> <span style='font-family:monospace; font-size:0.85rem;'>{target_file['sha256']}</span>
        </div>
        """, unsafe_allow_html=True)

        if page_data:
            st.markdown(f"**ข้อความต้นฉบับหน้า {selected_page_num} ({page_data['char_count']} ตัวอักษร):**")
            st.text_area(
                label=f"เนื้อหาหน้า {selected_page_num}",
                value=page_data["raw_text"],
                height=380,
                disabled=True,
                label_visibility="collapsed"
            )
        else:
            st.warning("ไม่พบข้อมูลเนื้อหาของหน้านี้")

# ==============================================================================
# TAB 4: SYNC & INGESTION
# ==============================================================================
with tab_sync:
    st.subheader("🔄 สแกนและซิงค์เอกสาร (Sync & Ingestion Dashboard)")
    st.caption("ระบบจะสแกนโฟลเดอร์เอกสาร อ่านข้อความแยกหน้า ตรวจจับไฟล์ซ้ำ (SHA-256) และอัปเดตไฟล์ที่มีการแก้ไข")

    st.info(f"📂 **โฟลเดอร์เอกสารต้นฉบับ:** `{DOCUMENTS_DIR}` (เปิดอ่านแบบ Read-Only ปลอดภัย ไม่แก้ไขไฟล์ต้นฉบับ)")

    col_btn, col_empty = st.columns([2, 5])
    with col_btn:
        start_sync_btn = st.button("🚀 สแกนและอัปเดตเดี๋ยวนี้ (Sync Now)", type="primary", use_container_width=True)

    if start_sync_btn:
        progress_bar = st.progress(0, text="กำลังเตรียมการสแกน...")
        
        def update_progress(current, total, filename):
            percent = int((current / max(1, total)) * 100)
            progress_bar.progress(percent, text=f"กำลังประมวลผล ({current}/{total}): {filename}")

        with st.spinner("กำลังสแกนและประมวลผลเอกสาร..."):
            sync_results = sync_documents(
                docs_dir=DOCUMENTS_DIR,
                db_path=DB_PATH,
                progress_callback=update_progress
            )
        
        progress_bar.progress(100, text="สแกนและซิงค์เสร็จสมบูรณ์!")
        st.success("✅ การสแกนและซิงค์ฐานข้อมูลเสร็จสิ้นเรียบร้อยแล้ว!")

        res_c1, res_c2, res_c3, res_c4, res_c5 = st.columns(5)
        with res_c1:
            st.metric("➕ เพิ่มใหม่", f"{sync_results['added']} ไฟล์")
        with res_c2:
            st.metric("🔄 อัปเดต", f"{sync_results['updated']} ไฟล์")
        with res_c3:
            st.metric("⏭️ ข้าม (ไม่เปลี่ยน)", f"{sync_results['skipped']} ไฟล์")
        with res_c4:
            st.metric("⚠️ ตรวจพบไฟล์ซ้ำ", f"{sync_results['duplicates']} ไฟล์")
        with res_c5:
            st.metric("❌ ปิดการใช้งาน", f"{sync_results['deactivated']} ไฟล์")

        if sync_results["errors"]:
            st.error("⚠️ พบข้อผิดพลาดในบางไฟล์:")
            for err in sync_results["errors"]:
                st.write(f"- {err}")

    st.markdown("#### 📊 สถิติเอกสารแยกตามหมวดหมู่ในฐานข้อมูล")
    current_stats = load_stats()
    cat_counts = current_stats["category_counts"]
    
    summary_data = []
    for cat_key, cat_name in CATEGORY_MAP.items():
        summary_data.append({
            "รหัสหมวดหมู่": cat_key,
            "ชื่อหมวดหมู่ (ภาษาไทย)": cat_name,
            "จำนวนเอกสาร": cat_counts.get(cat_key, 0)
        })
    st.table(summary_data)

# ==============================================================================
# TAB 5: BACKUP & HEALTH
# ==============================================================================
with tab_backup:
    st.subheader("💾 สำรองและดูแลฐานข้อมูล (Database Backup & Health)")
    st.caption("ระบบสำรองฐานข้อมูลแบบออนไลน์ (Online Backup API) สามารถสำรองได้ทันทีขณะเปิดใช้งาน")

    b_col1, b_col2 = st.columns([2, 5])
    with b_col1:
        if st.button("📦 สำรองฐานข้อมูลทันที (Backup Now)", type="primary", use_container_width=True):
            with st.spinner("กำลังสำรองข้อมูล..."):
                try:
                    new_backup = backup_database(DB_PATH, BACKUP_DIR)
                    st.success(f"✅ สำรองข้อมูลสำเร็จ!\nที่อยู่ไฟล์: `{new_backup}`")
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาดในการสำรองข้อมูล: {e}")

    st.markdown("#### 🗄️ รายการไฟล์สำรองข้อมูลล่าสุด")
    backup_list = list_backups(BACKUP_DIR)
    if not backup_list:
        st.info("ยังไม่มีประวัติการสำรองข้อมูลในโฟลเดอร์ backups/")
    else:
        st.dataframe(
            backup_list,
            column_config={
                "filename": "ชื่อไฟล์สำรอง",
                "filepath": "ตำแหน่งไฟล์",
                "size_kb": st.column_config.NumberColumn("ขนาด (KB)", format="%.2f KB"),
                "created_at": "วันที่และเวลาที่สำรอง"
            },
            hide_index=True,
            use_container_width=True
        )

    st.markdown("---")
    st.markdown("#### ⚙️ ข้อมูลจำเพาะทางเทคนิคระบบ (System Specifications)")
    import sqlite3
    st.write(f"- **Python Version:** {sys.version.split()[0]}")
    st.write(f"- **SQLite Version:** {sqlite3.sqlite_version}")
    st.write(f"- **Streamlit Version:** {st.__version__}")
    st.write(f"- **NLP & AI Engine:** PyThaiNLP (Offline) + Scikit-Learn TF-IDF + OpenAI GPT")
    st.write(f"- **Data Safety Policy:** Read-Only Source Access (Strict No-Modification Guarantee)")
