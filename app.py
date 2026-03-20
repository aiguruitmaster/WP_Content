import streamlit as st
from supabase import create_client
import pandas as pd
import time

# --- НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(
    page_title="SEO Commander UA",
    page_icon="🚀",
    layout="wide"
)

# --- ПІДКЛЮЧЕННЯ ДО SUPABASE ---
try:
    supabase_url = st.secrets["supabase"]["url"]
    supabase_key = st.secrets["supabase"]["key"]
    supabase = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error("❌ Помилка підключення до бази даних. Перевірте secrets.toml")
    st.stop()

# --- ФУНКЦІЯ АВТОМАТИЧНОЇ СИНХРОНІЗАЦІЇ КЛЮЧІВ ---
def sync_keys():
    state = st.session_state["editor"]
    sid = st.session_state["selected_site_id"]
    df_orig = st.session_state["current_df"]

    # 1. Видалення з бази
    if state["deleted_rows"]:
        ids_to_del = df_orig.iloc[state["deleted_rows"]]["id"].tolist()
        if ids_to_del:
            supabase.table("keywords").delete().in_("id", ids_to_del).execute()

    # 2. Редагування існуючих
    if state["edited_rows"]:
        for idx, changes in state["edited_rows"].items():
            row_id = df_orig.iloc[int(idx)]["id"]
            
            # Очищення перед відправкою (щоб уникнути конфліктів з БД)
            changes.pop("id", None)
            changes.pop("created_at", None)
            changes.pop("site_id", None)
            
            if changes:
                supabase.table("keywords").update(changes).eq("id", row_id).execute()

    # 3. Додавання нових
    if state["added_rows"]:
        for row in state["added_rows"]:
            # Очищення автогенерованих полів
            row.pop("id", None)
            row.pop("created_at", None)
            
            row["site_id"] = sid
            if "status" not in row or not row["status"]: 
                row["status"] = "new"
            supabase.table("keywords").insert(row).execute()

st.title("🎛️ Панель Управління SEO Фермою (UA)")

tab1, tab2, tab3 = st.tabs(["➕ Додати Проект", "📊 Дашборд", "⚙️ Керування Ключами та URL"])

# ==========================================
# ВКЛАДКА 1: ДОДАВАННЯ (З ПОЛЕМ ПАРОЛЯ)
# ==========================================
with tab1:
    st.header("Налаштування нового сайту")
    with st.form("main_add_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            site_link = st.text_input("Посилання (URL)", placeholder="https://vash-sait.com.ua")
            login = st.text_input("Логін (WP Admin)")
            password = st.text_input("Звичайний пароль (для нотаток)", type="password")
            app_password = st.text_input("App Password (для API)", type="password")
        
        with col2:
            lang = st.selectbox("Мова", ["ua", "en", "de", "pl"])
            interval = st.number_input("Інтервал (годин)", min_value=1, value=12)
            keywords_text = st.text_area("Список тем (ключі)", height=150)

        if st.form_submit_button("🚀 Зберегти проект"):
            if site_link and login and app_password:
                clean_link = site_link.strip().rstrip("/")
                try:
                    res = supabase.table("sites").insert({
                        "site_link": clean_link, "login": login, "password": password,
                        "app_password": app_password, "lang": lang,
                        "posting_interval": interval, "is_active": True
                    }).execute()
                    
                    if res.data and keywords_text.strip():
                        sid = res.data[0]['id']
                        lines = [l.strip() for l in keywords_text.split('\n') if l.strip()]
                        payload = [{"site_id": sid, "keyword": k, "status": "new"} for k in lines]
                        supabase.table("keywords").insert(payload).execute()
                    st.success("✅ Проект додано!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e: 
                    st.error(f"Помилка: {e}")

# ==========================================
# ВКЛАДКА 2: ДАШБОРД (З ПОСИЛАННЯМИ НА СТАТТІ)
# ==========================================
with tab2:
    st.header("📊 Стан публікацій")
    try:
        sites_data = supabase.table("sites").select("*").execute().data
        # Завантажуємо ключі разом із посиланнями на статті
        keys_data = supabase.table("keywords").select("site_id, keyword, status, article_link, created_at").execute().data
        
        if sites_data:
            df_keys_all = pd.DataFrame(keys_data) if keys_data else pd.DataFrame()
            
            for s in sites_data:
                with st.expander(f"🌐 {s['site_link']} — {s['lang'].upper()}", expanded=True):
                    sk = df_keys_all[df_keys_all['site_id'] == s['id']] if not df_keys_all.empty else pd.DataFrame()
                    
                    # Метрики
                    c1, c2, c3 = st.columns(3)
                    total = len(sk)
                    done = len(sk[sk['status'].isin(['published', 'done'])]) if not sk.empty else 0
                    c1.metric("Усього тем", total)
                    c2.metric("Готово", done)
                    c3.metric("В черзі", total - done)
                    
                    if total > 0: 
                        st.progress(done / total)

                    # ТАБЛИЦЯ ПОСИЛАНЬ
                    if not sk.empty:
                        st.subheader("🔗 Останні опубліковані посилання")
                        done_links = sk[sk['status'].isin(['published', 'done'])].sort_values(by="created_at", ascending=False)
                        if not done_links.empty:
                            st.dataframe(
                                done_links[["keyword", "article_link", "created_at"]],
                                column_config={"article_link": st.column_config.LinkColumn("Посилання на пост")},
                                use_container_width=True, hide_index=True
                            )
                        else: 
                            st.info("Публікацій ще немає.")
        else: 
            st.info("Додайте сайт.")
    except Exception as e: 
        st.error(f"Помилка: {e}")

# ==========================================
# ВКЛАДКА 3: КЕРУВАННЯ (АВТО-СИНХРОНІЗАЦІЯ)
# ==========================================
with tab3:
    st.header("⚙️ Редагування бази")
    all_sites = supabase.table("sites").select("id, site_link").execute().data
    if all_sites:
        site_map = {s['site_link']: s['id'] for s in all_sites}
        sel_name = st.selectbox("Виберіть сайт", options=list(site_map.keys()))
        sid = site_map[sel_name]
        st.session_state["selected_site_id"] = sid
        
        # Видалення сайту
        with st.expander("🗑️ Небезпечна зона (Видалення проекту)"):
            if st.button(f"Видалити {sel_name} та всі ключі", type="primary"):
                supabase.table("keywords").delete().eq("site_id", sid).execute()
                supabase.table("sites").delete().eq("id", sid).execute()
                st.rerun()

        st.divider()
        st.subheader("🔑 Керування ключами та посиланнями")
        st.caption("Змінюйте текст, статус або посилання прямо в таблиці — збережеться автоматично.")
        
        db_keys = supabase.table("keywords").select("*").eq("site_id", sid).order("id").execute().data
        if db_keys:
            df_keys = pd.DataFrame(db_keys)
            st.session_state["current_df"] = df_keys
            st.data_editor(
                df_keys,
                column_config={
                    "id": None, "site_id": None, "created_at": None,
                    "keyword": st.column_config.TextColumn("Ключове слово", width="large"),
                    "status": st.column_config.SelectboxColumn("Статус", options=["new", "published", "error"]),
                    "article_link": st.column_config.TextColumn("URL статті (можна редагувати)")
                },
                num_rows="dynamic", use_container_width=True, key="editor", on_change=sync_keys
            )
    else: 
        st.warning("Додайте сайт.")
