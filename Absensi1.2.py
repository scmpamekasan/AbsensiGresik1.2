import streamlit as st
import pandas as pd
import cv2
import numpy as np
from datetime import datetime
from io import BytesIO
from PIL import Image
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import streamlit_js_eval

# ====================================================
# CONFIGURASI UTAMA KANTOR
# ====================================================
KANTOR_LAT = -7.310502   # Koordinat Latitude Kantor Anda (Rungkut Surabaya)
KANTOR_LON = 112.798985  # Koordinat Longitude Kantor Anda (Rungkut Surabaya)
RADIUS_MAKSIMAL = 100.0  # Batas radius toleransi maksimal dalam satuan METER

# Teks rahasia yang tertanam di dalam QR Code Statis Kantor Anda
KODE_QR_SAH = "KANTOR_UTAMA_SECRET_KEY_2026" 

KARYAWAN_DATA = {
    "EMP001": "Eka Sulawestara",
    "EMP002": "Diny Herlita",
    "EMP003": "Eureka Annisa Naira",
    "EMP004": "Eustacia Redinka Amayra"
}

# Fungsi menghitung jarak GPS menggunakan Haversine Formula
def hitung_jarak(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000 # Radius bumi dalam satuan meter
    return c * r

if "attendance_db" not in st.session_state:
    st.session_state.attendance_db = []

# ====================================================
# INTERFACE APLIKASI
# ====================================================
st.set_page_config(page_title="Absensi QR + GPS", layout="centered")
st.title("🔒 Sistem Absensi Terkunci GPS & QR Code")
st.caption("Aplikasi ini secara otomatis memvalidasi koordinat GPS Anda pada saat mengunggah foto QR Code kantor.")

# Dropdown Karyawan
emp_id = st.selectbox("Pilih Profil ID Karyawan", list(KARYAWAN_DATA.keys()), format_func=lambda x: f"{x} - {KARYAWAN_DATA[x]}")

st.write("---")

# 1. TRIGGER PENGAMBILAN DATA LOKASI VIA JAVASCRIPT BAWAAN
# Mengaktifkan GPS hardware dengan akurasi tinggi
js_gps_script = "window.navigator.geolocation.getCurrentPosition(function(pos) { return pos.coords.latitude + ',' + pos.coords.longitude; }, function(err) { return 'ERROR:' + err.message; }, { enableHighAccuracy: true });"
loc_string = streamlit_js_eval(data_string=js_gps_script, key="gps_tracker_iphone")

user_lat, user_lon, jarak_ke_kantor = None, None, None

# Indikator Status GPS
if loc_string:
    if "ERROR" not in loc_string:
        try:
            user_lat, user_lon = map(float, loc_string.split(','))
            jarak_ke_kantor = hitung_jarak(user_lat, user_lon, KANTOR_LAT, KANTOR_LON)
            st.success(f"📍 GPS Aktif! Jarak Anda saat ini: **{jarak_ke_kantor:.1f} meter** dari kantor.")
        except:
            st.warning("⚠️ Menyelaraskan koordinat satelit...")
    else:
        st.error("❌ Gagal membaca GPS. Mohon izinkan akses lokasi (Location Services) pada browser iPhone Anda.")
else:
    st.warning("⏳ Menunggu browser mengunci lokasi GPS Anda. Jika muncul permintaan izin lokasi, klik 'Allow/Izinkan'.")

st.write("---")
st.markdown("### 📸 Pindai QR Code Kantor")

# Menggunakan file uploader bawaan browser untuk memicu kamera native iPhone secara langsung
picture = st.file_uploader("Ketuk di sini untuk membuka Kamera iPhone & Foto QR", type=["png", "jpg", "jpeg"])

if picture is not None:
    # PROTEKSI 1: Cek apakah data lokasi GPS sudah masuk atau belum
    if user_lat is None or user_lon is None:
        st.error("❌ Absen Ditolak! Lokasi GPS Anda belum terdeteksi. Mohon segarkan halaman browser dan pastikan GPS aktif.")
    
    # PROTEKSI 2: Cek apakah koordinat berada di dalam radius kantor
    elif jarak_ke_kantor > RADIUS_MAKSIMAL:
        st.error(f"❌ Absen Ditolak! Anda berada di luar area kantor. Jarak Anda: {jarak_ke_kantor:.1f} meter (Maksimal toleransi: {RADIUS_MAKSIMAL}m).")
        
    else:
        # Jika GPS Valid, proses pembacaan gambar QR Code dijalankan
        bytes_data = picture.read()
        cv_img = Image.open(BytesIO(bytes_data))
        open_cv_image = np.array(cv_img)
        
        if len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 4:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGBA2RGB)
        elif len(open_cv_image.shape) == 2:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_GRAY2RGB)
            
        open_cv_image = open_cv_image[:, :, ::-1].copy()
        
        st.image(bytes_data, caption="Pratinjau Foto QR Anda", width=200)
        
        with st.spinner("Memvalidasi QR Code..."):
            detector = cv2.QRCodeDetector()
            data, bbox, straight_qrcode = detector.detectAndDecode(open_cv_image)
            
            if data:
                # Validasi isi teks data QR Code
                if data == KODE_QR_SAH:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Cek double absen hari ini
                    sudah_absen = any(d['ID'] == emp_id for d in st.session_state.attendance_db)
                    
                    if not sudah_absen:
                        st.success(f"🎉 ABSENSI BERHASIL! Selamat bekerja, {KARYAWAN_DATA[emp_id]}.")
                        st.session_state.attendance_db.append({
                            "ID": emp_id,
                            "Nama": KARYAWAN_DATA[emp_id],
                            "Waktu Presensi": now_str,
                            "Jarak": f"{jarak_ke_kantor:.1f}m",
                            "Status": "Hadir Sah (QR + GPS Verified)"
                        })
                    else:
                        st.warning("⚠️ Anda sudah terdaftar hadir hari ini.")
                else:
                    st.error("❌ QR Code Salah! Ini bukan QR Code resmi kantor.")
            else:
                st.error("📷 QR Code tidak terdeteksi. Pastikan memotret kertas QR secara dekat, fokus, lurus, dan tidak blur.")

# 📊 Panel Log Hasil Absensi Hari Ini
if st.session_state.attendance_db:
    st.write("---")
    st.subheader("📊 Laporan Absensi Hari Ini")
    df = pd.DataFrame(st.session_state.attendance_db)
    st.dataframe(df, use_container_width=True)
