import streamlit as st
import pandas as pd
from ics import Calendar, Event
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Pro Takvim (Fix)", page_icon="✅", layout="wide")

st.title("✅ Ortopedi Asistan Takvimi (Hatasız Sürüm)")
st.markdown("""
**Özellikler:**
1. **Döngüsel Dağıtım:** Uzman sayısından fazla masa varsa sırayla dağıtır.
2. **Nöbet Ertesi:** Otomatik izin olarak işlenir.
3. **Sayısal Veriler:** İstatistik tablosu hatasız çalışır.
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
    return int(nums[0]) if nums else 999

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

        # Ameliyat sütunlarını bul ve SIRALA
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
            # 1. NÖBET ERTESİ
            # ---------------------------------------------------------
            if "ertes" in task_lower:
                stats["Nöbet Ertesi"] += 1
                baslik = "🛌 NÖBET ERTESİ (İZİN)"
                aciklama += "\nDurum: ÇALIŞMIYOR / DİNLENME"

            # ---------------------------------------------------------
            # 2. NÖBET
            # ---------------------------------------------------------
            elif "nöbet" in task_lower or "icap" in task_lower:
                stats["Nöbet"] += 1
                
                # Nöbetçi Uzmanı Bul
                uzman_adi = ""
                if tarih in df_uzman.index:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        val_uzman = str(u_row[u_col])
                        if "nöbet" in clean_text_for_comparison(val_uzman):
                            uzman_adi = u_col
                            break
                
                if uzman_adi:
                    baslik = f"🚨 NÖBET (Uzm: {uzman_adi})"
                    aciklama += f"\n👨‍⚕️ Nöbetçi Uzman: {uzman_adi}"
                else:
                    baslik = f"🚨 NÖBET ({display_col})"

                # Nöbet Ekibi
                ekip = []
                for nc in cols_nobet_ekibi:
                    val = clean_text_display(row[nc])
                    if len(val) > 2 and "nan" not in val.lower():
                        clean_nc = nc.rsplit('_', 1)[0] if '_' in nc else nc
                        ekip.append(f"- {val} ({clean_nc})")
                
                if ekip:
                    aciklama += f"\n\n💀 NÖBET EKİBİ:\n" + "\n".join(ekip)

            # ---------------------------------------------------------
            # 3. AMELİYAT (DÖNGÜSEL DAĞITIM)
            # ---------------------------------------------------------
            elif "ameliyat" in task_lower:
                stats["Ameliyat"] += 1
                
                try:
                    masa_sirasi = cols_ameliyat.index(my_task_col)
                except:
                    masa_sirasi = 0
                
                ameliyatci_hocalar = []
                if tarih in df_uzman.index:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        gorev = clean_text_for_comparison(str(u_row[u_col]))
                        if "ameliyat" in gorev and "nöbet" not in gorev:
                            ameliyatci_hocalar.append(u_col)
                
                if len(ameliyatci_hocalar) > 0:
                    atanan_index = masa_sirasi % len(ameliyatci_hocalar)
                    eslesen_hoca = ameliyatci_hocalar[atanan_index]
                    
                    baslik = f"{display_col} - {eslesen_hoca}"
                    aciklama += f"\n📍 Masa: {display_col}\n🔪 Eşleşen Uzman: {eslesen_hoca}"
                    if masa_sirasi >= len(ameliyatci_hocalar):
                        aciklama += "\n(Not: Uzman sayısından fazla masa olduğu için döngüsel atama yapıldı.)"
                else:
                    baslik = f"{display_col}"
                    aciklama += f"\n📍 Masa: {display_col}\n⚠️ Bugün ameliyat listesinde uzman görünmüyor."

            # ---------------------------------------------------------
            # 4. POLİKLİNİK (HATA BURADAYDI - DÜZELTİLDİ)
            # ---------------------------------------------------------
            elif "pol" in task_lower:
                stats["Poliklinik"] += 1
                pol_num = extract_number(display_col)
                eslesen_hoca = None
                
                if tarih in df_uzman.index and pol_num != 999:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        u_gorev = clean_text_for_comparison(str(u_row[u_col]))
                        if "pol" in u_gorev and extract_number(u_gorev) == pol_num:
                            eslesen_hoca = u_col
                            break
                
                if eslesen_hoca:
                    baslik = f"{display_col} - {eslesen_hoca}"
                    aciklama += f"\n🩺 Yer: {display_col}\nSorumlu: {eslesen_hoca}"
                else:
                    baslik = f"{display_col}"

            # ---------------------------------------------------------
            # 5. DİĞER
            # ---------------------------------------------------------
            else:
                stats["Diğer"] += 1
                baslik = f"🚑 {display_col}"
                aciklama += f"\nDurum: {display_col}"

            event.name = baslik
            event.description = aciklama
            cal.events.add(event)

        # --- SONUÇ ---
        if found_count > 0:
            st.success(f"✅ Takvim Hazır! Toplam {found_count} görev işlendi.")
            
            st.markdown("### 📊 Aylık Çalışma Özeti")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Nöbet Sayısı", stats["Nöbet"])
            c2.metric("Nöbet Ertesi", stats["Nöbet Ertesi"])
            c3.metric("Ameliyat", stats["Ameliyat"])
            c4.metric("Poliklinik", stats["Poliklinik"])
            c5.metric("Diğer/Acil", stats["Diğer"])
            
            safe_name = user_name_input.replace(" ", "_")
            st.download_button(
                label="📅 Takvimi İndir (.ics)",
                data=str(cal),
                file_name=f"Nobet_{safe_name}.ics",
                mime="text/calendar"
            )
        else:
            st.warning("⚠️ İsim bulunamadı. Lütfen kontrol edip tekrar deneyin.")
