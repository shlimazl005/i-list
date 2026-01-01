import streamlit as st
import pandas as pd
from ics import Calendar, Event
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Master Nöbet Takvimi", page_icon="👑", layout="wide")

st.title("👑 Ortopedi Asistan Master Takvimi")
st.markdown("""
**Son Güncelleme:**
✅ **Uzmanlar Takvimde:** Ameliyat, Nöbet ve Acil hocaları başlıkta yazıyor.
✅ **Akıllı Eşleşme:** Masalar hocalara sırayla dağıtılıyor.
✅ **Tam İstatistik:** Ameliyat sayıları doğru.
""")

# --- YARDIMCI FONKSİYONLAR ---

def tr_lower(text):
    """Türkçe karakter uyumlu küçültme"""
    if pd.isna(text): return ""
    text = str(text)
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
    """Metin içindeki sayıyı bulur"""
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

    keywords = ['nöbet', 'ameliyat', 'pol', 'servis', 'acil', 'icap', 'asistan', 'klinik']
    best_header_idx = -1
    max_matches = 0
    
    # İlk 20 satırı tara
    for i in range(min(20, len(df))):
        row = df.iloc[i]
        row_text = " ".join([str(x) for x in row.values]).lower()
        row_text = tr_lower(row_text)
        
        matches = sum(1 for k in keywords if k in row_text)
        if matches > max_matches:
            max_matches = matches
            best_header_idx = i
            
    if best_header_idx == -1: best_header_idx = 0
    
    df.columns = df.iloc[best_header_idx].astype(str)
    df = df.iloc[best_header_idx+1:].reset_index(drop=True)
    df = deduplicate_columns(df)
    
    try:
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], dayfirst=True, errors='coerce')
        df = df.dropna(subset=[df.columns[0]])
        df = df.set_index(df.columns[0])
    except:
        pass
        
    return df

def get_experts_by_keyword(df_uzman, date, keyword, exclude_keyword=None):
    """Belirli bir tarihte, görevi 'keyword' içeren uzmanları bulur."""
    experts = []
    if df_uzman.empty or date not in df_uzman.index:
        return experts
        
    row = df_uzman.loc[date]
    for col_name in df_uzman.columns:
        task = tr_lower(str(row[col_name]))
        
        # Keyword kontrolü (Örn: 'ameliyat' var mı?)
        if keyword in task:
            # Exclude kontrolü (Örn: 'ameliyat' olsun ama 'nöbet' olmasın)
            if exclude_keyword and exclude_keyword in task:
                continue
            experts.append(col_name) # Sütun ismi uzmanın adıdır
            
    return experts

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
        cols_nobet_ekibi = []
        raw_cols_ameliyat = []
        
        for c in df_asist.columns:
            cl = tr_lower(c) 
            # Nöbet Ekibi (Ertesi hariç)
            if ("nöbet" in cl or "acil" in cl or "icap" in cl) and "ertes" not in cl:
                cols_nobet_ekibi.append(c)
            # Ameliyat Sütunları
            if "ameliyat" in cl and "nöbet" not in cl:
                raw_cols_ameliyat.append(c)

        # Ameliyatları sırala (Masa 1, Masa 2...)
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
            # 2. NÖBET (VE ACİL NÖBETİ)
            # ---------------------------------------------------------
            elif "nöbet" in task_lower or "icap" in task_lower or "acil" in task_lower:
                stats["Nöbet"] += 1
                
                # Uzman Bul: Nöbetçi hocayı ara
                nobetci_hocalar = get_experts_by_keyword(df_uzman, tarih, "nöbet")
                
                # Başlık Oluştur
                if nobetci_hocalar:
                    # İlk hocayı al (Genelde tek olur ama liste döner)
                    hoca_str = ", ".join(nobetci_hocalar)
                    baslik = f"🚨 {display_col} (Uzm: {hoca_str})"
                    aciklama += f"\n👨‍⚕️ Nöbetçi Uzman: {hoca_str}"
                else:
                    baslik = f"🚨 {display_col}"
                    aciklama += "\n(Uzman listesinde nöbetçi görünmüyor)"

                # Nöbet Ekibini Ekle
                ekip = []
                for nc in cols_nobet_ekibi:
                    val = clean_text_display(row[nc])
                    if len(val) > 2 and "nan" not in tr_lower(val):
                        c_cl = nc.rsplit('_', 1)[0] if '_' in nc else nc
                        ekip.append(f"- {val} ({c_cl})")
                if ekip:
                    aciklama += f"\n\n💀 NÖBET/ACİL EKİBİ:\n" + "\n".join(ekip)

            # ---------------------------------------------------------
            # 3. AMELİYAT
            # ---------------------------------------------------------
            elif "ameliyat" in task_lower:
                stats["Ameliyat"] += 1
                
                # Benim masam kaçıncı sırada?
                try:
                    masa_sirasi = cols_ameliyat.index(my_task_col)
                except:
                    masa_sirasi = 0
                
                # O günkü Ameliyatçı Hocaları Bul (Nöbet hariç)
                ameliyatci_hocalar = get_experts_by_keyword(df_uzman, tarih, "ameliyat", exclude_keyword="nöbet")
                
                if len(ameliyatci_hocalar) > 0:
                    # Döngüsel Atama (Round-Robin)
                    atanan_index = masa_sirasi % len(ameliyatci_hocalar)
                    eslesen_hoca = ameliyatci_hocalar[atanan_index]
                    
                    baslik = f"{display_col} - {eslesen_hoca}"
                    aciklama += f"\n📍 Masa: {display_col}\n🔪 Uzman: {eslesen_hoca}"
                    
                    if masa_sirasi >= len(ameliyatci_hocalar):
                        aciklama += "\n(Not: Uzman sayısından fazla masa olduğu için döngüsel atama yapıldı.)"
                else:
                    baslik = f"{display_col}"
                    aciklama += f"\n📍 Masa: {display_col}\n(Bugün ameliyat listesinde uzman görünmüyor)"

            # ---------------------------------------------------------
            # 4. POLİKLİNİK
            # ---------------------------------------------------------
            elif "pol" in task_lower:
                stats["Poliklinik"] += 1
                pol_num = extract_number(display_col)
                eslesen_hoca = None
                
                if not df_uzman.empty and tarih in df_uzman.index and pol_num != 999:
                    row_uzman = df_uzman.loc[tarih]
                    for u_col in df_uzman.columns:
                        u_gorev = tr_lower(str(row_uzman[u_col]))
                        # Görevde "pol" var mı ve numarası tutuyor mu?
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
            st.success(f"✅ Takvim Hazır! {found_count} görev işlendi.")
            
            st.markdown("### 📊 Aylık İstatistik")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Nöbet/Acil", stats["Nöbet"])
            c2.metric("Ertesi (İzin)", stats["Nöbet Ertesi"])
            c3.metric("Ameliyat", stats["Ameliyat"])
            c4.metric("Poliklinik", stats["Poliklinik"])
            c5.metric("Diğer", stats["Diğer"])
            
            safe_name = user_name_input.replace(" ", "_")
            st.download_button(
                label="📅 Takvimi İndir (.ics)",
                data=str(cal),
                file_name=f"Master_Takvim_{safe_name}.ics",
                mime="text/calendar"
            )
        else:
            st.warning("⚠️ İsim bulunamadı. Lütfen kontrol et.")
