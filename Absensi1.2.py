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
    from streamlit_js_eval import get_geolocation
    JS_EVAL_AVAILABLE = True
except ImportError:
    JS_EVAL_AVAILABLE = False

# Definisi Zona Waktu Asia/Jakarta (WIB)
TZ_WIB = pytz.timezone('Asia/Jakarta')

# Inisialisasi session state untuk auto-clear kamera jika belum ada
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
# 2. SISTEM DATABASE (SQLITE)
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
                   jarak_dari_kantor AS [Jarak (meter)], status AS Status
            FROM absensi
            ORDER BY waktu_presensi DESC
        """, conn)
    except:
        df = pd.DataFrame(columns=[
            "Tanggal", "ID", "Nama", "Waktu Presensi", "Koordinat GPS",
            "Latitude", "Longitude", "Jarak (meter)", "Status"
        ])
    conn.close()
    return df

def simpan_absen(tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO absensi 
            (tanggal, id_karyawan, nama, waktu_presensi, koordinat_gps, latitude, longitude, jarak_dari_kantor, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, status))
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
        if img_np.shape == 4:
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
st.markdown("### 1️⃣ Verifikasi Lokasi GPS")
st.info("Aplikasi memerlukan akses lokasi. Harap pilih **Allow/Izinkan** jika browser memunculkan pop-up permintaan lokasi.")

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
    user_lon = st.session_state['user_lon8'] if 'user_lon8' in st.session_state else st.session_state['user_lon']
    # fallback jika ketik typo variabel
    user_lon = st.session_state['user_lon']
    jarak = hitung_jarak_meter(user_lat, user_lon, KANTOR_LATITUDE, KANTOR_LONGITUDE)
    dalam_radius = jarak <= RADIUS_MAKSIMAL_METER

    st.success("🎯 Lokasi GPS terdeteksi!")
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
    
    # PERBAIKAN UTAMA: Menyisipkan key dinamis agar kamera otomatis ter-clear pasca sukses absen
    camera_key = f"absen_cam_{st.session_state['camera_version']}"
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

            # Eksekusi penyimpanan ke SQLite Database
            berhasil = simpan_absen(
                hari_ini, emp_id, nama_karyawan, waktu_str, 
                koordinat_str, user_lat, user_lon, jarak, status_teks
            )

            if berhasil:
                st.balloons()
                st.success(f"🎉 Absensi BERHASIL dicatat untuk **{nama_karyawan}** pada {waktu_str} WIB!")
                
                # PERBAIKAN UTAMA: Naikkan versi kamera agar foto di layar otomatis terhapus
                st.session_state['camera_version'] += 1
                st.button("Klik Disini Untuk Melanjutkan / Selesai", on_click=st.rerun)
            else:
