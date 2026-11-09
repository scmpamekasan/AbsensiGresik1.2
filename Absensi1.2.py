import streamlit as st
import pandas as pd
import cv2
import numpy as np
import sqlite3
from datetime import datetime
from io import BytesIO
from PIL import Image
import math
from streamlit_js_eval import get_geolocation

# ====================================================
# CONFIGURASI
# ====================================================
KODE_QR_SAH = "KANTOR_UTAMA_SECRET_KEY_2026"

# --- GEOFENCING ---
KANTOR_LATITUDE = -7.259138          # Ganti dengan latitude kantor
KANTOR_LONGITUDE = 112.696182        # Ganti dengan longitude kantor
RADIUS_MAKSIMAL_METER = 150          # Radius maksimal (meter)

KARYAWAN_DATA = {
    "EMP001": "Eka Sulawestara",
    "EMP002": "Diny Herlita",
    "EMP003": "Eureka Annisa Naira",
    "EMP004": "Eustacia Redinka Amayra"
}

DB_NAME = "absen_master.db"

# ====================================================
# DATABASE
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

inisialisasi_database()

def muat_data_absen():
    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql_query("""
            SELECT 
                tanggal AS Tanggal, 
                id_karyawan AS ID, 
                nama AS Nama, 
                waktu_presensi AS [Waktu Presensi], 
                koordinat_gps AS [Koordinat GPS], 
                latitude AS Latitude, 
                longitude AS Longitude, 
                jarak_dari_kantor AS [Jarak (meter)],
                status AS Status
            FROM absensi
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
# FUNGSI BANTU
# ====================================================
def hitung_jarak_meter(lat1, lon1, lat2, lon2):
    R = 6371000
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
# INTERFACE
# ====================================================
st.set_page_config(page_title="Absensi QR + GPS Browser", layout="centered")
st.title("🔒 Sistem Absensi QR + GPS Akurat")
st.caption("Menggunakan lokasi GPS langsung dari HP (lebih andal)")

# Info Geofencing
with st.expander("📍 Informasi Geofencing", expanded=False):
    st.write(f"**Koordinat Kantor:** `{KANTOR_LATITUDE}, {KANTOR_LONGITUDE}`")
    st.write(f"**Radius Maksimal:** `{RADIUS_MAKSIMAL_METER} meter`")

emp_id = st.selectbox(
    "Pilih Profil ID Karyawan",
    list(KARYAWAN_DATA.keys()),
    format_func=lambda x: f"{x} - {KARYAWAN_DATA[x]}"
)

st.write("---")
st.markdown("### 1️⃣ Ambil Lokasi GPS Anda")

# Tombol ambil lokasi
if st.button("📍 Ambil Lokasi GPS Saya", use_container_width=True, type="primary"):
    loc = get_geolocation()
    
    if loc and loc.get("coords"):
        st.session_state['user_lat'] = loc["coords"]["latitude"]
        st.session_state['user_lon'] = loc["coords"]["longitude"]
        st.session_state['gps_accuracy'] = loc["coords"].get("accuracy", None)
        st.success("Lokasi berhasil diambil!")
        st.rerun()
    else:
        st.error("Gagal mengambil lokasi. Pastikan Anda mengizinkan akses lokasi di browser.")

# Tampilkan hasil GPS jika sudah ada
if 'user_lat' in st.session_state and 'user_lon' in st.session_state:
    user_lat = st.session_state['user_lat']
    user_lon = st.session_state['user_lon']
    jarak = hitung_jarak_meter(user_lat, user_lon, KANTOR_LATITUDE, KANTOR_LONGITUDE)
    dalam_radius = jarak <= RADIUS_MAKSIMAL_METER
    
    st.write(f"**Koordinat Anda:** `{user_lat:.6f}, {user_lon:.6f}`")
    st.write(f"**Jarak dari Kantor:** `{jarak:.1f} meter`")
    
    if dalam_radius:
        st.success(f"✅ Anda berada dalam radius kantor ({jarak:.1f} m)")
        st.session_state['boleh_scan'] = True
    else:
        st.error(f"❌ Anda berada di luar radius kantor ({jarak:.1f} m). Maksimal {RADIUS_MAKSIMAL_METER} meter.")
        st.session_state['boleh_scan'] = False
else:
    st.info("Silakan tekan tombol di atas untuk mengambil lokasi GPS Anda terlebih dahulu.")
    st.session_state['boleh_scan'] = False

# ====================================================
# BAGIAN SCAN QR (hanya muncul jika dalam radius)
# ====================================================
if st.session_state.get('boleh_scan', False):
    st.write("---")
    st.markdown("### 2️⃣ Scan QR Code Kantor")
    
    picture = st.camera_input("Ambil foto QR Code sekarang")
    
    if picture is not None:
        bytes_data = picture.getvalue()
        st.image(bytes_data, caption="Pratinjau Foto QR", width=280)
        
        with st.spinner("Sedang memindai QR Code..."):
            data_qr = scan_qr_code(bytes_data)
        
        if data_qr:
            if data_qr == KODE_QR_SAH:
                waktu_sekarang = datetime.now()
                hari_ini = waktu_sekarang.strftime("%Y-%m-%d")
                waktu_str = waktu_sekarang.strftime("%Y-%m-%d %H:%M:%S")
                
                koordinat_str = f"{user_lat:.6f},{user_lon:.6f}"
                status = f"Hadir Sah (GPS Browser - {jarak:.0f} m)"
                
                berhasil = simpan_absen(
                    hari_ini, emp_id, KARYAWAN_DATA[emp_id],
                    waktu_str, koordinat_str, user_lat, user_lon,
                    round(jarak, 1), status
                )
                
                if berhasil:
                    st.success(f"🎉 ABSENSI BERHASIL!\n\nSelamat bekerja, **{KARYAWAN_DATA[emp_id]}**")
                    st.write(f"**Status:** {status}")
                    st.info(f"📍 Koordinat: `{koordinat_str}`")
                else:
                    st.warning(f"⚠️ {KARYAWAN_DATA[emp_id]} sudah tercatat hadir hari ini.")
            else:
                st.error("❌ QR Code tidak valid.")
        else:
            st.error("📷 QR Code tidak terdeteksi. Coba lagi dengan posisi lebih dekat dan stabil.")

# ====================================================
# RIWAYAT
# ====================================================
st.write("---")
st.subheader("📊 Master Riwayat Absensi")

df_master = muat_data_absen()

if not df_master.empty:
    st.dataframe(df_master.sort_values(by="Waktu Presensi", ascending=False), use_container_width=True)
    
    df_peta = df_master.dropna(subset=['Latitude', 'Longitude'])
    if not df_peta.empty:
        st.write("### 🗺️ Peta Lokasi")
        st.map(df_peta[['Latitude', 'Longitude']].rename(columns={'Latitude': 'lat', 'Longitude': 'lon'}), zoom=14)
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "🟢 Unduh Excel",
            data=to_excel(df_master),
            file_name=f"rekap_absen_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "🔵 Unduh CSV",
            data=df_master.to_csv(index=False).encode('utf-8'),
            file_name=f"rekap_absen_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
else:
    st.info("Belum ada data absensi.")
