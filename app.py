import streamlit as st
from supabase import create_client

# 1. Настройка страницы
st.set_page_config(page_title="SEO Admin", layout="centered")
st.title("🎛️ Управление SEO Фермой")

# 2. Подключение к Supabase через Secrets
# Он сам найдет их в .streamlit/secrets.toml (локально) или в облаке
try:
    supabase_url = st.secrets["supabase"]["url"]
    supabase_key = st.secrets["supabase"]["key"]
    supabase = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"Ошибка подключения к секретам: {e}")
    st.stop()

# 3. Интерфейс
tab1, tab2, tab3 = st.tabs(["➕ Добавить Сайт", "🔑 Загрузить Ключи", "👀 Просмотр Базы"])

# --- ВКЛАДКА 1: ДОБАВЛЕНИЕ САЙТА ---
with tab1:
    st.header("Подключение нового сайта")
    with st.form("add_site_form"):
        col1, col2 = st.columns(2)
        with col1:
            domain = st.text_input("Домен (для удобства)", placeholder="mysite.com")
            username = st.text_input("Login (WordPress)")
        with col2:
            api_url = st.text_input("API URL", placeholder="https://mysite.com")
            app_password = st.text_input("App Password", type="password", help="Пароль приложения, не от админки!")
        
        interval = st.number_input("Интервал постинга (часов)", min_value=1, value=12)
        
        submitted = st.form_submit_button("Сохранить сайт")
        
        if submitted:
            if not domain or not api_url or not username or not app_password:
                st.warning("Заполните все поля!")
            else:
                # Убираем слэш в конце URL если есть
                clean_url = api_url.rstrip("/")
                data = {
                    "domain": domain,
                    "api_url": clean_url,
                    "username": username,
                    "app_password": app_password,
                    "posting_interval": interval
                }
                try:
                    supabase.table("sites").insert(data).execute()
                    st.success(f"Сайт {domain} успешно добавлен в базу!")
                except Exception as e:
                    st.error(f"Ошибка записи в БД: {e}")

# --- ВКЛАДКА 2: ЗАГРУЗКА КЛЮЧЕЙ ---
with tab2:
    st.header("Массовая загрузка задач")
    
    # Сначала получаем список доступных сайтов из базы
    try:
        response = supabase.table("sites").select("id, domain").execute()
        sites = response.data
    except:
        sites = []

    if not sites:
        st.warning("Сначала добавьте хотя бы один сайт во вкладке 1.")
    else:
        # Создаем словарь {domain: id} для удобства
        site_map = {site['domain']: site['id'] for site in sites}
        selected_domain = st.selectbox("Для какого сайта грузим ключи?", list(site_map.keys()))
        
        # Поле ввода
        keywords_text = st.text_area("Список тем (каждая тема с новой строки)", height=300)
        
        if st.button("🚀 Загрузить в очередь"):
            if not keywords_text.strip():
                st.warning("Список пуст.")
            else:
                site_id = site_map[selected_domain]
                # Разбиваем текст на строки и чистим от пробелов
                lines = [line.strip() for line in keywords_text.split('\n') if line.strip()]
                
                # Формируем данные для отправки
                payload = [{"site_id": site_id, "keyword": k, "status": "new"} for k in lines]
                
                try:
                    supabase.table("keywords").insert(payload).execute()
                    st.success(f"Успешно добавлено {len(payload)} задач для {selected_domain}!")
                except Exception as e:
                    st.error(f"Ошибка записи: {e}")

# --- ВКЛАДКА 3: ПРОСМОТР (ДЛЯ ТЕСТА) ---
with tab3:
    st.subheader("Статистика очереди")
    if st.button("Обновить данные"):
        st.rerun()
        
    # Получаем сырые данные (первые 100)
    try:
        data = supabase.table("keywords").select("keyword, status, created_at").order("created_at", desc=True).limit(20).execute()
        st.dataframe(data.data)
    except Exception as e:
        st.error(e)