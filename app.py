import streamlit as st
import pandas as pd
from ics import Calendar, Event
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Asistan Takvimi (Manuel)", page_icon="📝", layout="wide")

st.title("📝 Ortopedi Asistan Takvimi (Manuel Giriş)")
st.markdown("""
**Nasıl Kullanılır?**
1. Asistan ve Uzman listelerini yükle.
2. Adını ve Soyadını listede yazdığı gibi kutuya yaz.
3. Takvimini oluştur.
""")

# --- YARDIMCI FONKSİYONLAR ---

def clean_text_for_comparison(text):
    """Karşılaştırma için metni normalize eder (boşlukları siler, küçültür)"""
    if pd.isna(text): return ""
    text = str(text).lower()
    # Excel'den gelen görünmez boşlukları sil
    text = text.replace('\xa0', ' ').replace('\t', ' ').strip()
    # Türkçe karakter dönüşümü
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
    return nums[0] if nums else None

def deduplicate_columns(df):
    """HATAYI ÇÖZEN KISIM: Aynı isimli sütunları (NÖBET, NÖBET) -> (NÖBET, NÖBET_1) yapar"""
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols[cols == dup].index.values.tolist()] = [dup + '_' + str(i) if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    return df

def load_and_fix_df(file):
    """Dosyayı okur, kodlamayı çözer, başlığı bulur ve sütunları temizler"""
    encodings = ['utf-8', 'iso-8859-9', 'windows-1254']
    df = None
    
    # 1. Dosyayı Oku
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
            
    if df is None:
        return pd.DataFrame()

    # 2. Başlık Satırını Bul
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
    
    # 3. Aynı isimli sütunları düzelt (Duplicate Columns Fix)
    df = deduplicate_columns(df)
    
    # 4. Tarih sütununu ayarla
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

# Manuel İsim Girişi
user_name_input = st.text_input("Adın Soyadın:", placeholder="Örn: Tahir Sekizkardeş").strip()

# --- ANA MOTOR ---

if st.button("Takvimi Oluştur 🚀") and asistan_file and uzman_file and user_name_input:
    # Dosyaları Yükle
    df_asist = load_and_fix_df(asistan_file)
    df_uzman = load_and_fix_df(uzman_file)
    
    if df_asist.empty:
        st.error("Asistan dosyası okunamadı.")
    else:
        cal = Calendar()
        stats = {"Nöbet": 0, "Nöbet Ertesi": 0, "Ameliyat": 0, "Poliklinik": 0, "Diğer": 0}
        
        # Sütun gruplarını belirle (Temizlenmiş isimlerle)
        cols_nobet = [c for c in df_asist.columns if "nöbet" in clean_text_for_comparison(c) and "ertesi" not in clean_text_for_comparison(c)]
        cols_ameliyat = [c for c in df_asist.columns if "ameliyat" in clean_text_for_comparison(c) and "nöbet" not in clean_text_for_comparison(c)]
        
        found_count = 0
        
        for tarih, row in df_asist.iterrows():
            my_task_col = None
            
            # Girilen ismi satırda ara
            for col in df_asist.columns:
                cell_val = clean_text_for_comparison(row[col])
                target_name = clean_text_for_comparison(user_name_input)
                
                # İsim eşleşmesi (En az 3 harfli olmalı ki 'Ali' gibi kısa isimler karışmasın)
                if len(target_name) > 2 and target_name in cell_val:
                    my_task_col = col
                    break
            
            if not my_task_col:
                continue

            found_count += 1
            event = Event()
            event.begin = tarih
            event.make_all_day()
            
            # Görüntüleme için _1, _2 eklerini temizle
            display_task_col = my_task_col.rsplit('_', 1)[0] if '_' in my_task_col else my_task_col
            task_lower = clean_text_for_comparison(display_task_col)
            
            baslik = ""
            aciklama = f"📅 Tarih: {tarih.strftime('%d.%m.%Y')}\n"

            # --- MANTIK BLOKLARI ---
            
            # 1. Nöbet Ertesi
            if "ertesi" in task_lower:
                stats["Nöbet Ertesi"] += 1
                baslik = "🛌 NÖBET ERTESİ (İZİN)"
                aciklama += "\nDurum: ÇALIŞMIYOR / İZİNLİ"

            # 2. Nöbet
            elif "nöbet" in task_lower or "icap" in task_lower:
                stats["Nöbet"] += 1
                baslik = f"🚨 NÖBET ({display_task_col})"
                ekip = []
                # Nöbet ekibini topla
                for nc in cols_nobet:
                    val = clean_text_display(row[nc])
                    if len(val) > 2 and "nan" not in val.lower():
                        clean_nc = nc.rsplit('_', 1)[0] if '_' in nc else nc
                        ekip.append(f"- {val} ({clean_nc})")
                
                # Nöbetçi Uzmanı Bul
                uzman_nobetci = "Belirtilmemiş"
                if tarih in df_uzman.index:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        if "nöbet" in clean_text_for_comparison(str(u_row[u_col])):
                            uzman_nobetci = u_col
                            break
                aciklama += f"\n💀 NÖBET EKİBİ:\n" + "\n".join(ekip) + f"\n\n👨‍⚕️ Nöbetçi Uzman: {uzman_nobetci}"

            # 3. Ameliyat
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
                
                if masa_sirasi < len(ameliyatci_hocalar):
                    eslesen_hoca = ameliyatci_hocalar[masa_sirasi]
                    baslik = f"{display_task_col} - {eslesen_hoca}"
                    aciklama += f"\n📍 Yer: {display_task_col}\n🔪 Uzman: {eslesen_hoca}"
                else:
                    baslik = f"{display_task_col}"
                    aciklama += f"\n📍 Yer: {display_task_col}\n(Uzman listesinde bu sıra için hoca bulunamadı)"

            # 4. Poliklinik
            elif "pol" in task_lower:
                stats["Poliklinik"] += 1
                pol_num = extract_number(display_task_col)
                eslesen_hoca = None
                if tarih in df_uzman.index and pol_num:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        u_gorev = clean_text_for_comparison(str(u_row[u_col]))
                        if "pol" in u_gorev and pol_num == extract_number(u_gorev):
                            eslesen_hoca = u_col
                            break
                if eslesen_hoca:
                    baslik = f"{display_task_col} - {eslesen_hoca}"
                    aciklama += f"\n🩺 Yer: {display_task_col}\nSorumlu: {eslesen_hoca}"
                else:
                    baslik = f"{display_task_col}"

            # 5. Diğer
            else:
                stats["Diğer"] += 1
                baslik = f"🚑 {display_task_col}"
                aciklama += f"\nDurum: {display_task_col}"

            event.name = baslik
            event.description = aciklama
            cal.events.add(event)
        
        # --- SONUÇ VE İNDİRME ---
        if found_count > 0:
            st.success(f"✅ İşlem Tamam! {found_count} adet görev bulundu.")
            
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Nöbet", stats["Nöbet"])
            c2.metric("İzin (Ertesi)", stats["Nöbet Ertesi"])
            c3.metric("Ameliyat", stats["Ameliyat"])
            c4.metric("Poliklinik", stats["Poliklinik"])
            c5.metric("Diğer", stats["Diğer"])
            
            safe_name = user_name_input.replace(" ", "_")
            st.download_button(
                label="📅 Takvimini İndir (.ics)",
                data=str(cal),
                file_name=f"Takvim_{safe_name}.ics",
                mime="text/calendar"
            )
        else:
            st.warning("⚠️ Girdiğin isimle eşleşen bir görev bulunamadı.")
            st.info("İpucu: İsminin listede tam olarak nasıl yazıldığını kontrol et (Örn: 'Tahir' yerine 'Mehmet Tahir' olabilir).")
