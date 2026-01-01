import streamlit as st
import pandas as pd
from ics import Calendar, Event
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Pro Asistan Takvimi", page_icon="🗓️", layout="wide")

st.title("🗓️ Ortopedi Asistan Takvimi (Final v2)")
st.markdown("""
**Düzeltmeler:**
1. **Ameliyat Sayacı:** Artık "Diğer" sekmesine karışmıyor, doğru sayıyor.
2. **Başlık Algılama:** "Tarih" yazmasa bile Nöbet/Ameliyat satırını bulur.
3. **Karakter Sorunu:** Türkçe karakterler (İ/I) tam düzeltildi.
""")

# --- YARDIMCI FONKSİYONLAR ---

def tr_lower(text):
    """Türkçe karakter uyumlu küçültme"""
    if pd.isna(text): return ""
    text = str(text)
    # Önce manuel değişim
    mapping = {
        'İ': 'i', 'I': 'ı', 'Ş': 'ş', 'Ğ': 'ğ', 'Ü': 'ü', 'Ö': 'ö', 'Ç': 'ç',
        'Â': 'a', 'Î': 'i', 'Û': 'u'
    }
    for source, target in mapping.items():
        text = text.replace(source, target)
    return text.lower().strip()

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

def find_header_and_load(file):
    """Dosyayı okur ve EN DOĞRU başlık satırını bulur"""
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
            
    if df is None: return pd.DataFrame()

    # 2. Akıllı Başlık Tespiti
    # Satırdaki anahtar kelime sayısına bakar. En çok anahtar kelime içeren satır başlıktır.
    keywords = ['nöbet', 'ameliyat', 'pol', 'servis', 'acil', 'icap', 'asistan', 'klinik']
    
    best_header_idx = -1
    max_matches = 0
    
    for i in range(min(20, len(df))): # İlk 20 satıra bakmak yeterli
        row_text = " ".join([str(x) for x in row.values]).lower()
        # Türkçe karakter düzeltmesi yaparak kontrol et
        row_text = tr_lower(row_text)
        
        matches = sum(1 for k in keywords if k in row_text)
        
        if matches > max_matches:
            max_matches = matches
            best_header_idx = i
            
    # Eğer hiç eşleşme bulamazsa (çok garip dosya), 0. satırı al
    if best_header_idx == -1:
        best_header_idx = 0
    
    # DataFrame'i başlığa göre kes
    df.columns = df.iloc[best_header_idx].astype(str)
    df = df.iloc[best_header_idx+1:].reset_index(drop=True)
    
    # Sütun isimlerini temizle ve benzersiz yap
    df = deduplicate_columns(df)
    
    # Tarih sütununu ayarla (Genelde ilk sütundur)
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
    df_asist = find_header_and_load(asistan_file)
    df_uzman = find_header_and_load(uzman_file)
    
    if df_asist.empty:
        st.error("Dosya okunamadı veya boş.")
    else:
        cal = Calendar()
        stats = {"Nöbet": 0, "Nöbet Ertesi": 0, "Ameliyat": 0, "Poliklinik": 0, "Diğer": 0}
        
        # --- SÜTUN ANALİZİ ---
        # Sütunları kategorize et
        cols_nobet_ekibi = []
        raw_cols_ameliyat = []
        
        for c in df_asist.columns:
            cl = tr_lower(c) # Temiz sütun adı
            
            # Nöbet Ekibi (Ertesi hariç)
            if ("nöbet" in cl or "acil" in cl or "icap" in cl) and "ertes" not in cl:
                cols_nobet_ekibi.append(c)
                
            # Ameliyat Sütunları
            if "ameliyat" in cl and "nöbet" not in cl:
                raw_cols_ameliyat.append(c)

        # Ameliyatları numarasına göre sırala (Masa 1, Masa 2...)
        cols_ameliyat = sorted(raw_cols_ameliyat, key=lambda x: extract_number(tr_lower(x)))
        
        found_count = 0
        
        for tarih, row in df_asist.iterrows():
            my_task_col = None
            
            # İsmi Satırda Ara
            for col in df_asist.columns:
                cell_val = tr_lower(row[col])
                target_name = tr_lower(user_name_input)
                
                if len(target_name) > 2 and target_name in cell_val:
                    my_task_col = col
                    break
            
            if not my_task_col: continue

            found_count += 1
            event = Event()
            event.begin = tarih
            event.make_all_day()
            
            # Görüntüleme adı (NÖBET_1 -> NÖBET)
            display_col = my_task_col.rsplit('_', 1)[0] if '_' in my_task_col else my_task_col
            task_lower = tr_lower(display_col)
            
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
                
                # Nöbetçi Uzman Eşleşmesi
                uzman_adi = ""
                if not df_uzman.empty and tarih in df_uzman.index:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        if "nöbet" in tr_lower(str(u_row[u_col])):
                            uzman_adi = u_col
                            break
                
                if uzman_adi:
                    baslik = f"🚨 NÖBET (Uzm: {uzman_adi})"
                    aciklama += f"\n👨‍⚕️ Nöbetçi Uzman: {uzman_adi}"
                else:
                    baslik = f"🚨 NÖBET ({display_col})"

                # Ekip
                ekip = []
                for nc in cols_nobet_ekibi:
                    val = clean_text_display(row[nc])
                    if len(val) > 2 and "nan" not in tr_lower(val):
                        c_cl = nc.rsplit('_', 1)[0] if '_' in nc else nc
                        ekip.append(f"- {val} ({c_cl})")
                if ekip:
                    aciklama += f"\n\n💀 NÖBET EKİBİ:\n" + "\n".join(ekip)

            # ---------------------------------------------------------
            # 3. AMELİYAT
            # ---------------------------------------------------------
            elif "ameliyat" in task_lower:
                stats["Ameliyat"] += 1
                
                try:
                    masa_sirasi = cols_ameliyat.index(my_task_col)
                except:
                    masa_sirasi = 0
                
                ameliyatci_hocalar = []
                if not df_uzman.empty and tarih in df_uzman.index:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        gorev = tr_lower(str(u_row[u_col]))
                        if "ameliyat" in gorev and "nöbet" not in gorev:
                            ameliyatci_hocalar.append(u_col)
                
                if len(ameliyatci_hocalar) > 0:
                    atanan_index = masa_sirasi % len(ameliyatci_hocalar)
                    eslesen_hoca = ameliyatci_hocalar[atanan_index]
                    baslik = f"{display_col} - {eslesen_hoca}"
                    aciklama += f"\n📍 Masa: {display_col}\n🔪 Uzman: {eslesen_hoca}"
                    if masa_sirasi >= len(ameliyatci_hocalar):
                        aciklama += "\n(Not: Döngüsel atama yapıldı)"
                else:
                    baslik = f"{display_col}"
                    aciklama += f"\n📍 Masa: {display_col}\n(Uzman listesinde ameliyatçı görünmüyor)"

            # ---------------------------------------------------------
            # 4. POLİKLİNİK
            # ---------------------------------------------------------
            elif "pol" in task_lower:
                stats["Poliklinik"] += 1
                pol_num = extract_number(display_col)
                eslesen_hoca = None
                
                if not df_uzman.empty and tarih in df_uzman.index and pol_num != 999:
                    u_row = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        u_gorev = tr_lower(str(u_row[u_col]))
                        # Pol ve numara kontrolü
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
            st.success(f"✅ Takvim Hazır! {found_count} görev bulundu.")
            
            st.markdown("### 📊 Aylık İstatistik")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Nöbet", stats["Nöbet"])
            c2.metric("Ertesi (İzin)", stats["Nöbet Ertesi"])
            c3.metric("Ameliyat", stats["Ameliyat"])
            c4.metric("Poliklinik", stats["Poliklinik"])
            c5.metric("Diğer", stats["Diğer"])
            
            safe_name = user_name_input.replace(" ", "_")
            st.download_button(
                label="📅 Takvimi İndir (.ics)",
                data=str(cal),
                file_name=f"Takvim_{safe_name}.ics",
                mime="text/calendar"
            )
        else:
            st.warning("⚠️ İsim bulunamadı. Lütfen kontrol et.")
