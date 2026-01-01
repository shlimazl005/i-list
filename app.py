import streamlit as st
import pandas as pd
from ics import Calendar, Event

st.set_page_config(page_title="Nöbet Asistanı", page_icon="📅")

st.title("📅 Nöbet ve Ameliyat Takvimi")
st.markdown("Dosyaları yükle, adını yaz ve takvimini al. Gerisini sistem halleder.")

# --- 1. SADECE DOSYA YÜKLEME VE İSİM GİRİŞİ ---
col1, col2 = st.columns(2)
with col1:
    asistan_file = st.file_uploader("1. Asistan Listesi", type=["xlsx", "xls", "csv"])
with col2:
    uzman_file = st.file_uploader("2. Uzman Listesi", type=["xlsx", "xls", "csv"])

# Eski usül, basit isim kutusu
user_name = st.text_input("Adın Soyadın (Listede yazdığı gibi)", placeholder="Örn: Tahir").strip()

# --- ARKA PLAN MOTORU (SENİN GÖRMENE GEREK OLMAYAN KISIM) ---
def clean_df(df):
    df = df.dropna(how='all')
    df.columns = df.columns.astype(str).str.strip()
    return df

def find_col(columns, keywords):
    """Sütun ismini tahmin eder"""
    for col in columns:
        for key in keywords:
            if key in col.lower():
                return col
    return None

def get_expert_columns(expert_cols, task_name):
    """Göreve uygun uzman sütunlarını bulur"""
    task_lower = str(task_name).lower()
    found_cols = []
   
    # Kelime haritası
    keywords_map = {
        "ameliyat": ["ameliyat", "masa", "salon", "oda"],
        "poliklinik": ["poliklinik", "pol", "poli"],
        "servis": ["servis", "klinik"]
    }
   
    search_terms = [task_lower] # Varsayılan olarak görevin kendisini ara
    for key, terms in keywords_map.items():
        if key in task_lower:
            search_terms = terms
            break

    # Sütunları tara
    for col in expert_cols:
        c_low = col.lower()
        if "tarih" in c_low or "nöbet" in c_low: continue
        for term in search_terms:
            if term in c_low:
                found_cols.append(col)
                break
    return found_cols

if asistan_file and user_name:
    if st.button("Takvimi Oluştur"):
        try:
            # Dosyaları oku
            df_asistan = pd.read_excel(asistan_file) if asistan_file.name.endswith('x') else pd.read_csv(asistan_file)
            df_asistan = clean_df(df_asistan)
           
            # Uzman dosyası varsa onu da oku, yoksa boş geç (Hata vermesin)
            df_uzman = pd.DataFrame()
            if uzman_file:
                df_uzman = pd.read_excel(uzman_file) if uzman_file.name.endswith('x') else pd.read_csv(uzman_file)
                df_uzman = clean_df(df_uzman)

            # --- OTOMATİK SÜTUN BULMA ---
            cols_a = df_asistan.columns
            col_date_a = find_col(cols_a, ["tarih", "gün", "date"]) or cols_a[0]
            col_name_a = find_col(cols_a, ["ad", "soyad", "isim", "asistan"]) or cols_a[1]
            col_task_a = find_col(cols_a, ["görev", "yer", "durum"]) or cols_a[2]

            # Uzman sütunları (Eğer dosya varsa)
            col_date_u = None
            col_nobet_u = None
            if not df_uzman.empty:
                cols_u = df_uzman.columns
                col_date_u = find_col(cols_u, ["tarih", "gün", "date"]) or cols_u[0]
                col_nobet_u = find_col(cols_u, ["nöbet", "icap"])
                # Tarihleri düzelt
                df_uzman[col_date_u] = pd.to_datetime(df_uzman[col_date_u], dayfirst=True, errors='coerce')

            # Asistan tarihlerini düzelt
            df_asistan[col_date_a] = pd.to_datetime(df_asistan[col_date_a], dayfirst=True, errors='coerce')

            # --- FİLTRELEME ---
            # Kullanıcının adını içeren satırları bul (Büyük/küçük harf duyarsız)
            my_schedule = df_asistan[df_asistan[col_name_a].astype(str).str.contains(user_name, case=False, na=False)]

            if my_schedule.empty:
                st.error("Girdiğin isim listede bulunamadı. Lütfen kontrol et.")
            else:
                cal = Calendar()
                count = 0

                for index, row in my_schedule.iterrows():
                    current_date = row[col_date_a]
                    if pd.isna(current_date): continue
                   
                    gorev = str(row[col_task_a]).strip()
                   
                    event = Event()
                    event.begin = current_date
                    event.make_all_day()
                   
                    baslik = gorev
                    aciklama = f"Görev: {gorev}"

                    # --- UZMAN EŞLEŞTİRME (Sadece uzman dosyası varsa çalışır) ---
                    if not df_uzman.empty and col_date_u:
                        uzman_row = df_uzman[df_uzman[col_date_u] == current_date]
                       
                        if not uzman_row.empty:
                            uzman_data = uzman_row.iloc[0]
                            gorev_low = gorev.lower()

                            # 1. NÖBETÇİ EŞLEŞMESİ
                            if "nöbet" in gorev_low and col_nobet_u:
                                hoca = uzman_data[col_nobet_u]
                                if pd.notna(hoca):
                                    baslik += f" ({hoca})"
                                    aciklama += f"\nNöbetçi Uzman: {hoca}"
                           
                            # 2. MASALAR / POLİKLİNİKLER (ROUND ROBIN)
                            else:
                                # Bu göreve uygun sütunları bul (Masa, Pol vb.)
                                ilgili_sutunlar = get_expert_columns(df_uzman.columns, gorev)
                               
                                if ilgili_sutunlar:
                                    # O günkü hocaları topla
                                    aktif_hocalar = []
                                    for col in ilgili_sutunlar:
                                        h = uzman_data[col]
                                        if pd.notna(h) and str(h).strip() != "":
                                            aktif_hocalar.append(f"{h}")
                                   
                                    if aktif_hocalar:
                                        # O günkü benim sıramı bul
                                        gunun_asistanlari = df_asistan[
                                            (df_asistan[col_date_a] == current_date) &
                                            (df_asistan[col_task_a] == row[col_task_a])
                                        ]
                                        # İsimleri listeye al
                                        isim_listesi = gunun_asistanlari[col_name_a].astype(str).tolist()
                                       
                                        # Benim ismim listede nerede? (Contains ile bulmaya çalışalım)
                                        my_index = -1
                                        for i, name in enumerate(isim_listesi):
                                            if user_name.lower() in name.lower():
                                                my_index = i
                                                break
                                       
                                        if my_index != -1:
                                            # Matematik: Sıra % Hoca Sayısı
                                            atanan_index = my_index % len(aktif_hocalar)
                                            atanan_hoca = aktif_hocalar[atanan_index]
                                           
                                            baslik += f" - {atanan_hoca}"
                                            aciklama += f"\nEşleşilen Uzman: {atanan_hoca}"

                    event.name = baslik
                    event.description = aciklama
                    cal.events.add(event)
                    count += 1

                st.success(f"✅ {count} adet görev bulundu ve hazırlandı.")
               
                # İNDİRME BUTONU
                safe_name = user_name.replace(" ", "_")
                st.download_button(
                    label="📥 Takvimini İndir",
                    data=str(cal),
                    file_name=f"{safe_name}_Program.ics",
                    mime="text/calendar"
                )

        except Exception as e:
            st.error("Bir hata oluştu. Dosyaların formatı bozuk olabilir.")
            st.error(f"Detay: {e}")
