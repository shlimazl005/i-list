import streamlit as st
import pandas as pd
from ics import Calendar, Event
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Pro Takvim (Hatasız)", page_icon="🎯", layout="wide")

st.title("🎯 Ortopedi Asistan Takvimi (Otomatik İsim Seçmeli)")
st.markdown("""
**Sorun Çözüldü:** Artık ismini elle yazmana gerek yok.
1. Listeleri yükle.
2. Aşağıda açılan kutudan **ismini seç**.
3. Takvimini indir.
""")

# --- YARDIMCI FONKSİYONLAR ---

def clean_text_for_comparison(text):
    """Karşılaştırma için metni normalize eder (boşlukları siler, küçültür)"""
    if pd.isna(text): return ""
    text = str(text).lower()
    # Excel'den gelen görünmez boşlukları (non-breaking space) sil
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

def load_and_fix_df(file):
    """Dosyayı okur, kodlamayı çözer ve başlığı bulur"""
    # 1. Farklı kodlamalarla okumayı dene
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
            
    if df is None:
        st.error("Dosya okunamadı. Lütfen geçerli bir CSV veya Excel dosyası yükleyin.")
        return pd.DataFrame()

    # 2. Başlık satırını akıllıca bul
    header_idx = -1
    for i, row in df.iterrows():
        row_text = " ".join([str(x) for x in row.values]).lower()
        # Satırda hem tarih (veya gün) hem de nöbet/pol gibi anahtar kelimeler varsa başlıktır
        if ('pazartesi' in row_text or 'tarih' in row_text) and ('nöbet' in row_text or 'pol' in row_text):
            header_idx = i
            break
    
    if header_idx != -1:
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx+1:].reset_index(drop=True)
    else:
        # Başlık bulunamazsa 0. satırı başlık varsay
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
    
    # 3. Tarih sütununu ayarla
    # Genelde ilk sütun tarihtir, datetime'a çevir
    try:
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], dayfirst=True, errors='coerce')
        df = df.dropna(subset=[df.columns[0]]) # Tarihi olmayanları at
        df = df.set_index(df.columns[0])
    except:
        pass
        
    return df

def get_unique_names(df):
    """Dataframe içindeki tüm olası asistan isimlerini bulur"""
    names = set()
    keywords_to_exclude = ['nöbet', 'servis', 'pol', 'ameliyat', 'icap', 'tarih', 'gün', 'nan', 'bolumu', 'toplam']
    
    for col in df.columns:
        unique_vals = df[col].dropna().unique()
        for val in unique_vals:
            val_clean = clean_text_display(val)
            val_lower = clean_text_for_comparison(val)
            
            # İsim mi diye kontrol et (Kısa kelimeleri ve görev isimlerini ele)
            if len(val_clean) > 3 and not any(k in val_lower for k in keywords_to_exclude):
                # Sayı içermiyorsa isimdir muhtemelen
                if not any(char.isdigit() for char in val_clean):
                    names.add(val_clean)
    
    return sorted(list(names))

# --- ARAYÜZ ---
st.sidebar.header("Dosyaları Yükle")
asistan_file = st.sidebar.file_uploader("1. Asistan Listesi", type=["xlsx", "xls", "csv"])
uzman_file = st.sidebar.file_uploader("2. Uzman Listesi", type=["xlsx", "xls", "csv"])

# --- ANA MOTOR ---

if asistan_file and uzman_file:
    # Dosyaları Yükle
    df_asist = load_and_fix_df(asistan_file)
    df_uzman = load_and_fix_df(uzman_file)
    
    if not df_asist.empty:
        # İsim Listesini Çıkar ve Kullanıcıya Seçtir
        olasi_isimler = get_unique_names(df_asist)
        
        st.info("👇 Aşağıdaki listeden ismini seç. (Listeyi dosyadan otomatik çıkardım)")
        selected_name = st.selectbox("Asistan Adı Seç:", ["Seçiniz..."] + olasi_isimler)

        # DEBUG CHECKBOX (Eğer isimler saçma geliyorsa kontrol etsinler)
        with st.expander("Dosya verileri düzgün okunmuş mu? (Kontrol Paneli)"):
            st.write("Asistan Listesi İlk 5 Satır:")
            st.dataframe(df_asist.head())

        if st.button("Takvimi Oluştur 🚀") and selected_name != "Seçiniz...":
            cal = Calendar()
            stats = {"Nöbet": 0, "Nöbet Ertesi": 0, "Ameliyat": 0, "Poliklinik": 0, "Diğer": 0}
            
            cols_nobet = [c for c in df_asist.columns if "nöbet" in clean_text_for_comparison(c) and "ertesi" not in clean_text_for_comparison(c)]
            cols_ameliyat = [c for c in df_asist.columns if "ameliyat" in clean_text_for_comparison(c) and "nöbet" not in clean_text_for_comparison(c)]
            
            found_count = 0
            
            for tarih, row in df_asist.iterrows():
                # Seçilen ismi o satırda ara
                my_task_col = None
                
                for col in df_asist.columns:
                    cell_val = clean_text_for_comparison(row[col])
                    target_name = clean_text_for_comparison(selected_name)
                    
                    if target_name in cell_val and len(target_name) > 2:
                        my_task_col = col
                        break
                
                if not my_task_col:
                    continue

                found_count += 1
                event = Event()
                event.begin = tarih
                event.make_all_day()
                
                task_lower = clean_text_for_comparison(my_task_col)
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
                    baslik = f"🚨 NÖBET ({my_task_col})"
                    ekip = []
                    for nc in cols_nobet:
                        val = clean_text_display(row[nc])
                        if len(val) > 2 and "nan" not in val.lower():
                            ekip.append(f"- {val} ({nc})")
                    
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
                        baslik = f"{my_task_col} - {eslesen_hoca}"
                        aciklama += f"\n📍 Yer: {my_task_col}\n🔪 Uzman: {eslesen_hoca}"
                    else:
                        baslik = f"{my_task_col}"
                        aciklama += f"\n📍 Yer: {my_task_col}"

                # 4. Poliklinik
                elif "pol" in task_lower:
                    stats["Poliklinik"] += 1
                    pol_num = extract_number(my_task_col)
                    eslesen_hoca = None
                    if tarih in df_uzman.index and pol_num:
                        u_row = df_uzman.loc[tarih]
                        for u_col in df_uzman.columns:
                            u_gorev = clean_text_for_comparison(str(u_row[u_col]))
                            if "pol" in u_gorev and pol_num == extract_number(u_gorev):
                                eslesen_hoca = u_col
                                break
                    if eslesen_hoca:
                        baslik = f"{my_task_col} - {eslesen_hoca}"
                        aciklama += f"\n🩺 Yer: {my_task_col}\nSorumlu: {eslesen_hoca}"
                    else:
                        baslik = f"{my_task_col}"

                # 5. Diğer
                else:
                    stats["Diğer"] += 1
                    baslik = f"🚑 {my_task_col}"
                    aciklama += f"\nDurum: {my_task_col}"

                event.name = baslik
                event.description = aciklama
                cal.events.add(event)
            
            # --- SONUÇ ---
            if found_count > 0:
                st.success(f"✅ {found_count} adet görev bulundu ve takvime işlendi!")
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Nöbet", stats["Nöbet"])
                c2.metric("İzin (Ertesi)", stats["Nöbet Ertesi"])
                c3.metric("Ameliyat", stats["Ameliyat"])
                c4.metric("Poliklinik", stats["Poliklinik"])
                c5.metric("Diğer", stats["Diğer"])
                
                safe_name = selected_name.replace(" ", "_")
                st.download_button(
                    label="📅 İndir (.ics)",
                    data=str(cal),
                    file_name=f"Takvim_{safe_name}.ics",
                    mime="text/calendar"
                )
            else:
                st.warning("Seçtiğin isim için takvimde hiçbir görev bulunamadı. (Belki tüm ay izindesindir?)")
                
else:
    st.info("Lütfen sol taraftan dosyaları yükleyerek başlayın.")
