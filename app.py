"""
SIMULASI EVENT DISKRIT KEDAI KOPI (DES)
Pemodelan dan Simulasi Bisnis — Minggu 10
Jaya Santoso | 2026

Dashboard Streamlit Interaktif untuk Simulasi Kedai Kopi
"""

import streamlit as st
import heapq
import time
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# FUNGSI BANTUAN FORMAT WAKTU
# ---------------------------------------------------------------------------
def format_waktu(menit: float) -> str:
    """Mengonversi menit ke format HH:MM:SS yang mudah dibaca"""
    if menit < 0:
        return "0 jam 0 menit 0 detik"
    
    jam = int(menit // 60)
    sisa_menit = int(menit % 60)
    detik = int((menit % 1) * 60)
    
    bagian = []
    if jam > 0:
        bagian.append(f"{jam} jam")
    if sisa_menit > 0:
        bagian.append(f"{sisa_menit} menit")
    if detik > 0 or (jam == 0 and sisa_menit == 0):
        bagian.append(f"{detik} detik")
    
    return " ".join(bagian) if bagian else "0 detik"

def format_waktu_pendek(menit: float) -> str:
    """Format pendek: HH:MM:SS"""
    jam = int(menit // 60)
    sisa_menit = int(menit % 60)
    detik = int((menit % 1) * 60)
    return f"{jam:02d}:{sisa_menit:02d}:{detik:02d}"

def format_durasi(menit: float) -> str:
    """Format durasi untuk tooltip dan label"""
    if menit < 1:
        return f"{menit * 60:.1f} detik"
    elif menit < 60:
        return f"{menit:.1f} menit"
    else:
        jam = menit / 60
        return f"{jam:.1f} jam"

# ---------------------------------------------------------------------------
# KONFIGURASI HALAMAN
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Simulasi Kedai Kopi DES",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# CSS KHUSUS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp {
        background-color: #0F1117;
    }
    .main-header {
        text-align: center;
        padding: 1rem;
        background: linear-gradient(135deg, #00C9A7 0%, #845EF7 100%);
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #1A1D27;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #2A2D3E;
    }
    .info-text {
        color: #8B8FA8;
        font-size: 0.9rem;
    }
    .waktu-format {
        font-family: monospace;
        font-size: 1.1rem;
        color: #00C9A7;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# TEMA VISUAL GLOBAL
# ---------------------------------------------------------------------------
WARNA = {
    "teal": "#00C9A7",
    "ungu": "#845EF7",
    "kuning": "#FFB347",
    "merah": "#FF6B6B",
    "biru": "#74C0FC",
    "bg_gelap": "#0F1117",
    "bg_kartu": "#1A1D27",
    "batas": "#2A2D3E",
    "teks": "#E8E8F0",
    "teks_sub": "#8B8FA8",
}

# ---------------------------------------------------------------------------
# KONFIGURASI
# ---------------------------------------------------------------------------
@dataclass
class KonfigSim:
    tingkat_kedatangan_per_jam: float = 20.0
    rata_waktu_layanan_menit: float = 3.0
    durasi_simulasi_jam: float = 8.0
    jumlah_ulangan: int = 50
    basis_acak: int = 42

    tingkat_kedatangan_per_menit: float = field(init=False)
    durasi_simulasi_menit: float = field(init=False)

    def __post_init__(self):
        self.tingkat_kedatangan_per_menit = self.tingkat_kedatangan_per_jam / 60.0
        self.durasi_simulasi_menit = self.durasi_simulasi_jam * 60.0


# ---------------------------------------------------------------------------
# PENAMPUNG DATA
# ---------------------------------------------------------------------------
@dataclass
class CatatanPelanggan:
    id_pelanggan: int
    id_ulangan: int
    waktu_datang: float
    mulai_dilayani: float
    selesai_dilayani: float

    @property
    def waktu_tunggu(self) -> float:
        return self.mulai_dilayani - self.waktu_datang

    @property
    def waktu_layanan(self) -> float:
        return self.selesai_dilayani - self.mulai_dilayani

    @property
    def waktu_di_sistem(self) -> float:
        return self.selesai_dilayani - self.waktu_datang


@dataclass
class MetrikUlangan:
    jumlah_barista: int
    id_ulangan: int
    rata_waktu_tunggu: float
    maks_waktu_tunggu: float
    rata_panjang_antrian: float
    maks_panjang_antrian: float
    pelanggan_dilayani: int
    utilisasi_barista: float
    throughput: float
    rata_waktu_di_sistem: float
    maks_waktu_di_sistem: float


# ---------------------------------------------------------------------------
# EVENT SIMULASI
# ---------------------------------------------------------------------------
class Event:
    __slots__ = ("waktu", "jenis", "id_plg", "dur_layanan")

    def __init__(self, waktu: float, jenis: str, id_plg: int, dur_layanan: float = 0.0):
        self.waktu = waktu
        self.jenis = jenis
        self.id_plg = id_plg
        self.dur_layanan = dur_layanan

    def __lt__(self, other: "Event") -> bool:
        return self.waktu < other.waktu


# ---------------------------------------------------------------------------
# MESIN SIMULASI
# ---------------------------------------------------------------------------
class SimulasiKedaiKopi:
    def __init__(self, konfig: KonfigSim, jumlah_barista: int,
                 id_ulangan: int, acak: np.random.Generator):
        self.konfig = konfig
        self.jumlah_barista = jumlah_barista
        self.id_ulangan = id_ulangan
        self.acak = acak

        self.jam = 0.0
        self.bebas = jumlah_barista
        self.antrian: List[Tuple[float, int]] = []
        self.tumpukan: List[Event] = []

        self._waktu_datang: Dict[int, float] = {}
        self._mulai_dilayani: Dict[int, float] = {}

        self.catatan: List[CatatanPelanggan] = []
        self.log_antrian: List[Tuple[float, int]] = []
        self.waktu_sibuk = 0.0
        self._penghitung = 0

    def _waktu_antar_kedatangan(self) -> float:
        return float(self.acak.exponential(1.0 / self.konfig.tingkat_kedatangan_per_menit))

    def _waktu_layanan(self) -> float:
        return float(self.acak.exponential(self.konfig.rata_waktu_layanan_menit))

    def _catat_antrian(self):
        self.log_antrian.append((self.jam, len(self.antrian)))

    def _mulai_layani(self, id_plg: int):
        self.bebas -= 1
        self._mulai_dilayani[id_plg] = self.jam
        durasi = self._waktu_layanan()
        heapq.heappush(self.tumpukan, Event(self.jam + durasi, "SELESAI", id_plg, durasi))

    def jalankan(self) -> MetrikUlangan:
        self._penghitung += 1
        heapq.heappush(self.tumpukan, Event(self._waktu_antar_kedatangan(), "DATANG", self._penghitung))

        while self.tumpukan:
            evt = heapq.heappop(self.tumpukan)
            self.jam = evt.waktu

            if evt.jenis == "DATANG":
                id_plg = evt.id_plg
                self._waktu_datang[id_plg] = self.jam
                self._catat_antrian()

                if self.bebas > 0:
                    self._mulai_layani(id_plg)
                else:
                    self.antrian.append((self.jam, id_plg))

                berikutnya = self.jam + self._waktu_antar_kedatangan()
                if berikutnya <= self.konfig.durasi_simulasi_menit:
                    self._penghitung += 1
                    heapq.heappush(self.tumpukan, Event(berikutnya, "DATANG", self._penghitung))

            else:  # SELESAI
                id_plg = evt.id_plg
                self.waktu_sibuk += evt.dur_layanan
                self.bebas += 1
                waktu_datang = self._waktu_datang.pop(id_plg)
                waktu_mulai = self._mulai_dilayani.pop(id_plg)
                self.catatan.append(CatatanPelanggan(
                    id_pelanggan=id_plg,
                    id_ulangan=self.id_ulangan,
                    waktu_datang=waktu_datang,
                    mulai_dilayani=waktu_mulai,
                    selesai_dilayani=self.jam,
                ))
                self._catat_antrian()

                if self.antrian:
                    _, id_plg2 = self.antrian.pop(0)
                    self._mulai_layani(id_plg2)

        return self._metrik()

    def _metrik(self) -> MetrikUlangan:
        if not self.catatan:
            return MetrikUlangan(self.jumlah_barista, self.id_ulangan,
                                 0, 0, 0, 0, 0, 0, 0, 0, 0)
        waktu_tunggu = [c.waktu_tunggu for c in self.catatan]
        waktu_sistem = [c.waktu_di_sistem for c in self.catatan]
        panjang_antrian = [q for _, q in self.log_antrian]
        utilisasi = min(self.waktu_sibuk /
                       (self.jumlah_barista * self.konfig.durasi_simulasi_menit), 1.0)
        n = len(self.catatan)
        return MetrikUlangan(
            jumlah_barista=self.jumlah_barista,
            id_ulangan=self.id_ulangan,
            rata_waktu_tunggu=float(np.mean(waktu_tunggu)),
            maks_waktu_tunggu=float(np.max(waktu_tunggu)),
            rata_panjang_antrian=float(np.mean(panjang_antrian)) if panjang_antrian else 0,
            maks_panjang_antrian=float(np.max(panjang_antrian)) if panjang_antrian else 0,
            pelanggan_dilayani=n,
            utilisasi_barista=utilisasi,
            throughput=n / self.konfig.durasi_simulasi_jam,
            rata_waktu_di_sistem=float(np.mean(waktu_sistem)),
            maks_waktu_di_sistem=float(np.max(waktu_sistem)),
        )


# ---------------------------------------------------------------------------
# MESIN EKSPERIMEN
# ---------------------------------------------------------------------------
class MesinEksperimen:
    def __init__(self, konfig: KonfigSim):
        self.konfig = konfig

    def jalankan_skenario(self, jumlah_barista: int, callback_progres=None):
        semua_metrik: List[MetrikUlangan] = []
        semua_catatan: List[CatatanPelanggan] = []
        antrian_awal: List[Tuple[float, int]] = []

        for ulang in range(self.konfig.jumlah_ulangan):
            if callback_progres:
                callback_progres(ulang + 1, self.konfig.jumlah_ulangan)
            seed = self.konfig.basis_acak + ulang * 997 + jumlah_barista * 31
            acak = np.random.default_rng(seed)
            sim = SimulasiKedaiKopi(self.konfig, jumlah_barista, ulang, acak)
            m = sim.jalankan()
            semua_metrik.append(m)
            semua_catatan.extend(sim.catatan)
            if ulang == 0:
                antrian_awal = sim.log_antrian
        return semua_metrik, semua_catatan, antrian_awal

    @staticmethod
    def ringkasan(metrik: List[MetrikUlangan]) -> Dict:
        def ci95(v):
            n = len(v)
            if n < 2:
                return 0.0
            return float(stats.t.ppf(0.975, df=n-1) * stats.sem(v))

        kunci = ["rata_waktu_tunggu", "maks_waktu_tunggu",
                "rata_panjang_antrian", "maks_panjang_antrian",
                "pelanggan_dilayani", "utilisasi_barista",
                "throughput", "rata_waktu_di_sistem", "maks_waktu_di_sistem"]
        hasil = {}
        for k in kunci:
            v = [getattr(m, k) for m in metrik]
            hasil[k] = {"rata": float(np.mean(v)),
                    "std": float(np.std(v)) if len(v) > 1 else 0.0,
                    "ci95": ci95(v),
                    "min": float(np.min(v)), "max": float(np.max(v))}
        return hasil


# ---------------------------------------------------------------------------
# FUNGSI VISUALISASI
# ---------------------------------------------------------------------------
def buat_plot_waktu_tunggu(peta_catatan):
    """Membuat plot distribusi waktu tunggu"""
    fig = make_subplots(rows=1, cols=2, 
                        subplot_titles=["2 Barista - Waktu Tunggu", "3 Barista - Waktu Tunggu"])
    
    for i, (n, catatan) in enumerate(peta_catatan.items()):
        wt = [c.waktu_tunggu for c in catatan]
        warna = WARNA["teal"] if n == 2 else WARNA["ungu"]
        
        fig.add_trace(
            go.Histogram(x=wt, nbinsx=50, name=f"{n} Barista",
                        marker_color=warna, opacity=0.7,
                        showlegend=False,
                        hovertemplate='Waktu: %{x:.1f} menit<br>Frekuensi: %{y}<extra></extra>'),
            row=1, col=i+1
        )
        
        # Tambah garis rata-rata
        rata_wt = np.mean(wt)
        fig.add_vline(x=rata_wt, line_dash="dash", 
                     line_color=WARNA["kuning"],
                     annotation_text=f"Rata: {format_waktu(rata_wt)}",
                     annotation_position="top right",
                     row=1, col=i+1)
    
    fig.update_layout(title_text="Distribusi Waktu Tunggu",
                     height=500, showlegend=True,
                     template="plotly_dark",
                     bargap=0.05)
    fig.update_xaxes(title_text="Waktu Tunggu")
    fig.update_yaxes(title_text="Frekuensi")
    return fig


def buat_perbandingan_kpi(ringkasan_data):
    """Membuat grafik perbandingan KPI"""
    skenario = list(ringkasan_data.keys())
    kpis = {
        "Rata Waktu Tunggu": "rata_waktu_tunggu",
        "Rata Panjang Antrian": "rata_panjang_antrian",
        "Throughput (plg/jam)": "throughput",
        "Utilisasi Barista (%)": "utilisasi_barista"
    }
    
    fig = make_subplots(rows=2, cols=2, 
                        subplot_titles=list(kpis.keys()),
                        vertical_spacing=0.15,
                        horizontal_spacing=0.15)
    
    for idx, (judul, kunci) in enumerate(kpis.items()):
        baris, kolom = idx // 2 + 1, idx % 2 + 1
        if "Waktu" in judul:
            # Untuk waktu, tampilkan dalam format yang mudah dibaca di tooltip
            nilai = [ringkasan_data[n][kunci]["rata"] for n in skenario]
            teks_hover = [format_waktu(v) for v in nilai]
        else:
            nilai = [ringkasan_data[n][kunci]["rata"] * (100 if "Utilisasi" in judul else 1) 
                    for n in skenario]
            teks_hover = [f"{v:,.1f}" + ("%" if "Utilisasi" in judul else "") for v in nilai]
        
        error = [ringkasan_data[n][kunci]["ci95"] * (100 if "Utilisasi" in judul else 1) 
                 for n in skenario]
        warna = [WARNA["teal"] if n == 2 else WARNA["ungu"] for n in skenario]
        
        fig.add_trace(
            go.Bar(x=[f"{n} Barista" for n in skenario], 
                  y=nilai,
                  error_y=dict(type='data', array=error, visible=True, color=WARNA["teks"]),
                  marker_color=warna,
                  text=teks_hover,
                  textposition='outside',
                  textfont=dict(color=WARNA["teks"]),
                  hovertemplate='%{x}<br>Nilai: %{text}<extra></extra>'),
            row=baris, col=kolom
        )
    
    fig.update_layout(title_text="Perbandingan Indikator Kinerja Utama",
                     height=600, showlegend=False, 
                     template="plotly_dark",
                     font=dict(color=WARNA["teks"]))
    return fig


def buat_timeline_antrian(peta_log, konfig):
    """Membuat plot panjang antrian terhadap waktu"""
    fig = go.Figure()
    
    for n, log in peta_log.items():
        if not log:
            continue
        t, q = zip(*log)
        warna = WARNA["teal"] if n == 2 else WARNA["ungu"]
        
        # Buat warna rgba untuk fill
        if n == 2:
            warna_fill = "rgba(0, 201, 167, 0.2)"
        else:
            warna_fill = "rgba(132, 94, 247, 0.2)"
        
        # Konversi waktu ke format yang mudah dibaca untuk hover
        waktu_teks = [format_waktu(w) for w in t]
        
        fig.add_trace(go.Scatter(
            x=t, y=q, mode='lines',
            name=f"{n} Barista",
            line=dict(color=warna, width=2),
            fill='tozeroy',
            fillcolor=warna_fill,
            hovertemplate='Waktu: %{customdata}<br>Panjang Antrian: %{y}<extra></extra>',
            customdata=waktu_teks
        ))
    
    fig.add_vline(x=konfig.durasi_simulasi_menit, line_dash="dash",
                  line_color=WARNA["kuning"], line_width=2,
                  annotation_text=f"Akhir Hari ({format_waktu(konfig.durasi_simulasi_menit)})",
                  annotation_position="top right")
    
    fig.update_layout(title="Panjang Antrian Sepanjang Waktu",
                     xaxis_title="Waktu",
                     yaxis_title="Jumlah Pelanggan dalam Antrian",
                     height=500, 
                     template="plotly_dark",
                     hovermode='x unified')
    
    # Update x-axis tick labels ke format waktu
    fig.update_xaxes(
        tickvals=np.arange(0, konfig.durasi_simulasi_menit + 60, 60),
        ticktext=[format_waktu(t) for t in np.arange(0, konfig.durasi_simulasi_menit + 60, 60)]
    )
    return fig


def buat_perbandingan_utilisasi(ringkasan_data):
    """Membuat perbandingan utilisasi barista"""
    skenario = list(ringkasan_data.keys())
    utilisasi = [ringkasan_data[n]["utilisasi_barista"]["rata"] * 100 for n in skenario]
    error = [ringkasan_data[n]["utilisasi_barista"]["ci95"] * 100 for n in skenario]
    warna = [WARNA["teal"] if n == 2 else WARNA["ungu"] for n in skenario]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[f"{n} Barista" for n in skenario],
        y=utilisasi,
        error_y=dict(type='data', array=error, visible=True, color=WARNA["teks"]),
        marker_color=warna,
        text=[f"{u:,.1f}%" for u in utilisasi],
        textposition='outside',
        textfont=dict(color=WARNA["teks"])
    ))
    
    fig.add_hline(y=80, line_dash="dash", 
                  line_color=WARNA["merah"], line_width=2,
                  annotation_text="Batas 80% (Direkomendasikan)",
                  annotation_position="top right")
    
    fig.update_layout(title="Perbandingan Utilisasi Barista",
                     xaxis_title="Skenario",
                     yaxis_title="Utilisasi (%)",
                     yaxis_range=[0, 105],
                     height=500, 
                     template="plotly_dark")
    return fig


def buat_plot_sensitivitas(konfig):
    """Membuat plot analisis sensitivitas"""
    with st.spinner("Menjalankan analisis sensitivitas..."):
        cepat = KonfigSim(
            tingkat_kedatangan_per_jam=konfig.tingkat_kedatangan_per_jam,
            rata_waktu_layanan_menit=konfig.rata_waktu_layanan_menit,
            durasi_simulasi_jam=konfig.durasi_simulasi_jam,
            jumlah_ulangan=30,
            basis_acak=konfig.basis_acak,
        )
        mesin = MesinEksperimen(cepat)
        hasil = {}
        
        for n in range(1, 6):
            m, _, _ = mesin.jalankan_skenario(n)
            hasil[n] = mesin.ringkasan(m)
    
    fig = make_subplots(rows=2, cols=2,
                        subplot_titles=["Rata Waktu Tunggu", 
                                      "Utilisasi Barista",
                                      "Rata Panjang Antrian", 
                                      "Throughput"],
                        vertical_spacing=0.15,
                        horizontal_spacing=0.15)
    
    kpis = [
        ("rata_waktu_tunggu", "Rata Waktu Tunggu", WARNA["teal"], True),
        ("utilisasi_barista", "Utilisasi (%)", WARNA["ungu"], False),
        ("rata_panjang_antrian", "Rata Panjang Antrian", WARNA["kuning"], False),
        ("throughput", "Throughput (plg/jam)", WARNA["biru"], False)
    ]
    
    for idx, (kunci, judul, warna, is_waktu) in enumerate(kpis):
        baris, kolom = idx // 2 + 1, idx % 2 + 1
        ns = list(range(1, 6))
        if is_waktu:
            nilai = [hasil[n][kunci]["rata"] for n in ns]
            teks_hover = [format_waktu(v) for v in nilai]
        else:
            pengali = 100 if "Utilisasi" in judul else 1
            nilai = [hasil[n][kunci]["rata"] * pengali for n in ns]
            teks_hover = [f"{v:,.1f}" + ("%" if "Utilisasi" in judul else "") for v in nilai]
        
        error = [hasil[n][kunci]["ci95"] * (100 if "Utilisasi" in judul else 1) for n in ns]
        
        fig.add_trace(
            go.Scatter(x=ns, y=nilai, mode='lines+markers',
                      name=judul, 
                      line=dict(color=warna, width=3),
                      marker=dict(size=10, color=warna, 
                                symbol='circle',
                                line=dict(color=WARNA["bg_gelap"], width=2)),
                      error_y=dict(type='data', array=error, 
                                 visible=True, color=warna,
                                 thickness=2, width=10),
                      hovertemplate='Jumlah Barista: %{x}<br>%{text}<extra></extra>',
                      text=teks_hover),
            row=baris, col=kolom
        )
        
        fig.update_xaxes(title_text="Jumlah Barista", row=baris, col=kolom)
        fig.update_yaxes(title_text=judul, row=baris, col=kolom)
    
    fig.update_layout(title="Analisis Sensitivitas: Dampak Jumlah Barista",
                     height=600, showlegend=False, 
                     template="plotly_dark",
                     hovermode='x unified')
    return fig


def buat_plot_waktu_layanan(peta_catatan):
    """Membuat plot distribusi waktu layanan"""
    fig = go.Figure()
    
    for n, catatan in peta_catatan.items():
        waktu_layanan = [c.waktu_layanan for c in catatan]
        warna = WARNA["teal"] if n == 2 else WARNA["ungu"]
        
        fig.add_trace(go.Histogram(
            x=waktu_layanan, 
            nbinsx=50, 
            name=f"{n} Barista",
            marker_color=warna,
            opacity=0.7,
            histnorm='probability density',
            hovertemplate='Waktu: %{x:.1f} menit<br>Kepadatan: %{y:.3f}<extra></extra>'
        ))
        
        # Tambah garis KDE
        kde_x = np.linspace(0, np.percentile(waktu_layanan, 99), 100)
        kde = stats.gaussian_kde(waktu_layanan)
        fig.add_trace(go.Scatter(
            x=kde_x, y=kde(kde_x),
            mode='lines',
            name=f"{n} Barista (KDE)",
            line=dict(color=warna, width=2, dash='dash'),
            showlegend=False
        ))
    
    fig.update_layout(title="Distribusi Waktu Layanan",
                     xaxis_title="Waktu Layanan",
                     yaxis_title="Kepadatan",
                     height=500, 
                     template="plotly_dark",
                     barmode='overlay',
                     bargap=0.05)
    return fig


def buat_throughput_kumulatif(peta_catatan):
    """Membuat plot throughput kumulatif"""
    fig = go.Figure()
    
    for n, catatan in peta_catatan.items():
        if not catatan:
            continue
        catatan_urut = sorted(catatan, key=lambda c: c.selesai_dilayani)
        waktu = [c.selesai_dilayani for c in catatan_urut]
        kumulatif = list(range(1, len(waktu) + 1))
        warna = WARNA["teal"] if n == 2 else WARNA["ungu"]
        
        waktu_teks = [format_waktu(w) for w in waktu]
        
        fig.add_trace(go.Scatter(
            x=waktu, y=kumulatif,
            mode='lines',
            name=f"{n} Barista",
            line=dict(color=warna, width=2.5),
            fill='tozeroy',
            fillcolor=f"rgba{tuple(int(warna.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (0.1,)}",
            hovertemplate='Waktu: %{customdata}<br>Total Pelanggan: %{y}<extra></extra>',
            customdata=waktu_teks
        ))
    
    fig.update_layout(title="Kumulatif Pelanggan Dilayani Sepanjang Waktu",
                     xaxis_title="Waktu",
                     yaxis_title="Total Pelanggan Dilayani",
                     height=500, 
                     template="plotly_dark",
                     hovermode='x unified')
    return fig


def buat_boxplot_waktu_sistem(peta_catatan):
    """Membuat boxplot perbandingan waktu di sistem"""
    fig = go.Figure()
    
    data = []
    for n, catatan in peta_catatan.items():
        waktu_sistem = [c.waktu_di_sistem for c in catatan]
        data.append(go.Box(y=waktu_sistem, name=f"{n} Barista",
                          marker_color=WARNA["teal"] if n == 2 else WARNA["ungu"],
                          boxmean='sd',
                          hovertemplate='Waktu di Sistem: %{y:.1f} menit<br>%{text}<extra></extra>'))
    
    fig = go.Figure(data=data)
    fig.update_layout(title="Perbandingan Distribusi Waktu di Sistem",
                     xaxis_title="Skenario",
                     yaxis_title="Waktu di Sistem",
                     height=500, 
                     template="plotly_dark",
                     showlegend=False)
    return fig


# ---------------------------------------------------------------------------
# APLIKASI STREAMLIT UTAMA
# ---------------------------------------------------------------------------
def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1 style="color: white; margin: 0;">☕ Simulasi Kedai Kopi</h1>
        <p style="color: #E8E8F0; margin: 0.5rem 0 0 0;">Simulasi Event Diskrit (DES) dengan Model Antrian M/M/c</p>
        <p style="color: #8B8FA8; margin: 0.25rem 0 0 0; font-size: 0.8rem;">Jaya Santoso | Minggu 10 - Pemodelan dan Simulasi Bisnis</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("## 👥 Kelompok 7")
        
        members = [
        ("Gilbert Gultom", "11S25014"),
        ("Jose Napitupulu", "11S25026"),
        ("Tessa Manurung", "11S25045"),
        ("Shalomytha Siregar", "11S25049"),
        ("Michael Siburian", "11S25007"),
        ("Renaldi Tambunan", "11S25022"),
    ]
        for name, nim in members:
            with st.container():
                st.markdown(f"""
                🔹 **{name}**  
                🆔 `{nim}`
                """)

        st.divider()
        st.caption("Simulasi & Visualisasi Sistem Antrian")
               
        st.markdown("## 📊 Parameter Simulasi")
        
        tingkat_kedatangan = st.number_input(
            "Tingkat Kedatangan (pelanggan/jam)",
            min_value=5.0, max_value=50.0, value=20.0, step=1.0,
            help="Tingkat kedatangan Poisson - rata-rata pelanggan datang per jam"
        )
        
        waktu_layanan = st.number_input(
            "Rata Waktu Layanan",
            min_value=0.5, max_value=15.0, value=3.0, step=0.5,
            help="Rata-rata waktu layanan eksponensial - waktu rata-rata untuk melayani satu pelanggan",
            format="%.1f"
        )
        
        # Tampilkan contoh format waktu layanan
        st.caption(f"Contoh: {waktu_layanan} menit = {format_waktu(waktu_layanan)}")
        
        durasi_simulasi = st.number_input(
            "Durasi Simulasi",
            min_value=1.0, max_value=12.0, value=8.0, step=1.0,
            help="Total waktu simulasi",
            format="%.1f"
        )
        
        # Tampilkan contoh format durasi
        st.caption(f"Contoh: {durasi_simulasi} jam = {format_waktu(durasi_simulasi * 60)}")
        
        jumlah_ulangan = st.slider(
            "Jumlah Ulangan",
            min_value=10, max_value=100, value=50, step=10,
            help="Semakin banyak ulangan = hasil semakin akurat (CI 95%)"
        )
        
        st.markdown("---")
        
        st.markdown("### 🎯 Teori Antrian")
        st.info(f"""
        **Parameter Antrian M/M/c:**
        - λ = {tingkat_kedatangan:,.1f} pelanggan/jam
        - μ = {60/waktu_layanan:,.1f} pelanggan/jam
        - Rata layanan = {format_waktu(waktu_layanan)}
        - ρ = {tingkat_kedatangan/((60/waktu_layanan)*2):,.2f} (untuk 2 barista)
        """)
        
        st.markdown("---")
        
        st.markdown("### ℹ️ Tentang")
        st.markdown("""
        Simulasi ini menggunakan **Simulasi Event Diskrit (DES)** dengan:
        - Mesin DES kustom (antrian event min-heap)
        - Kedatangan Poisson
        - Waktu layanan eksponensial
        - Interval Kepercayaan 95%
        - Banyak ulangan
        - **Waktu ditampilkan dalam format Jam:Menit:Detik**
        """)
        
        jalankan_simulasi = st.button("🚀 JALANKAN SIMULASI", type="primary", use_container_width=True)
    
    # Konten utama
    if jalankan_simulasi:
        # Konfigurasi
        konfig = KonfigSim(
            tingkat_kedatangan_per_jam=tingkat_kedatangan,
            rata_waktu_layanan_menit=waktu_layanan,
            durasi_simulasi_jam=durasi_simulasi,
            jumlah_ulangan=jumlah_ulangan,
            basis_acak=42
        )
        
        mesin = MesinEksperimen(konfig)
        skenario = [2, 3]
        peta_metrik = {}
        peta_catatan = {}
        peta_log = {}
        ringkasan_data = {}
        
        # Jalankan simulasi dengan progres
        with st.spinner("Menjalankan simulasi..."):
            bilah_progres = st.progress(0)
            teks_status = st.empty()
            
            for idx, n in enumerate(skenario):
                teks_status.text(f"🔄 Menjalankan skenario: {n} Barista...")
                
                def update_progres(terkini, total):
                    progres = (idx + terkini/total) / len(skenario)
                    bilah_progres.progress(progres)
                    teks_status.text(f"🔄 {n} Barista: {terkini:,}/{total:,} ulangan")
                
                m, r, ql = mesin.jalankan_skenario(n, update_progres)
                peta_metrik[n] = m
                peta_catatan[n] = r
                peta_log[n] = ql
                ringkasan_data[n] = mesin.ringkasan(m)
            
            bilah_progres.progress(1.0)
            teks_status.text("✅ Simulasi selesai!")
            time.sleep(0.5)
            teks_status.empty()
            bilah_progres.empty()
        
        # Tampilan Metrik Utama
        st.markdown("## 📈 Indikator Kinerja Utama")
        
        kol1, kol2, kol3, kol4 = st.columns(4)
        
        for idx, n in enumerate(skenario):
            kolom = [kol1, kol2, kol3, kol4]
            with kolom[idx]:
                rata_tunggu = ringkasan_data[n]['rata_waktu_tunggu']['rata']
                st.markdown(f"""
                <div class="metric-card">
                    <h3 style="color: {WARNA['teal'] if n==2 else WARNA['ungu']}; margin: 0;">{n} Barista</h3>
                    <hr style="margin: 0.5rem 0;">
                    <p style="margin: 0.25rem 0;"><strong>Rata Tunggu:</strong> <span class="waktu-format">{format_waktu(rata_tunggu)}</span></p>
                    <p style="margin: 0.25rem 0; font-size: 0.8rem; color: {WARNA['teks_sub']};">±{format_waktu(ringkasan_data[n]['rata_waktu_tunggu']['ci95'])} (CI 95%)</p>
                    <p style="margin: 0.25rem 0;"><strong>Utilisasi:</strong> {ringkasan_data[n]['utilisasi_barista']['rata']*100:,.1f}%</p>
                    <p style="margin: 0.25rem 0;"><strong>Throughput:</strong> {ringkasan_data[n]['throughput']['rata']:,.1f} plg/jam</p>
                    <p style="margin: 0.25rem 0;"><strong>Pelanggan:</strong> {ringkasan_data[n]['pelanggan_dilayani']['rata']:,.0f}</p>
                </div>
                """, unsafe_allow_html=True)
        
        with kolom[3]:
            # Rekomendasi berdasarkan utilisasi
            utilisasi_2 = ringkasan_data[2]['utilisasi_barista']['rata'] * 100
            utilisasi_3 = ringkasan_data[3]['utilisasi_barista']['rata'] * 100
            
            if utilisasi_2 > 80:
                rekomendasi = "⚠️ Pertimbangkan menambah barista"
            elif utilisasi_3 < 60:
                rekomendasi = "✅ Staf saat ini sudah efisien"
            else:
                rekomendasi = "👍 Tingkat staf sudah optimal"
            
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="color: {WARNA['kuning']}; margin: 0;">💡 Rekomen</h3>
                <hr style="margin: 0.5rem 0;">
                <p style="margin: 0.25rem 0;">{rekomendasi}</p>
                <p style="margin: 0.25rem 0; font-size: 0.8rem; color: {WARNA['teks_sub']};">
                Target utilisasi: 60-80%
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        # Tab untuk visualisasi
        st.markdown("---")
        st.markdown("## 📊 Analisis Detail")
        
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📈 Analisis Antrian",
            "📊 Perbandingan KPI", 
            "📉 Analisis Distribusi",
            "🔬 Analisis Sensitivitas",
            "📋 Metrik Kinerja",
            "💾 Ekspor Data"
        ])
        
        with tab1:
            kol1, kol2 = st.columns(2)
            with kol1:
                st.plotly_chart(buat_timeline_antrian(peta_log, konfig), use_container_width=True)
            with kol2:
                st.plotly_chart(buat_perbandingan_utilisasi(ringkasan_data), use_container_width=True)
            st.plotly_chart(buat_throughput_kumulatif(peta_catatan), use_container_width=True)
        
        with tab2:
            st.plotly_chart(buat_perbandingan_kpi(ringkasan_data), use_container_width=True)
            st.plotly_chart(buat_boxplot_waktu_sistem(peta_catatan), use_container_width=True)
        
        with tab3:
            st.plotly_chart(buat_plot_waktu_tunggu(peta_catatan), use_container_width=True)
            st.plotly_chart(buat_plot_waktu_layanan(peta_catatan), use_container_width=True)
        
        with tab4:
            st.plotly_chart(buat_plot_sensitivitas(konfig), use_container_width=True)
            st.info("💡 **Wawasan:** Seiring bertambahnya jumlah barista, waktu tunggu menurun namun utilisasi juga turun. Tingkat staf yang optimal menyeimbangkan kualitas layanan dengan efisiensi sumber daya.")
        
        with tab5:
            st.subheader("📋 Ringkasan Metrik Detail")
            
            # Buat tabel metrik detail dengan format waktu
            data_detil = []
            for n in skenario:
                s = ringkasan_data[n]
                data_detil.append({
                    "Skenario": f"{n} Barista",
                    "Rata Waktu Tunggu": format_waktu(s['rata_waktu_tunggu']['rata']),
                    "Rata Waktu Tunggu (CI95)": f"±{format_waktu(s['rata_waktu_tunggu']['ci95'])}",
                    "Maks Waktu Tunggu": format_waktu(s['maks_waktu_tunggu']['rata']),
                    "Rata Panjang Antrian": f"{s['rata_panjang_antrian']['rata']:,.2f} ± {s['rata_panjang_antrian']['ci95']:,.2f}",
                    "Maks Panjang Antrian": f"{s['maks_panjang_antrian']['rata']:,.0f}",
                    "Utilisasi Barista": f"{s['utilisasi_barista']['rata']*100:,.1f}% ± {s['utilisasi_barista']['ci95']*100:,.1f}%",
                    "Throughput (plg/jam)": f"{s['throughput']['rata']:,.1f} ± {s['throughput']['ci95']:,.1f}",
                    "Rata Waktu di Sistem": format_waktu(s['rata_waktu_di_sistem']['rata']),
                    "Pelanggan Dilayani": f"{s['pelanggan_dilayani']['rata']:,.0f}"
                })
            
            st.dataframe(pd.DataFrame(data_detil), use_container_width=True)
            
            # Statistik tambahan dengan format waktu
            st.subheader("📊 Ringkasan Statistik")
            kol1, kol2 = st.columns(2)
            
            with kol1:
                st.markdown("#### 2 Barista")
                metrik_2 = peta_metrik[2]
                waktu_tunggu = [m.rata_waktu_tunggu for m in metrik_2]
                st.markdown(f"""
                - **Rata Waktu Tunggu:** {format_waktu(np.mean(waktu_tunggu))}
                - **Std Deviasi:** {format_waktu(np.std(waktu_tunggu))}
                - **Min Tunggu:** {format_waktu(np.min(waktu_tunggu))}
                - **Max Tunggu:** {format_waktu(np.max(waktu_tunggu))}
                - **Lebar CI 95%:** {format_waktu(ringkasan_data[2]['rata_waktu_tunggu']['ci95']*2)}
                """)
            
            with kol2:
                st.markdown("#### 3 Barista")
                metrik_3 = peta_metrik[3]
                waktu_tunggu = [m.rata_waktu_tunggu for m in metrik_3]
                st.markdown(f"""
                - **Rata Waktu Tunggu:** {format_waktu(np.mean(waktu_tunggu))}
                - **Std Deviasi:** {format_waktu(np.std(waktu_tunggu))}
                - **Min Tunggu:** {format_waktu(np.min(waktu_tunggu))}
                - **Max Tunggu:** {format_waktu(np.max(waktu_tunggu))}
                - **Lebar CI 95%:** {format_waktu(ringkasan_data[3]['rata_waktu_tunggu']['ci95']*2)}
                """)
        
        with tab6:
            st.subheader("💾 Ekspor Data Simulasi")
            
            kol1, kol2 = st.columns(2)
            
            with kol1:
                st.markdown("#### Catatan Pelanggan")
                for n, catatan in peta_catatan.items():
                    df = pd.DataFrame([{
                        "ID Pelanggan": c.id_pelanggan,
                        "ID Ulangan": c.id_ulangan,
                        "Waktu Datang": format_waktu(c.waktu_datang),
                        "Mulai Dilayani": format_waktu(c.mulai_dilayani),
                        "Selesai Dilayani": format_waktu(c.selesai_dilayani),
                        "Waktu Tunggu (menit)": round(c.waktu_tunggu, 2),
                        "Waktu Tunggu": format_waktu(c.waktu_tunggu),
                        "Waktu Layanan (menit)": round(c.waktu_layanan, 2),
                        "Waktu Layanan": format_waktu(c.waktu_layanan),
                        "Waktu di Sistem (menit)": round(c.waktu_di_sistem, 2),
                        "Waktu di Sistem": format_waktu(c.waktu_di_sistem)
                    } for c in catatan])
                    
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label=f"📥 Unduh Data {n} Barista ({len(df):,} catatan)",
                        data=csv,
                        file_name=f"kedai_kopi_{n}_barista.csv",
                        mime="text/csv",
                        key=f"unduh_{n}"
                    )
            
            with kol2:
                st.markdown("#### Dataset Lengkap")
                semua_data = []
                for n, catatan in peta_catatan.items():
                    for c in catatan:
                        semua_data.append({
                            "jumlah_barista": n,
                            "id_pelanggan": c.id_pelanggan,
                            "id_ulangan": c.id_ulangan,
                            "waktu_datang_menit": round(c.waktu_datang, 2),
                            "waktu_datang": format_waktu(c.waktu_datang),
                            "waktu_tunggu_menit": round(c.waktu_tunggu, 2),
                            "waktu_tunggu": format_waktu(c.waktu_tunggu),
                            "waktu_layanan_menit": round(c.waktu_layanan, 2),
                            "waktu_layanan": format_waktu(c.waktu_layanan),
                            "waktu_di_sistem_menit": round(c.waktu_di_sistem, 2),
                            "waktu_di_sistem": format_waktu(c.waktu_di_sistem)
                        })
                
                df_semua = pd.DataFrame(semua_data)
                csv_semua = df_semua.to_csv(index=False)
                st.download_button(
                    label="📥 Unduh Dataset Lengkap (Semua Skenario)",
                    data=csv_semua,
                    file_name="simulasi_kedai_kopi_semua_data.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                st.markdown("#### Statistik Ringkasan")
                df_ringkasan = pd.DataFrame(data_detil)
                csv_ringkasan = df_ringkasan.to_csv(index=False)
                st.download_button(
                    label="📥 Unduh Statistik Ringkasan",
                    data=csv_ringkasan,
                    file_name="kedai_kopi_ringkasan_statistik.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            st.success("✅ Semua data telah diproses dan siap diunduh!")
    
    else:
        # Pesan selamat datang ketika belum ada simulasi yang dijalankan
        st.markdown("""
        <div style="text-align: center; padding: 3rem; background-color: #1A1D27; border-radius: 10px; margin: 2rem 0;">
            <h2 style="color: #00C9A7;">☕ Selamat Datang di Simulasi Kedai Kopi</h2>
            <p style="color: #E8E8F0; font-size: 1.1rem;">
                Konfigurasikan parameter simulasi di sidebar dan klik <strong>JALANKAN SIMULASI</strong> untuk memulai.
            </p>
            <hr style="margin: 2rem 0;">
            <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <h3 style="color: #845EF7;">📊 Antrian M/M/c</h3>
                    <p>Kedatangan Poisson + Layanan eksponensial</p>
                </div>
                <div>
                    <h3 style="color: #FFB347;">🎯 Mesin DES</h3>
                    <p>Simulasi event diskrit kustom</p>
                </div>
                <div>
                    <h3 style="color: #00C9A7;">📈 CI 95%</h3>
                    <p>Interval kepercayaan via distribusi-t</p>
                </div>
                <div>
                    <h3 style="color: #74C0FC;">⏰ Format Waktu</h3>
                    <p>Jam:Menit:Detik yang mudah dibaca</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Pratinjau visualisasi contoh
        st.markdown("### 📊 Yang Akan Anda Lihat")
        kol1, kol2 = st.columns(2)
        
        with kol1:
            st.markdown("""
            **Analisis Antrian:**
            - Panjang antrian terhadap waktu (dalam format HH:MM:SS)
            - Utilisasi barista
            - Throughput kumulatif (dengan timestamp waktu)
            
            **Analisis Distribusi:**
            - Histogram waktu tunggu (dalam format waktu)
            - Distribusi waktu layanan
            - Boxplot waktu di sistem
            """)
        
        with kol2:
            st.markdown("""
            **Metrik Kinerja:**
            - Rata-rata waktu tunggu (contoh: 2 menit 30 detik)
            - Statistik panjang antrian
            - Analisis throughput
            - Utilisasi sumber daya
            
            **Analisis Sensitivitas:**
            - Dampak jumlah barista (1-5)
            - Rekomendasi staf optimal
            - Analisis trade-off dengan format waktu
            """)


if __name__ == "__main__":
    main()