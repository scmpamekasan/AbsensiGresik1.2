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
KANTOR_LAT = -7.310502   # Rungkut Surabaya
KANTOR_LON = 112.798985  # Rungkut Surabaya
RADIUS_MAKSIMAL = 100.0  # Batas radius dalam METER

KODE_QR_SAH = "KANTOR_UTAMA_SECRET_KEY_2026" 

KARYAWAN_DATA = {
    "EMP001": "Eka Sulawestara",
    "EMP002": "Diny Herlita",
    "EMP003": "Eureka Annisa Naira",
    "EMP004": "Eustacia Redinka Amayra"
}

def hitung_jarak(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000 
    return c * r

if "attendance_db" not in st.session_state:
    st.session_state.attendance_db = []

# ====================================================
# INTERFACE APLIKASI
# ====================================================
st.set_page_config(page_title="Absensi QR + GPS iPhone Fix", layout="centered")
st.title("🔒 Sistem Absensi QR Code Terkunci GPS")

# Dropdown Karyawan
emp_id = st.selectbox("Pilih Profil ID Karyawan", list(KARYAWAN_DATA.keys()), format_func=lambda x: f"{x} - {KARYAWAN_DATA[x]}")

st.write("---")
st.subheader("📍 Langkah 1: Kunci Koordinat GPS Anda")

# TOMBOL PAKSA REFRESH UNTUK MEMBUNUH PROTEKSI CACHE IPHONE
if st.button("🛰️ Aktifkan / Segarkan GPS HP Anda", use_container_width=True):
    st.session_state["trigger_gps"] = True

# Pemicu skrip JavaScript dengan opsi High Accuracy ekstra
js_gps_script = """
window.navigator.geolocation.getCurrentPosition(
    function(pos) { 
        return pos.coords.latitude + ',' + pos.coords.longitude; 
    }, 
    function(err) { 
        return 'ERROR:' + err.message; 
    }, 
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
);
"""

# Pengambilan lokasi secara langsung
loc_string = streamlit_js_eval(data_string=js_gps_script, key=f"gps_tracker_iphone_{st.session_state.get('trigger_gps', False)}")

user_lat, user_lon, jarak_ke_kantor = None, None, None
lokasi_terdeteksi = False

if loc_string:
    if "ERROR" not in loc_string:
        try:
            user_lat, user_lon = map(float, loc_string.split(','))
            jarak_ke_kantor = hitung_jarak(user_lat, user_lon, KANTOR_LAT, KANTOR_LON)
            
            st.info(f"🔍 [DEBUG] Koordinat HP Anda: {user_lat:.6f}, {user_lon:.6f}")
            
            if jarak_ke_kantor <= RADIUS_MAKSIMAL:
                st.success(f"✅ GPS Terkunci! Jarak Anda ke Kantor: **{jarak_ke_kantor:.1f} meter** (Aman).")
                lokasi_terdeteksi = True
            else:
                st.error(f"❌ GPS Terkunci! Namun Anda berada di luar radius kantor ({jarak_ke_kantor:.1f} meter).")
                lokasi_terdeteksi = False
        except:
            st.warning("⏳ Memproses data koordinat satelit...")
    else:
        st.error("❌ Safari iPhone memblokir lokasi. Buka Settings -> Safari -> Location -> Allow.")
else:
    st.warning("⚠️ Ketuk tombol hitam **'🛰️ Aktifkan / Segarkan GPS HP Anda'** di atas terlebih dahulu agar iPhone mengunci lokasi Anda.")

st.write("---")
st.subheader("📸 Langkah 2: Pindai QR Code Kantor")

# Menggunakan file uploader native kamera iPhone
picture = st.file_uploader("Ketuk di sini untuk memotret kertas QR Kantor", type=["png", "jpg", "jpeg"])

if picture is not None:
    # VALIDASI PINDAH KE DALAM TOMBOL SUBMIT UNTUK MEMASTIKAN SYARAT TERPENUHI
    if not lokasi_terdeteksi or jarak_ke_kantor is None:
        st.error("❌ Absen Ditolak! GPS Anda belum aktif atau berada di luar area kantor. Sila ketuk tombol 'Segarkan GPS' di atas terlebih dahulu.")
    else:
        bytes_data = picture.read()
        cv_img = Image.open(BytesIO(bytes_data))
        open_cv_image = np.array(cv_img)
        
        if len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 4:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGBA2RGB)
        elif len(open_cv_image.shape) == 2:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_GRAY2RGB)
            
        open_cv_image = open_cv_image[:, :, ::-1].copy()
        
        st.image(bytes_data, caption="Foto QR Anda", width=200)
        
        with st.spinner("Memvalidasi kode QR..."):
            detector = cv2.QRCodeDetector()
            data, bbox, straight_qrcode = detector.detectAndDecode(open_cv_image)
            
            if data:
                if data == KODE_QR_SAH:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sudah_absen = any(d['ID'] == emp_id for d in st.session_state.attendance_db)
                    
                    if not sudah_absen:
                        st.success(f"🎉 ABSEN BERHASIL! Selamat bekerja, {KARYAWAN_DATA[emp_id]}.")
                        st.session_state.attendance_db.append({
                            "ID": emp_id,
                            "Nama": KARYAWAN_DATA[emp_id],
                            "Waktu Presensi": now_str,
                            "Jarak": f"{jarak_ke_kantor:.1f}m",
                            "Status": "Hadir Sah (QR+GPS)"
                        })
                    else:
                        st.warning("⚠️ Anda sudah terdaftar hadir hari ini.")
                else:
                    st.error("❌ QR Code Salah! Ini bukan QR Code resmi kantor.")
            else:
                st.error("📷 QR Code tidak terbaca. Dekatkan kamera, pastikan fokus dan tidak blur.")

# Laporan Absensi
if st.session_state.attendance_db:
    st.write("---")
    st.subheader("📊 Laporan Absensi Hari Ini")
    df = pd.DataFrame(st.session_state.attendance_db)
    st.dataframe(df, use_container_width=True)
