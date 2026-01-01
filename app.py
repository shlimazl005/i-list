import streamlit as st
import pandas as pd
from ics import Calendar, Event
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Pro Takvim (Döngüsel Eşleşme)", page_icon="🔄", layout="wide")

st.title("🔄 Ortopedi Asistan Takvimi (Döngüsel Eşleşme Modu)")
st.markdown("""
**Yenilikler:**
1. **Döngüsel Dağıtım:** Hoca sayısı az olsa bile, artan ameliyat masaları sırayla hocalara paylaştırılır (Masa boş kalmaz).
2. **Nöbet Ertesi:** Kesinlikle "İZİN" olarak işaretlenir.
3. **Nöbetçi Uzman:** Takvim başlığına eklenir.
""")

# --- YARDIMCI FONKSİYONLAR ---

def clean_text_for_comparison(text):
    """Karşılaştırma için metni temizler"""
    if pd.isna(text): return ""
    text = str(text).lower()
    text = text.replace('\xa0', ' ').replace('\t', ' ').strip()
    mapping = {'İ': 'i', 'I': 'ı', 'Ş': 'ş', 'Ğ': 'ğ', 'Ü': 'ü', 'Ö': 'ö', 'Ç': 'ç'}
    for source, target in mapping.items():
        text = text.replace(source.lower(), target)
    return text

def clean_text_display(text):
    """Görüntüleme için temiz metin"""
    if pd.isna(text): return ""
    return str(text).replace('\xa0', ' ').strip()

def extract_number(text):
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 999  # Sayı yoksa sona atması için 999

def deduplicate_columns(df):
    """Aynı isimli sütunları ayırır (NÖBET -> NÖBET_1)"""
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols[cols == dup].index.values.tolist()] = [dup + '_' + str(i) if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    return df

def load_and_fix_df(file):
    """Dosyayı okur ve düzenler"""
    encodings = ['utf-8', 'iso-8859-9', 'windows-1254']
    df = None
    
    for enc in encodings:
        try:
            file.seek(0)
            if file.name.endswith('.csv'):
                df = pd.read_csv(file, header=None, encoding=enc, sep=None, engine='python')
            else:
                df = pd.read_excel(file, header=None)
            break
        except:
            continue
            
    if df is None: return pd.DataFrame()

    # Başlık satırını bul
    header_idx = -1
    for i, row in df.iterrows():
        row_text = " ".join([str(x) for x in row.values]).lower()
        if ('pazartesi' in row_text or 'tarih' in row_text) and ('nöbet' in row_text or 'pol' in row_text):
            header_idx = i
            break
    
    if header_idx != -1:
        df.columns = df.iloc[header_idx].astype(str)
        df = df.iloc[header_idx+1:].reset_index(drop=True)
    else:
        df.columns = df.iloc[0].astype(str)
        df = df.iloc[1:].reset_index(drop=True)
    
    df = deduplicate_columns(df)
    
    try:
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], dayfirst=True, errors='coerce')
        df = df.dropna(subset=[df.columns[0]])
        df = df.set_index(df.columns[0])
    except:
        pass
        
    return df

# --- ARAYÜZ ---
col1, col2 = st.columns(2)
with col1:
    asistan_file = st.file_uploader("1. Asistan Listesi", type=["xlsx", "xls", "csv"])
with col2:
    uzman_file = st.file_uploader("2. Uzman Listesi", type=["xlsx", "xls", "csv"])

user_name_input = st.text_input("Adın Soyadın:", placeholder="Örn: Tahir").strip()

# --- ANA MOTOR ---

if st.button("Takvimi Oluştur 🚀") and asistan_file and uzman_file and user_name_input:
    df_asist = load_and_fix_df(asistan_file)
    df_uzman = load_and_fix_df(uzman_file)
    
    if df_asist.empty:
        st.error("Dosya okunamadı.")
    else:
        cal = Calendar()
        stats = {"Nöbet": 0, "Nöbet Ertesi": 0, "Ameliyat": 0, "Poliklinik": 0, "Diğer": 0}
        
        # Sütun Grupları
        cols_nobet_ekibi = []
        for c in df_asist.columns:
            cl = clean_text_for_comparison(c)
            # Nöbet Ertesi sütunlarını ekibe dahil etme
            if ("nöbet" in cl or "acil" in cl or "icap" in cl) and "ertes" not in cl:
                cols_nobet_ekibi.append(c)

        # Ameliyat sütunlarını bul ve SIRALA (Ameliyat 1, Ameliyat 2...)
        # Sıralama önemli çünkü index mantığı buna göre çalışacak
        raw_cols_ameliyat = [c for c in df_asist.columns if "ameliyat" in clean_text_for_comparison(c) and "nöbet" not in clean_text_for_comparison(c)]
        cols_ameliyat = sorted(raw_cols_ameliyat, key=lambda x: extract_number(x))
        
        found_count = 0
        
        for tarih, row in df_asist.iterrows():
            my_task_col = None
            
            # Kişiyi Bul
            for col in df_asist.columns:
                cell_val = clean_text_for_comparison(row[col])
                target_name = clean_text_for_comparison(user_name_input)
                if len(target_name) > 2 and target_name in cell_val:
                    my_task_col = col
                    break
            
            if not my_task_col: continue

            found_count += 1
            event = Event()
            event.begin = tarih
            event.make_all_day()
            
            display_col = my_task_col.rsplit('_', 1)[0] if '_' in my_task_col else my_task_col
            task_lower = clean_text_for_comparison(display_col)
            
            baslik = ""
            aciklama = f"📅 Tarih: {tarih.strftime('%d.%m.%Y')}\n"

            # ---------------------------------------------------------
            # 1. NÖBET ERTESİ (Kesin İzin)
            # ---------------------------------------------------------
            if "ertes" in task_lower:
                stats["Nöbet Ertesi"] += 1
                baslik = "🛌 NÖBET ERTESİ (İZİN)"
                aciklama += "\nDurum: ÇALIŞMIYOR / DİNLENME"

            # ---------------------------------------------------------
            # 2. NÖBET
            # ---------------------------------------------------------
            elif "nöbet" in task_lower or "icap" in task_lower:
                stats["
