import streamlit as st
import pandas as pd
import cv2
import numpy as np
import sqlite3
from datetime import datetime
from io import BytesIO
from PIL import Image
import math
import pytz  # Library untuk mengatur zona waktu WIB

# Proteksi impor untuk streamlit-js-eval
try:
    from streamlit_js_eval import get_geolocation, streamlit_js_eval
    JS_EVAL_AVAILABLE = True
except ImportError:
    JS_EVAL_AVAILABLE = False

# Definisi Zona Waktu Asia/Jakarta (WIB)
TZ_WIB = pytz.timezone('Asia/Jakarta')

# Inisialisasi state versi kamera untuk auto-clear jika belum ada
if 'camera_version' not in st.session_state:
    st.session_state['camera_version'] = 0

# ====================================================
# 1. KONFIGURASI UTAMA KANTOR & DATA
# ====================================================
KODE_QR_SAH = "KANTOR_UTAMA_SECRET_KEY_2026"

# Koordinat Kantor Terbaru
KANTOR_LATITUDE = -7.259016          
KANTOR_LONGITUDE = 112.696162
RADIUS_MAKSIMAL_METER = 150

# Data Karyawan Terdaftar Terbaru
KARYAWAN_DATA = {
    "05001908": "Lila Aditya Perdana",
    "05002370": "Hendra",
    "05002934": "Arif Yuliadi",
    "05003750": "Septian Chandra",
    "05003758": "Alfian Nurhuda",
    "05004639": "Budi Setyawan",
    "05004711": "Khoirul Rijal",
    "05005032": "Maxbafasya Aditya Wibowo",
    "05005331": "Dwi Nor Fais",
    "05007005": "Rachmad Dani",
    "05007150": "Lurico Umar Raffsanjani",
    "05007173": "Diska Akbar Hermanto",
    "05007712": "Nur Nuhammad Khoirul Firmansyah",
    "05008111": "Mohammad Holidi"
}

DB_NAME = "absen_master.db"

# ====================================================
# 2. SISTEM DATABASE (SQLITE - DENGAN KOLOM PERANGKAT)
# ====================================================
def inisialisasi_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS absensi (
            tanggal TEXT,
            id_karyawan TEXT,
            nama TEXT,
            waktu_presensi TEXT,
            koordinat_gps TEXT,
            latitude REAL,
            longitude REAL,
            jarak_dari_kantor REAL,
            perangkat TEXT,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_absen_unique 
        ON absensi(tanggal, id_karyawan)
    """)
    conn.commit()
    conn.close()

# Jalankan inisialisasi skema saat aplikasi dimuat
inisialisasi_database()

def muat_data_absen():
    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql_query("""
            SELECT tanggal AS Tanggal, id_karyawan AS ID, nama AS Nama, 
                   waktu_presensi AS [Waktu Presensi], koordinat_gps AS [Koordinat GPS], 
                   latitude AS Latitude, longitude AS Longitude, 
                   jarak_dari_kantor AS [Jarak (meter)], perangkat AS [Perangkat/HP], status AS Status
            FROM absensi
            ORDER BY waktu_presensi DESC
        """, conn)
    except:
        df = pd.DataFrame(columns=[
            "Tanggal", "ID", "Nama", "Waktu Presensi", "Koordinat GPS",
            "Latitude", "Longitude", "Jarak (meter)", "Perangkat/HP", "Status"
        ])
    conn.close()
    return df

def simpan_absen(tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, perangkat, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO absensi 
            (tanggal, id_karyawan, nama, waktu_presensi, koordinat_gps, latitude, longitude, jarak_dari_kantor, perangkat, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, perangkat, status))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# ====================================================
# 3. FUNGSI BANTU (GEOFENCING & QR DETECTOR)
# ====================================================
def hitung_jarak_meter(lat1, lon1, lat2, lon2):
    R = 6371000  # Radius bumi dalam satuan meter
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def proses_gambar_untuk_qr(bytes_data):
    img = Image.open(BytesIO(bytes_data))
    img_np = np.array(img)
    
    if len(img_np.shape) == 3:
        if img_np.shape[2] == 4:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
        else:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    else:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
    
    h, w = img_np.shape[:2]
    if max(h, w) > 1200:
        scale = 1200 / max(h, w)
        img_np = cv2.resize(img_np, None, fx=scale, fy=scale)
    
    versions = [img_np]
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    versions.append(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    versions.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))
    return versions

def scan_qr_code(bytes_data):
    detector = cv2.QRCodeDetector()
    for img in proses_gambar_untuk_qr(bytes_data):
        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data
    return None

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Master Absensi')
    return output.getvalue()

# ====================================================
# 4. ANTARMUKA PENGGUNA (STREAMLIT INTERFACE)
# ====================================================
st.set_page_config(page_title="Absensi QR + GPS", layout="centered")
st.title("🔒 Sistem Absensi QR + GPS")

if not JS_EVAL_AVAILABLE:
    st.error("""
    Library `streamlit-js-eval` belum terinstall.
    Tambahkan baris ini ke file **requirements.txt**:
    ```
    streamlit-js-eval
    ```
    Lalu Commit & Push ulang repositori Anda.
    """)
    st.stop()

with st.expander("📍 Informasi Geofencing Kantor"):
    st.write(f"Koordinat Pusat: `{KANTOR_LATITUDE}, {KANTOR_LONGITUDE}`")
    st.write(f"Batas Radius: `{RADIUS_MAKSIMAL_METER} meter`")

# Dropdown Karyawan
emp_id = st.selectbox(
    "Pilih Profil ID Karyawan",
    list(KARYAWAN_DATA.keys()),
    format_func=lambda x: f"{x} - {KARYAWAN_DATA[x]}"
)

st.write("---")
st.markdown("### 1️⃣ Verifikasi Lokasi GPS & Perangkat")
st.info("Aplikasi memerlukan akses lokasi. Harap pilih **Allow/Izinkan** jika browser memunculkan pop-up permintaan lokasi.")

# FITUR DETEKSI PERANGKAT: Membaca navigator.userAgent dari JavaScript browser
user_device = "Tidak Terdeteksi"
try:
    ua_string = streamlit_js_eval(cmd_id='navigator.userAgent', want_output=True, key='get_user_agent')
    if ua_string:
        if "Android" in ua_string:
            # Mengekstrak model HP android secara sederhana dari string user agent
            parts = ua_string.split('(')
            if len(parts) > 1:
                sub_parts = parts[1].split(')')
                android_info = sub_parts[0]
                # Ambil bagian setelah spesifikasi OS Android untuk deteksi model HP
                model_parts = android_info.split(';')
                if len(model_parts) > 2:
                    user_device = f"Android ({model_parts[2].strip()})"
                else:
                    user_device = "HP Android"
            else:
                user_device = "HP Android"
        elif "iPhone" in ua_string:
            user_device = "Apple iPhone"
        elif "iPad" in ua_string:
            user_device = "Apple iPad"
        elif "Windows" in ua_string:
            user_device = "PC / Laptop (Windows)"
        elif "Macintosh" in ua_string:
            user_device = "PC / Macbook (macOS)"
        elif "Linux" in ua_string:
            user_device = "PC / Laptop (Linux)"
        else:
            user_device = "Perangkat Lain"
except:
    user_device = "Gagal Deteksi Device"

# Mengambil koordinat secara langsung di tingkat skrip (asinkron)
loc = get_geolocation()

if loc and isinstance(loc, dict) and loc.get("coords"):
    st.session_state['user_lat'] = loc["coords"]["latitude"]
    st.session_state['user_lon'] = loc["coords"]["longitude"]
    st.session_state['gps_accuracy'] = loc["coords"].get("accuracy")
else:
    st.warning("⏳ Menunggu koordinat GPS terdeteksi oleh browser... Pastikan GPS HP/Laptop Anda aktif.")
    st.session_state['boleh_scan'] = False

# Evaluasi Jarak apabila Koordinat GPS tersedia
if 'user_lat' in st.session_state and 'user_lon' in st.session_state:
    user_lat = st.session_state['user_lat']
    user_lon = st.session_state['user_lon']
    jarak = hitung_jarak_meter(user_lat, user_lon, KANTOR_LATITUDE, KANTOR_LONGITUDE)
    dalam_radius = jarak <= RADIUS_MAKSIMAL_METER

    st.success("🎯 Lokasi & Perangkat Terverifikasi!")
    st.write(f"**Perangkat Anda:** `{user_device}`")
    st.write(f"**Koordinat Anda:** `{user_lat:.6f}, {user_lon:.6f}`")
    st.write(f"**Jarak ke Kantor:** `{jarak:.1f} meter`")

    if dalam_radius:
        st.success("✅ Lokasi Valid! Anda berada di dalam wilayah radius kantor.")
        st.session_state['boleh_scan'] = True
    else:
        st.error(f"❌ Lokasi Ditolak! Jarak Anda ({jarak:.1f} m) melebihi batas operasional {RADIUS_MAKSIMAL_METER} meter.")
        st.session_state['boleh_scan'] = False

# ====================================================
# 5. PEMINDAIAN QR CODE (HANYA AKTIF JIKA LOKASI VALID)
# ====================================================
if st.session_state.get('boleh_scan', False):
    st.write("---")
    st.markdown("### 2️⃣ Pindai QR Code Kantor")
    
# Kunci ID dinamis berbasis versi kamera agar gambar otomatis reset setelah sukses absen
camera_key = f"absen_camera_v{st.session_state['camera_version']}"
picture = st.camera_input("Arahkan kamera ke QR Code Resmi Kantor", key=camera_key)
if picture is not None:
bytes_data = picture.getvalue()
with st.spinner("Memproses pemindaian QR..."):
data_qr = scan_qr_code(bytes_data)
if data_qr == KODE_QR_SAH:
waktu_sekarang = datetime.now(TZ_WIB)
hari_ini = waktu_sekarang.strftime("%Y-%m-%d")
waktu_str = waktu_sekarang.strftime("%Y-%m-%d %H:%M:%S")
koordinat_str = f"{user_lat:.6f},{user_lon:.6f}"
status_teks = "Hadir Tepat Radius"
nama_karyawan = KARYAWAN_DATA[emp_id]
# Eksekusi penyimpanan ke SQLite Database (Menyertakan variabel user_device)
berhasil = simpan_absen(
hari_ini, emp_id, nama_karyawan, waktu_str,
koordinat_str, user_lat, user_lon, jarak, user_device, status_teks
)
if berhasil:
st.balloons()
st.success(f"🎉 Absensi BERHASIL dicatat untuk {nama_karyawan} pada {waktu_str} WIB!")
# Ubah versi kamera agar widget kamera otomatis ter-clear kosong kembali
st.session_state['camera_version'] += 1
st.rerun()
else:
st.warning(f"⚠️ {nama_karyawan} sudah melakukan absensi hari ini ({hari_ini}). Data duplikat ditolak oleh sistem.")
else:
st.error("❌ QR Code tidak valid atau tidak terdeteksi! Pastikan kode tegak lurus dan pencahayaan cukup.")

====================================================


6. PANEL ADMIN (RIWAYAT, DOWNLOAD & PROTECTED RESET)


====================================================

st.write("---")
st.markdown("### 📊 Panel Monitoring Absensi (Real-time)")
df_absen = muat_data_absen()

Tampilkan tabel absensi jika ada data

if not df_absen.empty:
st.dataframe(df_absen, use_container_width=True)
else:
st.info("Belum ada riwayat data presensi karyawan yang tercatat di database.")
st.write("")

Tombol dipasang di luar "if" agar SELALU MUNCUL setiap saat

col1, col2 = st.columns(2)
with col1:
waktu_unduh = datetime.now(TZ_WIB).strftime("%Y%m%d_%H%M%S")
data_excel = to_excel(df_absen)
st.download_button(
label="📥 Unduh Seluruh Riwayat Absensi (Excel)",
data=data_excel,
file_name=f"log_absensi_{waktu_unduh}_WIB.xlsx",
mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
use_container_width=True
)
with col2:
if st.button("🗑️ Reset Semua Log Absensi", type="primary", use_container_width=True):
st.session_state['konfirmasi_reset'] = True

Alur Input Password Admin (Hanya muncul jika tombol reset diklik)

if st.session_state.get('konfirmasi_reset', False):
st.write("")
st.warning("⚠️ PERINGATAN: Tindakan ini akan menghapus seluruh data riwayat absensi secara permanen.")
input_pass = st.text_input("Masukkan Password Admin:", type="password", key="pass_reset_admin")
c1, c2 = st.columns(2)
with c1:
if st.button("❌ Batalkan", use_container_width=True, key="btn_batal_reset"):
st.session_state['konfirmasi_reset'] = False
st.rerun()
with c2:
if st.button("🔥 Konfirmasi Hapus Total", type="primary", use_container_width=True, key="btn_eksekusi_reset"):
if input_pass == "admin123":
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()
cursor.execute("DELETE FROM absensi")
conn.commit()
conn.close()
st.session_state['konfirmasi_reset'] = False
st.success("🗑️ Seluruh riwayat log absensi berhasil dibersihkan secara permanen!")
st.rerun()
else:
st.error("❌ Password Admin salah! Data gagal dihapus.")
