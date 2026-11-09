import streamlit as st
import pandas as pd
import cv2
import numpy as np
import sqlite3
import piexif
from datetime import datetime
from io import BytesIO
from PIL import Image
import math

# ====================================================
# CONFIGURASI UTAMA
# ====================================================
KODE_QR_SAH = "KANTOR_UTAMA_SECRET_KEY_2026"

# --- PENGATURAN GEOFENCING ---
# Ganti dengan koordinat kantor Anda yang sebenarnya
KANTOR_LATITUDE = -7.259138          # Contoh: Kantor DSO
KANTOR_LONGITUDE = 112.696182
RADIUS_MAKSIMAL_METER = 150          # Radius yang diizinkan (meter)

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
def inisialisasi_database_sqlite():
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
            status TEXT,
            sumber_foto TEXT
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_absen_unique 
        ON absensi(tanggal, id_karyawan)
    """)
    conn.commit()
    conn.close()

inisialisasi_database_sqlite()

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
                status AS Status, 
                sumber_foto AS [Sumber Foto]
            FROM absensi
        """, conn)
        df['Koordinat GPS'] = df['Koordinat GPS'].astype(str)
    except:
        df = pd.DataFrame(columns=[
            "Tanggal", "ID", "Nama", "Waktu Presensi", "Koordinat GPS",
            "Latitude", "Longitude", "Jarak (meter)", "Status", "Sumber Foto"
        ])
    conn.close()
    return df

def simpan_absen_baru(tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, status, sumber_foto):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO absensi 
            (tanggal, id_karyawan, nama, waktu_presensi, koordinat_gps, latitude, longitude, jarak_dari_kantor, status, sumber_foto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, status, sumber_foto))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# ====================================================
# FUNGSI GEOFENCING (Haversine)
# ====================================================
def hitung_jarak_meter(lat1, lon1, lat2, lon2):
    """Menghitung jarak antara dua koordinat dalam meter (Haversine Formula)"""
    R = 6371000  # Radius bumi dalam meter
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

# ====================================================
# FUNGSI GPS
# ====================================================
def konversi_ke_derajat_desimal(nilai, referensi):
    try:
        derajat = float(nilai[0][0]) / float(nilai[0][1])
        menit   = float(nilai[1][0]) / float(nilai[1][1])
        detik   = float(nilai[2][0]) / float(nilai[2][1])
        desimal = derajat + (menit / 60.0) + (detik / 3600.0)
        if referensi in ['S', 'W']:
            desimal = -desimal
        return desimal
    except:
        return None

def ekstrak_gps_dari_foto(bytes_gambar):
    try:
        exif_dict = piexif.load(bytes_gambar)
        gps_data = exif_dict.get("GPS")
        
        if not gps_data:
            return None, None, "GPS Tidak Aktif / Tidak Tersedia"
        
        lat_val = gps_data.get(piexif.GPSIFD.GPSLatitude)
        lat_ref = gps_data.get(piexif.GPSIFD.GPSLatitudeRef)
        lon_val = gps_data.get(piexif.GPSIFD.GPSLongitude)
        lon_ref = gps_data.get(piexif.GPSIFD.GPSLongitudeRef)
        
        if lat_val and lon_val and lat_ref and lon_ref:
            lat_ref = lat_ref.decode('utf-8') if isinstance(lat_ref, bytes) else lat_ref
            lon_ref = lon_ref.decode('utf-8') if isinstance(lon_ref, bytes) else lon_ref
            
            lat = konversi_ke_derajat_desimal(lat_val, lat_ref)
            lon = konversi_ke_derajat_desimal(lon_val, lon_ref)
            
            if lat is not None and lon is not None:
                return lat, lon, f"{lat:.6f},{lon:.6f}"
        
        return None, None, "GPS Tidak Lengkap"
    except Exception:
        return None, None, "Gagal Membaca EXIF GPS"

# ====================================================
# FUNGSI DETEKSI KAMERA & QR
# ====================================================
def deteksi_sumber_foto(nama_file: str) -> str:
    nama = nama_file.lower()
    kamera_keywords = ["camera", "captured", "image", "photo", "img_", "cam_"]
    if any(k in nama for k in kamera_keywords) or nama.startswith("camera"):
        return "Kamera Langsung"
    return "Dari Galeri / File"

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
    
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 11, 2)
    versions.append(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))
    
    return versions

def scan_qr_code(bytes_data):
    detector = cv2.QRCodeDetector()
    versions = proses_gambar_untuk_qr(bytes_data)
    
    for img in versions:
        data, bbox, _ = detector.detectAndDecode(img)
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
st.set_page_config(page_title="Absensi QR + GPS + Geofencing", layout="centered")
st.title("🔒 Sistem Absensi QR Code + Geofencing")
st.caption("Scan QR • Deteksi Kamera • GPS • Geofencing Radius Kantor")

# Tampilkan info geofencing
with st.expander("📍 Informasi Geofencing Kantor", expanded=False):
    st.write(f"**Koordinat Kantor:** `{KANTOR_LATITUDE}, {KANTOR_LONGITUDE}`")
    st.write(f"**Radius Maksimal:** `{RADIUS_MAKSIMAL_METER} meter`")
    st.caption("Absensi hanya dianggap sah jika Anda berada dalam radius di atas.")

emp_id = st.selectbox(
    "Pilih Profil ID Karyawan",
    list(KARYAWAN_DATA.keys()),
    format_func=lambda x: f"{x} - {KARYAWAN_DATA[x]}"
)

st.write("---")
st.markdown("### 📸 Ambil Foto QR Code Kantor")

st.info("""
**Syarat Absensi Sah:**
1. Menggunakan **Kamera Langsung** (bukan dari Galeri)
2. QR Code resmi kantor terdeteksi
3. GPS HP aktif
4. Berada dalam radius **{} meter** dari kantor
""".format(RADIUS_MAKSIMAL_METER))

picture = st.camera_input("Ambil foto QR Code sekarang")

if picture is not None:
    bytes_data = picture.getvalue()
    nama_file = getattr(picture, "name", "camera_input.jpg")
    
    # 1. Deteksi sumber foto
    sumber_foto = deteksi_sumber_foto(nama_file)
    
    # 2. Ekstrak GPS
    user_lat, user_lon, koordinat_str = ekstrak_gps_dari_foto(bytes_data)
    
    # 3. Hitung jarak geofencing
    jarak = None
    dalam_radius = False
    if user_lat is not None and user_lon is not None:
        jarak = hitung_jarak_meter(user_lat, user_lon, KANTOR_LATITUDE, KANTOR_LONGITUDE)
        dalam_radius = jarak <= RADIUS_MAKSIMAL_METER
    
    # 4. Preview
    st.image(bytes_data, caption=f"Pratinjau ({sumber_foto})", width=280)
    
    # 5. Scan QR
    with st.spinner("Sedang memindai QR Code & memvalidasi lokasi..."):
        data_qr = scan_qr_code(bytes_data)
    
    if data_qr:
        if data_qr == KODE_QR_SAH:
            waktu_sekarang = datetime.now()
            hari_ini = waktu_sekarang.strftime("%Y-%m-%d")
            waktu_str = waktu_sekarang.strftime("%Y-%m-%d %H:%M:%S")
            
            # ===== LOGIKA STATUS + GEOFENCING =====
            if sumber_foto != "Kamera Langsung":
                status = "Ditolak - Foto dari Galeri"
                boleh_simpan = False
            elif user_lat is None:
                status = "Ditolak - GPS Tidak Tersedia"
                boleh_simpan = False
            elif not dalam_radius:
                status = f"Ditolak - Di Luar Area Kantor ({jarak:.0f} m)"
                boleh_simpan = False
            else:
                status = f"Hadir Sah (Dalam Radius {jarak:.0f} m)"
                boleh_simpan = True
            
            # Simpan hanya jika memenuhi syarat
            if boleh_simpan:
                berhasil = simpan_absen_baru(
                    hari_ini, emp_id, KARYAWAN_DATA[emp_id],
                    waktu_str, koordinat_str, user_lat, user_lon,
                    round(jarak, 1), status, sumber_foto
                )
                
                if berhasil:
                    st.success(f"🎉 ABSENSI BERHASIL!\n\nSelamat bekerja, **{KARYAWAN_DATA[emp_id]}**")
                    st.write(f"**Status:** {status}")
                    st.write(f"**Jarak dari Kantor:** {jarak:.1f} meter")
                    st.info(f"📍 Koordinat: `{koordinat_str}`")
                else:
                    st.warning(f"⚠️ {KARYAWAN_DATA[emp_id]} sudah tercatat hadir hari ini.")
            else:
                # Tetap bisa dicatat sebagai percobaan gagal (opsional)
                st.error(f"❌ ABSENSI DITOLAK\n\n**Alasan:** {status}")
                
                if jarak is not None:
                    st.write(f"Jarak Anda saat ini: **{jarak:.1f} meter** dari kantor")
                    st.write(f"Batas maksimal: **{RADIUS_MAKSIMAL_METER} meter**")
                
                # Opsional: tetap simpan data penolakan untuk audit
                # simpan_absen_baru(..., status, ...) 
        else:
            st.error("❌ QR Code tidak valid. Ini bukan QR Code resmi kantor.")
    else:
        st.error("📷 QR Code tidak terdeteksi.\n\nTips: Dekatkan kamera, pastikan QR tidak buram, dan pencahayaan cukup.")

# ====================================================
# PANEL RIWAYAT
# ====================================================
st.write("---")
st.subheader("📊 Master Riwayat Absensi")

df_master = muat_data_absen()

if not df_master.empty:
    st.dataframe(
        df_master.sort_values(by="Waktu Presensi", ascending=False),
        use_container_width=True
    )
    
    # Peta
    df_peta = df_master.dropna(subset=['Latitude', 'Longitude'])
    if not df_peta.empty:
        st.write("### 🗺️ Peta Lokasi Scan Karyawan")
        st.map(
            df_peta[['Latitude', 'Longitude']].rename(columns={'Latitude': 'lat', 'Longitude': 'lon'}),
            zoom=14
        )
    
    # Download
    st.write("### 📥 Unduh Data")
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
