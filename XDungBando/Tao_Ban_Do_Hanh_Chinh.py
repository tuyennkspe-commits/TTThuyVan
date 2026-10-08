import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.patheffects as pe
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.colors import LightSource
from matplotlib.ticker import MultipleLocator, FuncFormatter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from shapely.geometry import box, LineString, MultiLineString, Polygon as ShapelyPolygon, MultiPolygon
import shapely
import numpy as np
import urllib.request
import json
import threading
import os
import re
import math
import traceback
import warnings

warnings.filterwarnings('ignore', category=UserWarning)

# Thư viện xử lý DEM
try:
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman', 'DejaVu Serif']
plt.rcParams['axes.unicode_minus'] = False

CRS_DICT = {
    "WGS84 - Độ thập phân (EPSG:4326)": "EPSG:4326",
    "VN-2000 / UTM Múi 48N (EPSG:3405)": "EPSG:3405",
    "WGS84 / UTM Zone 48N (EPSG:32648)": "EPSG:32648",
    "VN-2000 Nội tỉnh (KTT địa phương)": "+proj=tmerc +lat_0=0 +lon_0=105.0 +k=0.9999 +x_0=500000 +y_0=0 +ellps=WGS84 +units=m +no_defs"
}

PROVINCES_META_34 = {
    'an giang': {'name': 'An Giang', 'type': 'TỈNH', 'foreign': ['CAMPUCHIA'], 'sea': 'VỊNH THÁI LAN', 'sea_dir': 'W'},
    'bac ninh': {'name': 'Bắc Ninh', 'type': 'THÀNH PHỐ', 'foreign': [], 'sea': None, 'sea_dir': None},
    'ca mau': {'name': 'Cà Mau', 'type': 'TỈNH', 'foreign': [], 'sea': 'BIỂN ĐÔNG / VỊNH THÁI LAN', 'sea_dir': 'ALL'},
    'cao bang': {'name': 'Cao Bằng', 'type': 'TỈNH', 'foreign': ['TRUNG QUỐC'], 'sea': None, 'sea_dir': None},
    'can tho': {'name': 'Cần Thơ', 'type': 'THÀNH PHỐ', 'foreign': [], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'da nang': {'name': 'Đà Nẵng', 'type': 'THÀNH PHỐ', 'foreign': ['LÀO'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'dak lak': {'name': 'Đắk Lắk', 'type': 'TỈNH', 'foreign': ['CAMPUCHIA'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'dien bien': {'name': 'Điện Biên', 'type': 'TỈNH', 'foreign': ['LÀO', 'TRUNG QUỐC'], 'sea': None, 'sea_dir': None},
    'dong nai': {'name': 'Đồng Nai', 'type': 'TỈNH', 'foreign': ['CAMPUCHIA'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'dong thap': {'name': 'Đồng Tháp', 'type': 'TỈNH', 'foreign': ['CAMPUCHIA'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'gia lai': {'name': 'Gia Lai', 'type': 'TỈNH', 'foreign': ['CAMPUCHIA'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'ha noi': {'name': 'Hà Nội', 'type': 'THÀNH PHỐ', 'foreign': [], 'sea': None, 'sea_dir': None},
    'ha tinh': {'name': 'Hà Tĩnh', 'type': 'TỈNH', 'foreign': ['LÀO'], 'sea': 'VỊNH BẮC BỘ', 'sea_dir': 'E'},
    'hai phong': {'name': 'Hải Phòng', 'type': 'THÀNH PHỐ', 'foreign': [], 'sea': 'VỊNH BẮC BỘ', 'sea_dir': 'E'},
    'ho chi minh': {'name': 'Hồ Chí Minh', 'type': 'THÀNH PHỐ', 'foreign': [], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'hue': {'name': 'Huế', 'type': 'THÀNH PHỐ', 'foreign': ['LÀO'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'hung yen': {'name': 'Hưng Yên', 'type': 'TỈNH', 'foreign': [], 'sea': 'VỊNH BẮC BỘ', 'sea_dir': 'E'},
    'khanh hoa': {'name': 'Khánh Hòa', 'type': 'TỈNH', 'foreign': [], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'lai chau': {'name': 'Lai Châu', 'type': 'TỈNH', 'foreign': ['TRUNG QUỐC'], 'sea': None, 'sea_dir': None},
    'lam dong': {'name': 'Lâm Đồng', 'type': 'TỈNH', 'foreign': ['CAMPUCHIA'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'lang son': {'name': 'Lạng Sơn', 'type': 'TỈNH', 'foreign': ['TRUNG QUỐC'], 'sea': None, 'sea_dir': None},
    'lao cai': {'name': 'Lào Cai', 'type': 'TỈNH', 'foreign': ['TRUNG QUỐC'], 'sea': None, 'sea_dir': None},
    'nghe an': {'name': 'Nghệ An', 'type': 'TỈNH', 'foreign': ['LÀO'], 'sea': 'VỊNH BẮC BỘ', 'sea_dir': 'E'},
    'ninh binh': {'name': 'Ninh Bình', 'type': 'TỈNH', 'foreign': [], 'sea': 'VỊNH BẮC BỘ', 'sea_dir': 'E'},
    'phu tho': {'name': 'Phú Thọ', 'type': 'TỈNH', 'foreign': [], 'sea': None, 'sea_dir': None},
    'quang ngai': {'name': 'Quảng Ngãi', 'type': 'TỈNH', 'foreign': ['LÀO', 'CAMPUCHIA'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'quang ninh': {'name': 'Quảng Ninh', 'type': 'TỈNH', 'foreign': ['TRUNG QUỐC'], 'sea': 'VỊNH BẮC BỘ', 'sea_dir': 'E'},
    'quang tri': {'name': 'Quảng Trị', 'type': 'TỈNH', 'foreign': ['LÀO'], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'},
    'son la': {'name': 'Sơn La', 'type': 'TỈNH', 'foreign': ['LÀO'], 'sea': None, 'sea_dir': None},
    'tay ninh': {'name': 'Tây Ninh', 'type': 'TỈNH', 'foreign': ['CAMPUCHIA'], 'sea': None, 'sea_dir': None},
    'thai nguyen': {'name': 'Thái Nguyên', 'type': 'TỈNH', 'foreign': [], 'sea': None, 'sea_dir': None},
    'thanh hoa': {'name': 'Thanh Hóa', 'type': 'TỈNH', 'foreign': ['LÀO'], 'sea': 'VỊNH BẮC BỘ', 'sea_dir': 'E'},
    'tuyen quang': {'name': 'Tuyên Quang', 'type': 'TỈNH', 'foreign': ['TRUNG QUỐC'], 'sea': None, 'sea_dir': None},
    'vinh long': {'name': 'Vĩnh Long', 'type': 'TỈNH', 'foreign': [], 'sea': 'BIỂN ĐÔNG', 'sea_dir': 'E'}
}

MERGED_OLD_TO_NEW = {
    'thai binh': 'hung yen',
    'ha nam': 'ninh binh', 'nam dinh': 'ninh binh',
    'hai duong': 'hai phong',
    'vinh phuc': 'phu tho', 'hoa binh': 'phu tho',
    'bac kan': 'thai nguyen',
    'ha giang': 'tuyen quang',
    'yen bai': 'lao cai',
    'quang binh': 'quang tri',
    'kon tum': 'quang ngai',
    'quang nam': 'da nang',
    'binh dinh': 'gia lai',
    'phu yen': 'dak lak',
    'ninh thuan': 'khanh hoa',
    'dak nong': 'lam dong', 'binh thuan': 'lam dong',
    'binh phuoc': 'dong nai',
    'ba ria - vung tau': 'ho chi minh', 'ba ria': 'ho chi minh', 'vung tau': 'ho chi minh', 'binh duong': 'ho chi minh',
    'long an': 'tay ninh',
    'tien giang': 'dong thap',
    'ben tre': 'vinh long', 'tra vinh': 'vinh long',
    'soc trang': 'can tho', 'hau giang': 'can tho',
    'bac lieu': 'ca mau',
    'kien giang': 'an giang',
    'bac giang': 'bac ninh'
}

def remove_accents(text):
    patterns = {
        '[àáảãạăằắẳẵặâầấẩẫậ]': 'a', '[èéẻẽẹêềếểễệ]': 'e',
        '[ìíỉĩị]': 'i', '[òóỏõọôồốổỗộơờớởỡợ]': 'o',
        '[ùúủũụưừứửữự]': 'u', '[ỳýỷỹỵ]': 'y', '[đ]': 'd',
        '[ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ]': 'A', '[ÈÉẺẼẸÊỀẾỂỄỆ]': 'E',
        '[ÌÍỈĨỊ]': 'I', '[ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ]': 'O',
        '[ÙÚỦŨỤƯỪỨỬỮỰ]': 'U', '[ỲÝỶỸỴ]': 'Y', '[Đ]': 'D'
    }
    for regex, rep in patterns.items():
        text = re.sub(regex, rep, text)
    return text.strip().lower()

def safe_polylabel(geom):
    try:
        if hasattr(shapely, 'polylabel'):
            return shapely.polylabel(geom, tolerance=0.001)
        from shapely.ops import polylabel
        return polylabel(geom, tolerance=0.001)
    except Exception:
        return geom.representative_point()

def find_best_province_key(user_input):
    clean = remove_accents(user_input)
    aliases = {
        'tphcm': 'ho chi minh', 'hcm': 'ho chi minh', 'sai gon': 'ho chi minh',
        'tp.hcm': 'ho chi minh', 'tp hcm': 'ho chi minh', 'thua thien': 'hue',
        'thua thien hue': 'hue', 'tp hue': 'hue'
    }
    if clean in aliases:
        return aliases[clean]
    if clean in MERGED_OLD_TO_NEW:
        return MERGED_OLD_TO_NEW[clean]
    for key in PROVINCES_META_34:
        if key in clean or clean in key:
            return key
    for old_k, new_k in MERGED_OLD_TO_NEW.items():
        if old_k in clean or clean in old_k:
            return new_k
    return 'ho chi minh'

def find_province_column(gdf, target_prov_name):
    clean_target = remove_accents(target_prov_name)
    core_target = re.sub(r'^(tinh|thanh pho|tp)\s+', '', clean_target).strip()
    all_cols = [c for c in gdf.columns if c.lower() != 'geometry']
    
    prov_keywords = ['ten_tinh', 'tentinh', 'tinh_tp', 'tinh', 'province', 'adm1', 'name_1', 'city', 'pro_name']
    forbidden = ['xa', 'phuong', 'comm', 'adm3', 'name_3', 'huyen', 'quan', 'dist', 'adm2', 'name_2', 'ma_', 'code', 'id', 'stt']
    
    cand_cols = [c for c in all_cols if any(k in c.lower() for k in prov_keywords) and not any(fb in c.lower() for fb in forbidden)]
    
    for c in cand_cols:
        vals = gdf[c].dropna().astype(str).tolist()
        cleaned = [re.sub(r'^(tinh|thanh pho|tp)\s+', '', remove_accents(v)).strip() for v in vals]
        if any(core_target == cv for cv in cleaned):
            return c

    for c in cand_cols:
        vals = gdf[c].dropna().astype(str).tolist()
        cleaned = [remove_accents(v) for v in vals]
        if any(core_target in cv for cv in cleaned):
            return c

    return cand_cols[0] if cand_cols else None

def find_commune_column(gdf):
    all_cols = [c for c in gdf.columns if c.lower() != 'geometry']
    comm_keywords = ['ten_xa', 'tenxa', 'xa', 'phuong', 'comm', 'adm3', 'name_3', 'com_name']
    forbidden = ['ma_', 'code', 'id', 'stt', 'tinh', 'prov', 'huyen', 'dist']
    
    cand_cols = [c for c in all_cols if any(k in c.lower() for k in comm_keywords) and not any(fb in c.lower() for fb in forbidden)]
    for c in cand_cols:
        sample = gdf[c].dropna().astype(str).head(60).tolist()
        if not sample: continue
        has_letters = sum(bool(re.search(r'[a-zA-Zà-ỹÀ-Ỹ]', v)) for v in sample)
        is_num = sum(v.strip().replace('.','',1).isdigit() for v in sample)
        if has_letters > is_num:
            return c
    return cand_cols[0] if cand_cols else None

def find_feature_name_col(gdf, candidate_keys):
    if gdf is None or gdf.empty:
        return None
    cols = [c for c in gdf.columns if c.lower() != 'geometry']
    for kw in candidate_keys:
        for c in cols:
            if c.lower() == kw.lower():
                return c
    for kw in candidate_keys:
        for c in cols:
            if kw.lower() in c.lower() and not any(bad in c.lower() for bad in ['ma_', 'id', 'gid', 'code', 'stt', 'fid', 'cap']):
                return c
    return None

def get_line_label_pt_and_angle(line, is_projected=True):
    mid_dist = line.length * 0.5
    pt = line.interpolate(mid_dist)
    delta = min(line.length * 0.05, 1000.0 if is_projected else 0.01)
    if delta <= 0:
        return pt.x, pt.y, 0.0
        
    pt_before = line.interpolate(max(0.0, mid_dist - delta))
    pt_after = line.interpolate(min(line.length, mid_dist + delta))
    
    dx = pt_after.x - pt_before.x
    dy = pt_after.y - pt_before.y
    
    if not is_projected:
        lat_rad = math.radians(pt.y)
        dx *= math.cos(lat_rad)
        
    if dx == 0 and dy == 0:
        angle = 0.0
    else:
        angle = float(np.degrees(np.arctan2(dy, dx)))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
            
    return pt.x, pt.y, angle

def load_feature_layer_safe(shp_path, target_crs, canvas_box):
    if not shp_path or not os.path.exists(shp_path):
        return None
    try:
        gdf = None
        for enc in [None, 'utf-8', 'cp1258', 'latin1']:
            try:
                gdf = gpd.read_file(shp_path, encoding=enc) if enc else gpd.read_file(shp_path)
                if gdf is not None and not gdf.empty:
                    break
            except Exception:
                continue

        if gdf is None or gdf.empty:
            return None

        bounds = gdf.total_bounds
        is_meters = (bounds[0] > 180 or bounds[2] > 180 or bounds[1] > 90)

        if is_meters:
            if bounds[0] > 900000 and bounds[1] < 900000:
                gdf['geometry'] = gdf['geometry'].apply(lambda g: shapely.ops.transform(lambda x, y: (y, x), g))
            if gdf.crs is None or gdf.crs.is_geographic:
                gdf.set_crs("EPSG:3405", allow_override=True)
        else:
            if gdf.crs is None or not gdf.crs.is_geographic:
                gdf.set_crs("EPSG:4326", allow_override=True)

        gdf = gdf.to_crs(target_crs)
        gdf['geometry'] = gdf['geometry'].make_valid()
        gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty]

        search_box = canvas_box.buffer(50.0 if is_meters else 0.005)
        gdf_filtered = gdf[gdf.geometry.intersects(search_box)].copy()
        
        return gdf_filtered if not gdf_filtered.empty else None
    except Exception as e:
        print(f"Lỗi nạp file {shp_path}: {e}")
        return None

def fetch_osm_online(south, west, north, east, query_tag):
    query = f"""
    [out:json][timeout:35];
    (
      way{query_tag}({south},{west},{north},{east});
    );
    out geom;
    """
    servers = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]
    headers = {'User-Agent': 'Vietnam_Atlas_Pro_GIS/41.0 (contact: hydro@project.vn)'}
    for srv in servers:
        try:
            req = urllib.request.Request(srv, data=query.encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                lines = []
                for el in data.get('elements', []):
                    if 'geometry' in el and len(el['geometry']) >= 2:
                        coords = [(pt['lon'], pt['lat']) for pt in el['geometry']]
                        lines.append(LineString(coords))
                if lines:
                    return gpd.GeoDataFrame({'geometry': lines}, crs="EPSG:4326")
        except Exception:
            continue
    return None

# =========================================================================
# HOA GIÓ LA BÀN NHỎ GỌN, MÀU ĐEN (COMPASS ROSE COMPACT BLACK)
# =========================================================================
class DraggableNorthArrow:
    def __init__(self, ax, x, y, dx, dy):
        self.ax = ax
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.scale = 1.0
        self.angle = 0.0
        
        self.r = 0.015 * max(dx, dy)
        
        self.n_dark = Polygon([[self.x, self.y + self.r * 1.3], [self.x, self.y], [self.x - self.r * 0.2, self.y]], closed=True, facecolor='#0f172a', edgecolor='#0f172a', zorder=12)
        self.n_light = Polygon([[self.x, self.y + self.r * 1.3], [self.x, self.y], [self.x + self.r * 0.2, self.y]], closed=True, facecolor='#cbd5e1', edgecolor='#0f172a', zorder=12)
        
        self.s_dark = Polygon([[self.x, self.y - self.r * 1.3], [self.x, self.y], [self.x + self.r * 0.2, self.y]], closed=True, facecolor='#0f172a', edgecolor='#0f172a', zorder=12)
        self.s_light = Polygon([[self.x, self.y - self.r * 1.3], [self.x, self.y], [self.x - self.r * 0.2, self.y]], closed=True, facecolor='#cbd5e1', edgecolor='#0f172a', zorder=12)
        
        self.e_dark = Polygon([[self.x + self.r * 1.3, self.y], [self.x, self.y], [self.x, self.y + self.r * 0.2]], closed=True, facecolor='#cbd5e1', edgecolor='#0f172a', zorder=12)
        self.e_light = Polygon([[self.x + self.r * 1.3, self.y], [self.x, self.y], [self.x, self.y - self.r * 0.2]], closed=True, facecolor='#0f172a', edgecolor='#0f172a', zorder=12)
        
        self.w_dark = Polygon([[self.x - self.r * 1.3, self.y], [self.x, self.y], [self.x, self.y - self.r * 0.2]], closed=True, facecolor='#cbd5e1', edgecolor='#0f172a', zorder=12)
        self.w_light = Polygon([[self.x - self.r * 1.3, self.y], [self.x, self.y], [self.x, self.y + self.r * 0.2]], closed=True, facecolor='#0f172a', edgecolor='#0f172a', zorder=12)

        self.patches = [self.n_dark, self.n_light, self.s_dark, self.s_light, self.e_dark, self.e_light, self.w_dark, self.w_light]
        for p in self.patches:
            ax.add_patch(p)

        self.txt_n = ax.text(self.x, self.y + self.r * 1.55, 'N', ha='center', va='bottom', fontsize=10, fontweight='bold', fontfamily='serif', color='#0f172a', zorder=13)
        self.txt_s = ax.text(self.x, self.y - self.r * 1.55, 'S', ha='center', va='top', fontsize=10, fontweight='bold', fontfamily='serif', color='#0f172a', zorder=13)
        self.txt_e = ax.text(self.x + self.r * 1.55, self.y, 'E', ha='left', va='center', fontsize=10, fontweight='bold', fontfamily='serif', color='#0f172a', zorder=13)
        self.txt_w = ax.text(self.x - self.r * 1.55, self.y, 'W', ha='right', va='center', fontsize=10, fontweight='bold', fontfamily='serif', color='#0f172a', zorder=13)

    def get_position(self):
        return (self.x, self.y)

    def set_position(self, pos):
        self.x, self.y = pos
        self._update_geometry()

    def _update_geometry(self):
        r = self.r * self.scale
        pts_def = [
            ([[0, r * 1.3], [0, 0], [-r * 0.2, 0]]),
            ([[0, r * 1.3], [0, 0], [r * 0.2, 0]]),
            ([[0, -r * 1.3], [0, 0], [r * 0.2, 0]]),
            ([[0, -r * 1.3], [0, 0], [-r * 0.2, 0]]),
            ([[r * 1.3, 0], [0, 0], [0, r * 0.2]]),
            ([[r * 1.3, 0], [0, 0], [0, -r * 0.2]]),
            ([[-r * 1.3, 0], [0, 0], [0, -r * 0.2]]),
            ([[-r * 1.3, 0], [0, 0], [0, r * 0.2]])
        ]

        rad = math.radians(-self.angle) if self.angle != 0 else 0.0
        c, s = math.cos(rad), math.sin(rad)
        R = np.array([[c, -s], [s, c]]) if self.angle != 0 else None

        for patch, coords in zip(self.patches, pts_def):
            arr = np.array(coords)
            if R is not None:
                arr = arr @ R.T
            arr += np.array([self.x, self.y])
            patch.set_xy(arr)

        offsets = {
            self.txt_n: np.array([0.0, r * 1.55]),
            self.txt_s: np.array([0.0, -r * 1.55]),
            self.txt_e: np.array([r * 1.55, 0.0]),
            self.txt_w: np.array([-r * 1.55, 0.0])
        }
        for txt, off in offsets.items():
            if R is not None:
                off = off @ R.T
            txt.set_position((self.x + off[0], self.y + off[1]))
            txt.set_rotation(self.angle)

    def get_text(self):
        return "Compass Rose (N, S, E, W)"

    def set_text(self, text):
        pass

    def get_rotation(self):
        return self.angle

    def set_rotation(self, angle):
        self.angle = angle
        self._update_geometry()

    def get_fontsize(self):
        return self.txt_n.get_fontsize()

    def set_fontsize(self, size):
        self.scale = max(0.4, size / 10.0)
        sz = max(7, int(size))
        for t in [self.txt_n, self.txt_s, self.txt_e, self.txt_w]:
            t.set_fontsize(sz)
        self._update_geometry()

    def set_color(self, color):
        for t in [self.txt_n, self.txt_s, self.txt_e, self.txt_w]:
            t.set_color(color)

    def get_window_extent(self, renderer):
        bboxes = [p.get_window_extent(renderer) for p in self.patches] + [t.get_window_extent(renderer) for t in [self.txt_n, self.txt_s, self.txt_e, self.txt_w]]
        from matplotlib.transforms import Bbox
        return Bbox.union(bboxes)

# =========================================================================
# LỚP ĐỐI TƯỢNG THƯỚC TỶ LỆ TƯƠNG TÁC
# =========================================================================
class DraggableScaleBar:
    def __init__(self, ax, sx, sy, dx, dy, half_len, bar_len, half_km, bar_total_km):
        self.ax = ax
        self.x = sx
        self.y = sy
        self.dx = dx
        self.dy = dy
        self.half_len = half_len
        self.bar_len = bar_len
        self.half_km = half_km
        self.bar_total_km = bar_total_km
        self.bar_h = 0.009 * dy
        
        self.rect1 = mpatches.Rectangle((self.x, self.y), half_len, self.bar_h, facecolor='#0f172a', edgecolor='#0f172a', zorder=10)
        self.rect2 = mpatches.Rectangle((self.x + half_len, self.y), half_len, self.bar_h, facecolor='white', edgecolor='#0f172a', zorder=10)
        ax.add_patch(self.rect1)
        ax.add_patch(self.rect2)
        
        lbl_y = self.y + self.bar_h * 1.5
        self.t0 = ax.text(self.x, lbl_y, '0', ha='center', va='bottom', fontsize=8, fontfamily='serif', fontweight='bold', color='#0f172a', zorder=10)
        self.t1 = ax.text(self.x + half_len, lbl_y, f'{int(half_km)}', ha='center', va='bottom', fontsize=8, fontfamily='serif', fontweight='bold', color='#0f172a', zorder=10)
        self.t2 = ax.text(self.x + bar_len, lbl_y, f'{int(bar_total_km)} km', ha='center', va='bottom', fontsize=8, fontfamily='serif', fontweight='bold', color='#0f172a', zorder=10)

    def get_position(self):
        return (self.x, self.y)

    def set_position(self, pos):
        self.x, self.y = pos
        self.rect1.set_xy((self.x, self.y))
        self.rect2.set_xy((self.x + self.half_len, self.y))
        lbl_y = self.y + self.bar_h * 1.5
        self.t0.set_position((self.x, lbl_y))
        self.t1.set_position((self.x + self.half_len, lbl_y))
        self.t2.set_position((self.x + self.bar_len, lbl_y))

    def get_text(self):
        return f"{int(self.bar_total_km)} km"

    def set_text(self, text):
        self.t2.set_text(text)

    def get_rotation(self):
        return 0.0

    def set_rotation(self, angle):
        pass

    def get_fontsize(self):
        return self.t0.get_fontsize()

    def set_fontsize(self, size):
        self.t0.set_fontsize(size)
        self.t1.set_fontsize(size)
        self.t2.set_fontsize(size)

    def set_color(self, color):
        self.rect1.set_facecolor(color)
        self.rect1.set_edgecolor(color)
        self.rect2.set_edgecolor(color)
        self.t0.set_color(color)
        self.t1.set_color(color)
        self.t2.set_color(color)

    def get_window_extent(self, renderer):
        bbox1 = self.rect1.get_window_extent(renderer)
        bbox2 = self.rect2.get_window_extent(renderer)
        bbox3 = self.t0.get_window_extent(renderer)
        bbox4 = self.t1.get_window_extent(renderer)
        bbox5 = self.t2.get_window_extent(renderer)
        from matplotlib.transforms import Bbox
        return Bbox.union([bbox1, bbox2, bbox3, bbox4, bbox5])

# =========================================================================
# CỬA SỔ BIÊN TẬP TƯƠNG TÁC (ĐẢM BẢO LUÔN HIỂN THỊ ĐỦ BẢNG CHỈNH SỬA)
# =========================================================================
class MapEditorWindow(tk.Toplevel):
    def __init__(self, parent, fig, ax, default_out_file, editable_texts, dem_artist, legend_obj):
        super().__init__(parent)
        self.title("BỘ BIÊN TẬP VÀ XEM TRƯỚC BẢN ĐỒ (INTERACTIVE MAP EDITOR)")
        self.geometry("1380x880")
        self.state('zoomed')

        self.fig = fig
        self.ax = ax
        self.out_file = default_out_file
        self.editable_texts = editable_texts
        self.dem_artist = dem_artist
        self.legend_obj = legend_obj

        self.selected_item_name = None
        self.selected_artist = None
        self.dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.custom_text_counter = 0

        self.show_dem_var = tk.BooleanVar(value=(dem_artist is not None))
        self.show_commune_labels_var = tk.BooleanVar(value=True)
        self.show_river_labels_var = tk.BooleanVar(value=True)
        self.show_road_labels_var = tk.BooleanVar(value=True)
        self.batch_target_var = tk.StringVar(value="Xã / Phường trong tỉnh")

        self.setup_ui()
        self.setup_events()

    def setup_ui(self):
        # QUAN TRỌNG: Gắn thanh công cụ bên phải TRƯỚC TIÊN (để không bị bản đồ chiếm chỗ)
        panel = ttk.Frame(self, padding="10", width=360)
        panel.pack(side=tk.RIGHT, fill=tk.Y, expand=False)
        panel.pack_propagate(False)

        # Gắn khung bản đồ thứ hai (chiếm toàn bộ phần không gian còn lại bên trái)
        map_frame = ttk.Frame(self)
        map_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=map_frame)
        self.canvas.draw()

        toolbar = NavigationToolbar2Tk(self.canvas, map_frame)
        toolbar.update()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # XÂY DỰNG NỘI DUNG BẢNG ĐIỀU KHIỂN BÊN PHẢI
        ttk.Label(panel, text="BẢNG CHỈNH SỬA TƯƠNG TÁC", font=("Arial", 11, "bold"), foreground="#0f172a").pack(anchor="w", pady=(0, 4))

        # 1. BẬT TẮT LỚP
        toggle_box = ttk.LabelFrame(panel, text="1. Bật / Tắt Lớp Hiển Thị", padding=5)
        toggle_box.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Checkbutton(toggle_box, text="Hiển thị bóng đổ địa hình DEM", variable=self.show_dem_var, command=self.toggle_dem).pack(anchor="w")
        ttk.Checkbutton(toggle_box, text="Hiển thị tên Xã / Phường", variable=self.show_commune_labels_var, command=self.toggle_commune_labels).pack(anchor="w", pady=(1, 0))
        ttk.Checkbutton(toggle_box, text="Hiển thị tên Sông ngòi & Hồ", variable=self.show_river_labels_var, command=self.toggle_river_labels).pack(anchor="w", pady=(1, 0))
        ttk.Checkbutton(toggle_box, text="Hiển thị tên Tuyến đường (Quốc lộ)", variable=self.show_road_labels_var, command=self.toggle_road_labels).pack(anchor="w", pady=(1, 0))

        # 2. CHÈN THÊM CHỮ MỚI
        add_box = ttk.LabelFrame(panel, text="2. Chèn Thêm Chữ Mới (Custom Text)", padding=5)
        add_box.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(add_box, text="Nội dung chữ cần chèn:").pack(anchor="w")
        self.ent_new_text = ttk.Entry(add_box, font=("Arial", 9))
        self.ent_new_text.pack(fill=tk.X, pady=(2, 3))
        self.ent_new_text.bind("<Return>", lambda e: self.add_custom_text())

        btn_add_row = ttk.Frame(add_box)
        btn_add_row.pack(fill=tk.X, pady=(1, 1))
        ttk.Button(btn_add_row, text="➕ Thêm chữ", command=self.add_custom_text).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(btn_add_row, text="🗑️️ Xóa chữ chọn", command=self.delete_selected_text).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # 3. CHỈNH SỬA ĐỐI TƯỢNG ĐANG CHỌN
        text_box = ttk.LabelFrame(panel, text="3. Chỉnh sửa đối tượng đang chọn", padding=5)
        text_box.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(text_box, text="Đối tượng đang chọn:", font=("Arial", 8, "bold")).pack(anchor="w")
        self.cbo_items = ttk.Combobox(text_box, values=list(self.editable_texts.keys()), state="readonly")
        self.cbo_items.pack(fill=tk.X, pady=(1, 3))
        self.cbo_items.bind("<<ComboboxSelected>>", self.on_combo_select)

        ttk.Label(text_box, text="Nội dung chữ:").pack(anchor="w")
        self.ent_text = ttk.Entry(text_box, font=("Arial", 9))
        self.ent_text.pack(fill=tk.X, pady=(1, 3))
        self.ent_text.bind("<KeyRelease>", self.on_text_change)

        rot_row = ttk.Frame(text_box)
        rot_row.pack(fill=tk.X, pady=(1, 1))
        ttk.Label(rot_row, text="Góc xoay:").pack(side=tk.LEFT)
        self.lbl_angle = ttk.Label(rot_row, text="0.0°", foreground="blue")
        self.lbl_angle.pack(side=tk.LEFT, padx=(5, 0))
        
        self.scale_angle = ttk.Scale(text_box, from_=-90, to=90, orient=tk.HORIZONTAL, command=self.on_angle_change)
        self.scale_angle.pack(fill=tk.X, pady=(1, 3))

        btn_rot = ttk.Frame(text_box)
        btn_rot.pack(fill=tk.X, pady=(0, 3))
        ttk.Button(btn_rot, text="-10°", width=6, command=lambda: self.step_angle(-10)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(btn_rot, text="Ngang 0°", width=8, command=lambda: self.step_angle(0, reset=True)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(btn_rot, text="+10°", width=6, command=lambda: self.step_angle(10)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        ttk.Label(text_box, text="Cỡ chữ & Màu sắc:").pack(anchor="w")
        size_row = ttk.Frame(text_box)
        size_row.pack(fill=tk.X, pady=(1, 1))
        self.spn_size = ttk.Spinbox(size_row, from_=4.0, to=64.0, increment=0.5, width=5, command=self.on_size_change)
        self.spn_size.pack(side=tk.LEFT, padx=(0, 2))
        self.spn_size.bind("<KeyRelease>", lambda e: self.on_size_change())
        ttk.Button(size_row, text="[-1]", width=4, command=lambda: self.step_size(-1.0)).pack(side=tk.LEFT, padx=1)
        ttk.Button(size_row, text="[+1]", width=4, command=lambda: self.step_size(1.0)).pack(side=tk.LEFT, padx=1)
        ttk.Button(size_row, text="🎨 Màu", command=self.change_selected_color).pack(side=tk.LEFT, padx=(3, 0), expand=True, fill=tk.X)

        # 4. ĐỊNH DẠNG CẢ LỚP CHỮ
        batch_box = ttk.LabelFrame(panel, text="4. Định dạng cả lớp chữ (Batch)", padding=5)
        batch_box.pack(fill=tk.X, pady=(0, 4))

        self.cbo_batch_layer = ttk.Combobox(
            batch_box, textvariable=self.batch_target_var, state="readonly",
            values=["Xã / Phường trong tỉnh", "Tên Sông ngòi", "Tên Tuyến đường", "Tỉnh lân cận", "Quốc gia & Vùng biển", "Chữ tự chèn", "Tất cả chữ trên bản đồ"]
        )
        self.cbo_batch_layer.pack(fill=tk.X, pady=(1, 3))

        b_size_row = ttk.Frame(batch_box)
        b_size_row.pack(fill=tk.X, pady=(1, 3))
        self.spn_batch_size = ttk.Spinbox(b_size_row, from_=4.0, to=36.0, increment=0.5, width=6)
        self.spn_batch_size.set("7.0")
        self.spn_batch_size.pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(b_size_row, text="Áp dụng", command=self.apply_batch_size).pack(side=tk.LEFT, padx=1)
        ttk.Button(b_size_row, text="[-1]", width=4, command=lambda: self.step_batch_size(-1.0)).pack(side=tk.LEFT, padx=1)
        ttk.Button(b_size_row, text="[+1]", width=4, command=lambda: self.step_batch_size(1.0)).pack(side=tk.LEFT, padx=1)

        b_btn_row = ttk.Frame(batch_box)
        b_btn_row.pack(fill=tk.X, pady=(1, 1))
        ttk.Button(b_btn_row, text="🎨 Đổi màu lớp", command=self.apply_batch_color).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(b_btn_row, text="Ngang 0° lớp", command=self.apply_batch_rotation_zero).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # 5. HƯỚNG DẪN
        note_box = ttk.LabelFrame(panel, text="5. Hướng dẫn tương tác", padding=5)
        note_box.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(note_box, text="• Giữ chuột trái vào bất kỳ CHỮ, LA BÀN hoặc\n  THƯỚC ĐO trên bản đồ để KÉO THẢ.",
                  foreground="#475569", font=("Arial", 8)).pack(anchor="w")

        # NÚT XUẤT BẢN ĐỒ HOÀN THIỆN (GẮN CỐ ĐỊNH Ở ĐÁY THANH CÔNG CỤ)
        self.btn_save = ttk.Button(panel, text="💾 XUẤT BẢN ĐỒ HOÀN THIỆN (300 DPI) 💾", command=self.export_map)
        self.btn_save.pack(fill=tk.X, ipady=6, side=tk.BOTTOM, pady=(4, 0))

    def setup_events(self):
        self.canvas.mpl_connect('button_press_event', self.on_mouse_press)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_motion)
        self.canvas.mpl_connect('button_release_event', self.on_mouse_release)

    def add_custom_text(self):
        txt = self.ent_new_text.get().strip()
        if not txt:
            messagebox.showwarning("Thông báo", "Vui lòng nhập nội dung chữ cần chèn!")
            return

        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        cx = (xlim[0] + xlim[1]) / 2.0
        cy = (ylim[0] + ylim[1]) / 2.0

        self.custom_text_counter += 1
        item_key = f"[Chữ riêng {self.custom_text_counter}] {txt}"

        artist = self.ax.text(
            cx, cy, txt,
            ha='center', va='center', rotation=0.0,
            fontsize=11.0, fontweight='bold', fontfamily='serif',
            color='#b91c1c', zorder=12, clip_on=True,
            path_effects=[pe.withStroke(linewidth=2.8, foreground="white")]
        )

        self.editable_texts[item_key] = artist
        self.cbo_items['values'] = list(self.editable_texts.keys())
        self.select_artist(item_key, artist)
        self.ent_new_text.delete(0, tk.END)
        self.canvas.draw_idle()

    def delete_selected_text(self):
        if not self.selected_item_name or not self.selected_artist:
            messagebox.showinfo("Thông báo", "Vui lòng chọn chữ trên bản đồ hoặc chọn từ danh sách trước khi xóa!")
            return

        protected_keys = ["[Tiêu đề] Bản đồ", "[La bàn] Kim chỉ hướng Bắc", "[Thước đo] Thước tỷ lệ"]
        if self.selected_item_name in protected_keys:
            messagebox.showwarning("Cảnh báo", "Không thể xóa đối tượng hệ thống này!")
            return

        if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc muốn xóa đối tượng chữ:\n\n{self.selected_item_name}?"):
            try:
                self.selected_artist.remove()
            except Exception:
                self.selected_artist.set_visible(False)

            if self.selected_item_name in self.editable_texts:
                del self.editable_texts[self.selected_item_name]

            self.cbo_items['values'] = list(self.editable_texts.keys())
            self.selected_item_name = None
            self.selected_artist = None
            self.cbo_items.set('')
            self.ent_text.delete(0, tk.END)
            self.canvas.draw_idle()

    def change_selected_color(self):
        if not self.selected_artist:
            messagebox.showinfo("Thông báo", "Vui lòng chọn đối tượng cần đổi màu trước!")
            return
        color = colorchooser.askcolor(title="Chọn màu chữ")[1]
        if color:
            self.selected_artist.set_color(color)
            self.canvas.draw_idle()

    def toggle_dem(self):
        if self.dem_artist is not None:
            self.dem_artist.set_visible(self.show_dem_var.get())
            self.canvas.draw_idle()

    def toggle_commune_labels(self):
        v = self.show_commune_labels_var.get()
        for name, item in self.editable_texts.items():
            if name.startswith("Xã/Phường:") or name.startswith("Địa danh:"):
                item.set_visible(v)
        self.canvas.draw_idle()

    def toggle_river_labels(self):
        v = self.show_river_labels_var.get()
        for name, item in self.editable_texts.items():
            if name.startswith("Sông:") or name.startswith("Hồ:"):
                item.set_visible(v)
        self.canvas.draw_idle()

    def toggle_road_labels(self):
        v = self.show_road_labels_var.get()
        for name, item in self.editable_texts.items():
            if name.startswith("Đường:"):
                item.set_visible(v)
        self.canvas.draw_idle()

    def matches_batch_layer(self, name, target):
        if target == "Xã / Phường trong tỉnh":
            return name.startswith("Xã/Phường:") or name.startswith("Địa danh:")
        elif target == "Tên Sông ngòi":
            return name.startswith("Sông:") or name.startswith("Hồ:")
        elif target == "Tên Tuyến đường":
            return name.startswith("Đường:")
        elif target == "Tỉnh lân cận":
            return any(name.startswith(p) for p in ["Tỉnh:", "Tỉnh lân cận:"])
        elif target == "Quốc gia & Vùng biển":
            return any(name.startswith(p) for p in ["[Quốc gia]", "[Vùng biển]"])
        elif target == "Chữ tự chèn":
            return name.startswith("[Chữ riêng")
        elif target == "Tất cả chữ trên bản đồ":
            return True
        return False

    def apply_batch_size(self):
        try:
            sz = float(self.spn_batch_size.get())
            target = self.batch_target_var.get()
            for name, item in self.editable_texts.items():
                if self.matches_batch_layer(name, target):
                    item.set_fontsize(sz)
            self.canvas.draw_idle()
        except ValueError:
            pass

    def step_batch_size(self, delta):
        try:
            cur = float(self.spn_batch_size.get())
            new_sz = max(4.0, min(48.0, cur + delta))
            self.spn_batch_size.delete(0, tk.END)
            self.spn_batch_size.insert(0, str(new_sz))
            self.apply_batch_size()
        except ValueError:
            pass

    def apply_batch_color(self):
        color = colorchooser.askcolor(title="Chọn màu chữ cho cả lớp")[1]
        if not color: return
        target = self.batch_target_var.get()
        for name, item in self.editable_texts.items():
            if self.matches_batch_layer(name, target):
                item.set_color(color)
        self.canvas.draw_idle()

    def apply_batch_rotation_zero(self):
        target = self.batch_target_var.get()
        for name, item in self.editable_texts.items():
            if self.matches_batch_layer(name, target):
                item.set_rotation(0.0)
        self.canvas.draw_idle()

    def select_artist(self, name, artist):
        self.selected_item_name = name
        self.selected_artist = artist
        self.cbo_items.set(name)

        cur_text = artist.get_text()
        self.ent_text.delete(0, tk.END)
        self.ent_text.insert(0, cur_text)

        cur_rot = artist.get_rotation()
        if cur_rot > 180: cur_rot -= 360
        self.scale_angle.set(cur_rot)
        self.lbl_angle.config(text=f"{cur_rot:.1f}°")

        cur_size = artist.get_fontsize()
        self.spn_size.delete(0, tk.END)
        self.spn_size.insert(0, str(cur_size))

    def on_combo_select(self, event):
        name = self.cbo_items.get()
        if name in self.editable_texts:
            self.select_artist(name, self.editable_texts[name])

    def on_mouse_press(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return

        renderer = self.canvas.get_renderer()
        clicked_item = None
        clicked_name = None

        for name, item in self.editable_texts.items():
            try:
                bbox = item.get_window_extent(renderer=renderer)
                if bbox.expanded(1.2, 1.2).contains(event.x, event.y):
                    clicked_item = item
                    clicked_name = name
                    break
            except Exception:
                continue

        if clicked_item:
            self.select_artist(clicked_name, clicked_item)
            if not clicked_name.startswith("[Chú giải]"):
                self.dragging = True
                pos = clicked_item.get_position()
                self.drag_offset_x = pos[0] - event.xdata
                self.drag_offset_y = pos[1] - event.ydata

    def on_mouse_motion(self, event):
        if not self.dragging or not self.selected_artist or event.inaxes != self.ax:
            return

        new_x = event.xdata + self.drag_offset_x
        new_y = event.ydata + self.drag_offset_y
        self.selected_artist.set_position((new_x, new_y))
        self.canvas.draw_idle()

    def on_mouse_release(self, event):
        self.dragging = False

    def on_text_change(self, event=None):
        if self.selected_artist:
            self.selected_artist.set_text(self.ent_text.get())
            self.canvas.draw_idle()

    def on_angle_change(self, val):
        if self.selected_artist:
            angle = float(val)
            self.selected_artist.set_rotation(angle)
            self.lbl_angle.config(text=f"{angle:.1f}°")
            self.canvas.draw_idle()

    def step_angle(self, delta, reset=False):
        if self.selected_artist:
            new_angle = 0.0 if reset else (self.selected_artist.get_rotation() + delta)
            if new_angle > 180: new_angle -= 360
            elif new_angle < -180: new_angle += 360
            self.scale_angle.set(new_angle)
            self.on_angle_change(new_angle)

    def on_size_change(self):
        if self.selected_artist:
            try:
                sz = float(self.spn_size.get())
                self.selected_artist.set_fontsize(sz)
                self.canvas.draw_idle()
            except ValueError:
                pass

    def step_size(self, delta):
        if self.selected_artist:
            try:
                cur = float(self.spn_size.get())
                new_sz = max(4.0, min(64.0, cur + delta))
                self.spn_size.delete(0, tk.END)
                self.spn_size.insert(0, str(new_sz))
                self.on_size_change()
            except ValueError:
                pass

    def export_map(self):
        f = filedialog.asksaveasfilename(
            title="Lưu bản đồ hoàn thiện",
            initialfile=os.path.basename(self.out_file),
            defaultextension=".png",
            filetypes=[("Ảnh PNG độ nét cao (300 DPI)", "*.png"), ("Tài liệu PDF Vector", "*.pdf")]
        )
        if f:
            try:
                self.fig.savefig(f, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Thành công", f"Đã xuất bản đồ hoàn chỉnh thành công!\nFile lưu tại:\n{f}")
            except Exception as e:
                messagebox.showerror("Lỗi khi lưu", str(e))

# =========================================================================
# GIAO DIỆN CHÍNH
# =========================================================================
class MainMapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Phần Mềm Lập Bản Đồ Hành Chính")
        self.root.geometry("820x810")
        self.root.resizable(False, False)

        base_dir = r"D:\Phanmem_TTthuyvan\XDungBando"
        
        self.shp_communes = tk.StringVar(value=os.path.join(base_dir, "VietNam_phuong-xa.shp"))
        self.shp_provinces = tk.StringVar(value=os.path.join(base_dir, "VietNam-34Tinh.shp"))
        self.shp_roads = tk.StringVar(value=os.path.join(base_dir, "GIAOTHONG.shp"))
        self.shp_rivers = tk.StringVar(value=os.path.join(base_dir, "Song_VN.shp"))
        self.shp_lakes = tk.StringVar(value="")
        self.dem_path = tk.StringVar(value=os.path.join(base_dir, "VietNam_DEM_SRTMGL1_30m_v3_USGS.tiff"))

        self.province_name = tk.StringVar(value="Hồ Chí Minh")
        
        self.use_dem = tk.BooleanVar(value=True)
        self.crs_choice = tk.StringVar(value="WGS84 - Độ thập phân (EPSG:4326)")
        self.show_grid = tk.BooleanVar(value=True)
        self.grid_style = tk.StringVar(value="Nét chấm (:)")
        self.grid_interval = tk.StringVar(value="Tự động tối ưu")
        self.zoom_margin = tk.DoubleVar(value=4.5)

        self.output_image = tk.StringVar(value=os.path.abspath("Ban_Do_Hanh_Chinh_Atlas_Chuan.png"))

        self.setup_ui()

    def setup_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # TAB 1: DỮ LIỆU
        tab_main = ttk.Frame(notebook, padding="15")
        notebook.add(tab_main, text="1. Nguồn Dữ Liệu & Hệ Tọa Độ (CRS)")

        ttk.Label(tab_main, text="Đường dẫn các lớp dữ liệu Shapefile (Ưu tiên nạp Offline):", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5), columnspan=3)
        
        ttk.Label(tab_main, text="Ranh giới Xã / Phường (VietNam_phuong-xa.shp):").grid(row=1, column=0, sticky="w")
        ttk.Entry(tab_main, textvariable=self.shp_communes, width=50).grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(tab_main, text="Duyệt Xã...", command=lambda: self.browse_file(self.shp_communes, "*.shp")).grid(row=1, column=2)

        ttk.Label(tab_main, text="Ranh giới Tỉnh / Thành (VietNam-34Tinh.shp):").grid(row=2, column=0, sticky="w")
        ttk.Entry(tab_main, textvariable=self.shp_provinces, width=50).grid(row=2, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(tab_main, text="Duyệt Tỉnh...", command=lambda: self.browse_file(self.shp_provinces, "*.shp")).grid(row=2, column=2)

        ttk.Label(tab_main, text="Mạng lưới đường bộ (GIAOTHONG.shp):").grid(row=3, column=0, sticky="w")
        ttk.Entry(tab_main, textvariable=self.shp_roads, width=50).grid(row=3, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(tab_main, text="Duyệt Đường...", command=lambda: self.browse_file(self.shp_roads, "*.shp")).grid(row=3, column=2)

        ttk.Label(tab_main, text="Mạng lưới sông ngòi (Songhotoanquoc_26.shp):").grid(row=4, column=0, sticky="w")
        ttk.Entry(tab_main, textvariable=self.shp_rivers, width=50).grid(row=4, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(tab_main, text="Duyệt Sông...", command=lambda: self.browse_file(self.shp_rivers, "*.shp")).grid(row=4, column=2)

        ttk.Label(tab_main, text="Hồ chứa / Vực nước phụ (.shp, tùy chọn):").grid(row=5, column=0, sticky="w")
        ttk.Entry(tab_main, textvariable=self.shp_lakes, width=50).grid(row=5, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(tab_main, text="Duyệt Hồ...", command=lambda: self.browse_file(self.shp_lakes, "*.shp")).grid(row=5, column=2)

        ttk.Label(tab_main, text="Mô hình địa hình số DEM (.tif):").grid(row=6, column=0, sticky="w")
        ttk.Entry(tab_main, textvariable=self.dem_path, width=50).grid(row=6, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(tab_main, text="Duyệt DEM...", command=lambda: self.browse_file(self.dem_path, "*.tif;*.tiff")).grid(row=6, column=2)

        ttk.Checkbutton(tab_main, text="Kích hoạt đổ bóng DEM", variable=self.use_dem).grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 10))

        ttk.Separator(tab_main, orient=tk.HORIZONTAL).grid(row=8, column=0, columnspan=3, sticky="ew", pady=8)

        ttk.Label(tab_main, text="Cấu hình Tỉnh thành (34 Đơn vị Hành chính Mới):", font=("Arial", 10, "bold")).grid(row=9, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Label(tab_main, text="Tên Tỉnh / Thành phố:").grid(row=10, column=0, sticky="w")
        
        sorted_34_names = [v['name'] for v in sorted(PROVINCES_META_34.values(), key=lambda x: remove_accents(x['name']))]
        self.cbo_province = ttk.Combobox(tab_main, textvariable=self.province_name, width=32, font=("Arial", 10))
        self.cbo_province['values'] = sorted_34_names
        self.cbo_province.grid(row=10, column=1, sticky="w", padx=5)

        ttk.Label(tab_main, text="Hệ quy chiếu thực tế (CRS):").grid(row=11, column=0, sticky="w", pady=5)
        cbo_crs = ttk.Combobox(tab_main, textvariable=self.crs_choice, state="readonly", width=42)
        cbo_crs['values'] = list(CRS_DICT.keys())
        cbo_crs.grid(row=11, column=1, sticky="w", padx=5)

        # TAB 2: LƯỚI TỌA ĐỘ
        tab_grid = ttk.Frame(notebook, padding="15")
        notebook.add(tab_grid, text="2. Lưới Tọa Độ & Mức Độ Thu Phóng")

        ttk.Label(tab_grid, text="A. Cấu hình lưới tọa độ (Ghi đủ cả 4 cạnh: Dưới, Trên, Trái, Phải):", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Checkbutton(tab_grid, text="Hiển thị lưới tọa độ trên bản đồ", variable=self.show_grid).grid(row=1, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(tab_grid, text="Kiểu đường lưới:").grid(row=2, column=0, sticky="w", pady=4)
        cbo_style = ttk.Combobox(tab_grid, textvariable=self.grid_style, state="readonly", width=25)
        cbo_style['values'] = ("Nét chấm (:)", "Nét đứt (--)", "Nét mảnh liền (-)")
        cbo_style.grid(row=2, column=1, sticky="w", padx=5)

        ttk.Label(tab_grid, text="Bước nhảy lưới (Interval):").grid(row=3, column=0, sticky="w", pady=4)
        cbo_int = ttk.Combobox(tab_grid, textvariable=self.grid_interval, state="readonly", width=25)
        cbo_int['values'] = ("Tự động tối ưu", "Dày", "Vừa", "Thưa")
        cbo_int.grid(row=3, column=1, sticky="w", padx=5)

        ttk.Separator(tab_grid, orient=tk.HORIZONTAL).grid(row=4, column=0, columnspan=3, sticky="ew", pady=15)

        ttk.Label(tab_grid, text="B. Tùy chỉnh mức độ Zoom cận cảnh vào tỉnh chính:", font=("Arial", 10, "bold")).grid(row=5, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Label(tab_grid, text="Lề mở rộng quanh tỉnh (%):").grid(row=6, column=0, sticky="w")
        ttk.Scale(tab_grid, from_=1.0, to=15.0, variable=self.zoom_margin, orient=tk.HORIZONTAL, length=220).grid(row=6, column=1, sticky="w", padx=5)

        # PHẦN THỰC THI
        bottom_frame = ttk.Frame(self.root, padding="15")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Label(bottom_frame, text="Đường dẫn file lưu mặc định:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Entry(bottom_frame, textvariable=self.output_image, width=68).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Button(bottom_frame, text="Chọn...", command=self.browse_save).grid(row=1, column=1, padx=5)

        self.lbl_status = ttk.Label(bottom_frame, text="Trạng thái: Sẵn sàng kết xuất.", foreground="blue", font=("Arial", 9))
        self.lbl_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 5))

        self.btn_run = ttk.Button(bottom_frame, text="🚀 XUẤT BẢN ĐỒ (300 DPI) 🚀", command=self.start_process)
        self.btn_run.grid(row=3, column=0, columnspan=2, pady=5)

    def browse_file(self, str_var, pattern):
        f = filedialog.askopenfilename(title="Chọn file dữ liệu", filetypes=[("GIS Files", pattern), ("All Files", "*.*")])
        if f:
            str_var.set(os.path.normpath(f))
            if "*.tif" in pattern: self.use_dem.set(True)

    def browse_save(self):
        f = filedialog.asksaveasfilename(title="Lưu bản đồ", defaultextension=".png", filetypes=[("Ảnh PNG nét cao 300 DPI", "*.png")])
        if f: self.output_image.set(os.path.normpath(f))

    def update_status(self, text, color="blue"):
        self.root.after(0, lambda: self.lbl_status.config(text=f"Trạng thái: {text}", foreground=color))

    def start_process(self):
        prov = self.province_name.get().strip()
        out_f = self.output_image.get().strip()

        comm_path = self.shp_communes.get().strip()
        prov_path = self.shp_provinces.get().strip()

        if not os.path.exists(comm_path) and not os.path.exists(prov_path):
            messagebox.showerror("Thiếu file", "Không tìm thấy file ranh giới hành chính!")
            return

        self.btn_run.config(state=tk.DISABLED)
        threading.Thread(target=self.run_generation, args=(prov, out_f)).start()

    def run_generation(self, prov, out_f):
        try:
            target_crs = CRS_DICT[self.crs_choice.get()]
            is_projected = ("EPSG:4326" not in target_crs)

            prov_key = find_best_province_key(prov)
            prov_meta = PROVINCES_META_34[prov_key]

            self.update_status(f"Đang chuẩn bị không gian địa lý cho {prov_meta['name']}...", "orange")

            # 1. ĐỌC FILE XÃ / PHƯỜNG
            comm_path = self.shp_communes.get().strip()
            gdf_comm_raw = None
            if os.path.exists(comm_path):
                gdf_comm_raw = gpd.read_file(comm_path)
                if gdf_comm_raw.crs is None:
                    b = gdf_comm_raw.total_bounds
                    gdf_comm_raw.set_crs("EPSG:4326" if (b[0] > 90 and b[2] < 130) else "EPSG:3405", inplace=True)
                if gdf_comm_raw.crs.to_string() != "EPSG:4326":
                    gdf_comm_raw = gdf_comm_raw.to_crs("EPSG:4326")

            # 2. ĐỌC FILE TỈNH
            prov_path = self.shp_provinces.get().strip()
            gdf_prov_all_raw = None
            if os.path.exists(prov_path):
                gdf_prov_all_raw = gpd.read_file(prov_path)
                if gdf_prov_all_raw.crs is None:
                    b = gdf_prov_all_raw.total_bounds
                    gdf_prov_all_raw.set_crs("EPSG:4326" if (b[0] > 90 and b[2] < 130) else "EPSG:3405", inplace=True)
                if gdf_prov_all_raw.crs.to_string() != "EPSG:4326":
                    gdf_prov_all_raw = gdf_prov_all_raw.to_crs("EPSG:4326")

            # 3. LỌC ĐÚNG CÁC XÃ/PHƯỜNG THUỘC TỈNH
            gdf_prov_communes_wgs = None
            commune_name_col = None

            if gdf_comm_raw is not None and not gdf_comm_raw.empty:
                prov_col = find_province_column(gdf_comm_raw, prov_key)
                comm_col = find_commune_column(gdf_comm_raw)
                commune_name_col = comm_col if comm_col else 'ten_xa'

                if prov_col:
                    clean_p = remove_accents(prov)
                    mask_c = gdf_comm_raw[prov_col].dropna().astype(str).apply(lambda x: clean_p in remove_accents(x))
                    if not mask_c.any():
                        mask_c = gdf_comm_raw[prov_col].dropna().astype(str).apply(lambda x: prov_key in remove_accents(x))
                    if not mask_c.any():
                        former = [old for old, new in MERGED_OLD_TO_NEW.items() if new == prov_key]
                        for fn in former:
                            mask_c = gdf_comm_raw[prov_col].dropna().astype(str).apply(lambda x: fn in remove_accents(x))
                            if mask_c.any(): break
                    gdf_prov_communes_wgs = gdf_comm_raw[mask_c].copy()

            if gdf_prov_communes_wgs is None or gdf_prov_communes_wgs.empty:
                if gdf_prov_all_raw is not None and not gdf_prov_all_raw.empty:
                    prov_col_p = find_province_column(gdf_prov_all_raw, prov_key)
                    if prov_col_p:
                        clean_p = remove_accents(prov)
                        mask_p = gdf_prov_all_raw[prov_col_p].dropna().astype(str).apply(lambda x: clean_p in remove_accents(x))
                        if not mask_p.any():
                            mask_p = gdf_prov_all_raw[prov_col_p].dropna().astype(str).apply(lambda x: prov_key in remove_accents(x))
                        gdf_prov_communes_wgs = gdf_prov_all_raw[mask_p].copy()
                        commune_name_col = prov_col_p

            if gdf_prov_communes_wgs is None or gdf_prov_communes_wgs.empty:
                raise Exception(f"Không tìm thấy ranh giới '{prov_meta['name']}' trong dữ liệu Shapefile!")

            total_communes = len(gdf_prov_communes_wgs)

            # 4. CHUYỂN ĐỔI CRS & TÍNH KÍCH THƯỚC BẢN ĐỒ LINH ĐỘNG THEO HÌNH DẠNG TỈNH
            gdf_communes = gdf_prov_communes_wgs.to_crs(target_crs)
            prov_outer = gdf_communes.geometry.union_all()

            # Lọc bỏ cụm đảo xa bờ (Côn Đảo, Hoàng Sa, Trường Sa...) để chỉ tính trọng tâm đất liền
            if prov_outer.geom_type == 'MultiPolygon':
                polys = list(prov_outer.geoms)
            elif prov_outer.geom_type == 'Polygon':
                polys = [prov_outer]
            elif hasattr(prov_outer, 'geoms'):
                polys = [g for g in prov_outer.geoms if g.geom_type in ['Polygon', 'MultiPolygon']]
            else:
                polys = [prov_outer]

            main_poly = max(polys, key=lambda p: p.area)
            thresh_buffer = 35000.0 if is_projected else 0.35
            buffered_main = main_poly.buffer(thresh_buffer)
            core_polys = [p for p in polys if p.intersects(buffered_main)]
            core_geom = shapely.ops.unary_union(core_polys) if core_polys else main_poly

            center_geom = core_geom.centroid
            center_x, center_y = center_geom.x, center_geom.y
            
            minx, miny, maxx, maxy = core_geom.bounds
            span_x = maxx - minx
            span_y = maxy - miny

            margin_ratio = self.zoom_margin.get() / 100.0
            pad_x = span_x * margin_ratio
            pad_y = span_y * margin_ratio

            c_minx = minx - pad_x
            c_maxx = maxx + pad_x
            c_miny = miny - pad_y
            c_maxy = maxy + pad_y

            dx = c_maxx - c_minx
            dy = c_maxy - c_miny

            # TÍNH TOÁN TỶ LỆ HÌNH HỌC THỰC TẾ (PHYSICAL ASPECT RATIO) CỦA VÙNG TRỌNG TÂM
            if is_projected:
                geo_aspect = dx / dy
                mean_lat = 0.0
            else:
                mean_lat = (c_miny + c_maxy) / 2.0
                cos_lat = math.cos(math.radians(mean_lat))
                geo_aspect = (dx * cos_lat) / dy

            # TÍNH KÍCH THƯỚC KHUNG HÌNH (FIGURE SIZE) VỪA KHÍT MÀN HÌNH VÀ TỶ LỆ TỈNH
            base_size = 9.0
            if geo_aspect >= 1.0:
                plot_w = base_size
                plot_h = max(5.0, min(base_size, base_size / geo_aspect))
            else:
                plot_h = base_size
                plot_w = max(5.0, min(base_size, base_size * geo_aspect))

            canvas_box = box(c_minx, c_miny, c_maxx, c_maxy)
            canvas_box_w = gpd.GeoSeries([canvas_box], crs=target_crs).to_crs("EPSG:4326").iloc[0].bounds
            c_minx_w, c_miny_w, c_maxx_w, c_maxy_w = canvas_box_w

            has_coast = (prov_meta['sea'] is not None)
            foreign_list = prov_meta['foreign']
            has_foreign = len(foreign_list) > 0

            gdf_neighbors = None
            if gdf_prov_all_raw is not None and not gdf_prov_all_raw.empty:
                p_col = find_province_column(gdf_prov_all_raw, prov_key)
                if p_col:
                    mask_oth = ~gdf_prov_all_raw[p_col].dropna().astype(str).apply(lambda x: prov_key in remove_accents(x))
                    box_w_geom = box(c_minx_w, c_miny_w, c_maxx_w, c_maxy_w)
                    gdf_oth = gdf_prov_all_raw[mask_oth & gdf_prov_all_raw.geometry.intersects(box_w_geom)].copy()
                    if not gdf_oth.empty:
                        gdf_neighbors = gdf_oth.to_crs(target_crs).dissolve(by=p_col).reset_index()

            if gdf_neighbors is not None and not gdf_neighbors.empty:
                all_vn_land = shapely.ops.unary_union([prov_outer, gdf_neighbors.geometry.union_all()])
            else:
                all_vn_land = prov_outer

            vn_true_perimeter = all_vn_land.boundary
            prov_center_x, prov_center_y = center_geom.x, center_geom.y

            # NẠP SÔNG NGÒI, HỒ NƯỚC & GIAO THÔNG
            self.update_status("Đang kết xuất mạng lưới Sông ngòi, Hồ nước và Giao thông...", "orange")
            gdf_rivers = load_feature_layer_safe(self.shp_rivers.get().strip(), target_crs, canvas_box)
            gdf_lakes = load_feature_layer_safe(self.shp_lakes.get().strip(), target_crs, canvas_box)
            gdf_roads = load_feature_layer_safe(self.shp_roads.get().strip(), target_crs, canvas_box)

            if gdf_lakes is not None and not gdf_lakes.empty:
                if gdf_rivers is not None and not gdf_rivers.empty:
                    gdf_rivers = gpd.GeoDataFrame(pd.concat([gdf_rivers, gdf_lakes], ignore_index=True), crs=target_crs)
                else:
                    gdf_rivers = gdf_lakes

            if gdf_rivers is None or gdf_rivers.empty:
                gdf_rivers = fetch_osm_online(c_miny_w, c_minx_w, c_maxy_w, c_maxx_w, '["waterway"~"^(river|canal)$"]')
                if gdf_rivers is not None and not gdf_rivers.empty:
                    gdf_rivers = gdf_rivers.to_crs(target_crs)
                    gdf_rivers = gdf_rivers[gdf_rivers.geometry.intersects(canvas_box)].copy()

            if gdf_roads is None or gdf_roads.empty:
                gdf_roads = fetch_osm_online(c_miny_w, c_minx_w, c_maxy_w, c_maxx_w, '["highway"~"^(motorway|trunk|primary)$"]')
                if gdf_roads is not None and not gdf_roads.empty:
                    gdf_roads = gdf_roads.to_crs(target_crs)
                    gdf_roads = gdf_roads[gdf_roads.geometry.intersects(canvas_box)].copy()

            # KHỞI TẠO ĐỒ HỌA (DÙNG DPI=100 ĐỂ XEM TRƯỚC VỪA VẶN MÀN HÌNH)
            fig = Figure(figsize=(plot_w, plot_h), dpi=100)
            ax = fig.add_subplot(111)
            ax.set_facecolor('#ffffff' if has_foreign else '#f8fafc')

            # KHÓA CHẶT VÙNG HIỂN THỊ BAO KHÍT TỈNH KHÔNG BỊ TRÀN BIÊN
            if is_projected:
                ax.set_aspect('equal', adjustable='box')
            else:
                ax.set_aspect(1.0 / math.cos(math.radians(mean_lat)), adjustable='box')

            # PHÂN TÁCH BIỂN VÀ NƯỚC NGOÀI
            non_vn_area = canvas_box.difference(all_vn_land)
            sea_polys = []
            foreign_polys = []

            if not non_vn_area.is_empty:
                poly_list = list(non_vn_area.geoms) if isinstance(non_vn_area, MultiPolygon) else [non_vn_area]
                for p in poly_list:
                    if p.area < 1e-7: continue
                    if not has_coast:
                        foreign_polys.append(p)
                    elif not has_foreign:
                        sea_polys.append(p)
                    else:
                        s_dir = prov_meta.get('sea_dir', 'E')
                        if s_dir == 'E' and p.centroid.x > prov_center_x:
                            sea_polys.append(p)
                        elif s_dir == 'W' and (p.centroid.x < prov_center_x or p.centroid.y < prov_center_y):
                            sea_polys.append(p)
                        elif s_dir == 'ALL':
                            sea_polys.append(p)
                        else:
                            foreign_polys.append(p)

            sea_polygon = shapely.ops.unary_union(sea_polys) if sea_polys else None
            foreign_land = shapely.ops.unary_union(foreign_polys) if foreign_polys else None

            # 1. Vẽ biển
            if sea_polygon is not None and not sea_polygon.is_empty:
                gpd.GeoSeries([sea_polygon]).plot(ax=ax, facecolor='#bae6fd', edgecolor='none', zorder=1)

            # 2. Lãnh thổ nước bạn
            if foreign_land is not None and not foreign_land.is_empty:
                gpd.GeoSeries([foreign_land]).plot(ax=ax, facecolor='#ffffff', edgecolor='none', zorder=1)

            # 3. Đất liền tỉnh lân cận
            if gdf_neighbors is not None and not gdf_neighbors.empty:
                for _, row in gdf_neighbors.iterrows():
                    gpd.GeoSeries([row.geometry]).plot(ax=ax, color='#f8fafc', edgecolor='none', zorder=2)

            # 4. KẾT XUẤT DEM
            dem_artist = None
            if self.use_dem.get() and HAS_RASTERIO and os.path.exists(self.dem_path.get()):
                self.update_status("Đang trích xuất địa hình DEM...", "orange")
                try:
                    with rasterio.open(self.dem_path.get()) as dem_src:
                        dem_crs = dem_src.crs if dem_src.crs else "EPSG:4326"
                        canvas_box_dem = gpd.GeoSeries([canvas_box], crs=target_crs).to_crs(dem_crs).iloc[0]
                        b_dem = canvas_box_dem.bounds

                        win = from_bounds(b_dem[0], b_dem[1], b_dem[2], b_dem[3], transform=dem_src.transform)
                        c_off = max(0, int(math.floor(win.col_off)))
                        r_off = max(0, int(math.floor(win.row_off)))
                        c_max = min(dem_src.width, int(math.ceil(win.col_off + win.width)))
                        r_max = min(dem_src.height, int(math.ceil(win.row_off + win.height)))
                        w_win = c_max - c_off
                        h_win = r_max - r_off

                        if w_win > 0 and h_win > 0:
                            safe_win = rasterio.windows.Window(c_off, r_off, w_win, h_win)
                            scale_down = max(1.0, max(w_win, h_win) / 900.0)
                            out_w = max(10, int(round(w_win / scale_down)))
                            out_h = max(10, int(round(h_win / scale_down)))
                            
                            dem_chip = dem_src.read(
                                1, window=safe_win, out_shape=(out_h, out_w),
                                resampling=Resampling.bilinear, boundless=True, fill_value=dem_src.nodata or -9999.0
                            ).astype(np.float32)
                            
                            win_bounds = rasterio.windows.bounds(safe_win, dem_src.transform)
                            chip_transform = rasterio.transform.from_bounds(
                                win_bounds[0], win_bounds[1], win_bounds[2], win_bounds[3], out_w, out_h
                            )
                            
                            valid_mask = (dem_chip > -9000.0)
                            filled_dem = dem_chip.copy()
                            filled_dem[~valid_mask] = 0.0
                            
                            ls = LightSource(azdeg=315, altdeg=45)
                            shaded = ls.hillshade(filled_dem, vert_exag=1.8).astype(np.float32)
                            shaded[~valid_mask] = np.nan

                            if str(target_crs).lower() != str(dem_crs).lower():
                                dest_transform, dest_width, dest_height = calculate_default_transform(
                                    dem_crs, target_crs, out_w, out_h,
                                    *rasterio.transform.array_bounds(out_h, out_w, chip_transform)
                                )
                                reprojected_shade = np.full((dest_height, dest_width), np.nan, dtype=np.float32)
                                reproject(
                                    source=shaded, destination=reprojected_shade,
                                    src_transform=chip_transform, src_crs=dem_crs,
                                    dst_transform=dest_transform, dst_crs=target_crs,
                                    resampling=Resampling.bilinear
                                )
                                r_bounds = rasterio.transform.array_bounds(dest_height, dest_width, dest_transform)
                                final_shade = reprojected_shade
                                final_transform = dest_transform
                            else:
                                r_bounds = rasterio.transform.array_bounds(out_h, out_w, chip_transform)
                                final_shade = shaded
                                final_transform = chip_transform

                            try:
                                from rasterio.features import geometry_mask
                                vn_clipped = all_vn_land.intersection(canvas_box)
                                poly_geom = [vn_clipped] if vn_clipped.geom_type in ['Polygon', 'MultiPolygon'] else [
                                    g for g in getattr(vn_clipped, 'geoms', []) if g.geom_type in ['Polygon', 'MultiPolygon']
                                ]
                                if poly_geom:
                                    in_vn_mask = geometry_mask(poly_geom, out_shape=final_shade.shape, transform=final_transform, invert=True)
                                    final_shade[~in_vn_mask] = np.nan
                            except Exception:
                                pass

                            dem_artist = ax.imshow(
                                final_shade, extent=[r_bounds[0], r_bounds[2], r_bounds[1], r_bounds[3]],
                                origin='upper', cmap='gray', alpha=0.28, zorder=3
                            )
                except Exception as e_dem:
                    print(f"Bỏ qua DEM: {e_dem}")

            # 5. VẼ CÁC XÃ / PHƯỜNG TRONG TỈNH
            self.update_status("Đang vẽ ranh giới từng xã / phường...", "orange")
            try:
                import matplotlib as mpl
                cmap = mpl.colormaps['Pastel1']
            except Exception:
                cmap = plt.cm.get_cmap('Pastel1', 9)

            palette = [mcolors.to_hex(cmap(i % cmap.N)) for i in range(total_communes)]
            gdf_communes['color'] = palette

            for _, row in gdf_communes.iterrows():
                gpd.GeoSeries([row.geometry]).plot(ax=ax, color=row['color'], edgecolor='none', alpha=0.52, zorder=4)

            for _, row in gdf_communes.iterrows():
                gpd.GeoSeries([row.geometry]).plot(ax=ax, facecolor='none', edgecolor='#475569', linewidth=0.60, linestyle='-', zorder=5)

            # 6. HỆ THỐNG RANH GIỚI
            eps = 5.0 if is_projected else 0.00005

            if has_foreign and foreign_land is not None and not foreign_land.is_empty:
                national_border = all_vn_land.boundary.intersection(foreign_land.buffer(eps * 2))
                if not national_border.is_empty:
                    gpd.GeoSeries([national_border]).plot(
                        ax=ax, color='#000000', linewidth=2.5, linestyle=(0, (6, 2, 1.2, 2, 1.2, 2)), zorder=8
                    )

            if has_coast and sea_polygon is not None and not sea_polygon.is_empty:
                coastline = all_vn_land.boundary.intersection(sea_polygon.buffer(eps * 2))
                if not coastline.is_empty:
                    gpd.GeoSeries([coastline]).plot(ax=ax, color='#0284c7', linewidth=0.85, zorder=7)

            prov_internal = prov_outer.boundary.difference(vn_true_perimeter.buffer(eps * 2))
            if not prov_internal.is_empty:
                gpd.GeoSeries([prov_internal]).plot(
                    ax=ax, facecolor='none', edgecolor='#1e1b4b', linewidth=2.0, linestyle=(0, (6, 2, 1.5, 2)), zorder=7
                )

            if gdf_neighbors is not None and not gdf_neighbors.empty:
                for _, nb_row in gdf_neighbors.iterrows():
                    nb_geom = nb_row.geometry
                    nb_internal = nb_geom.boundary.difference(vn_true_perimeter.buffer(eps * 2)).difference(prov_outer.buffer(eps * 2))
                    if not nb_internal.is_empty:
                        gpd.GeoSeries([nb_internal]).plot(
                            ax=ax, color='#64748b', linewidth=1.2, linestyle=(0, (5, 2, 1.2, 2)), zorder=6
                        )

            # 7. VẼ SÔNG NGÒI & GIAO THÔNG
            if gdf_rivers is not None and not gdf_rivers.empty:
                riv_polys = gdf_rivers[gdf_rivers.geometry.type.isin(['Polygon', 'MultiPolygon'])]
                riv_lines = gdf_rivers[gdf_rivers.geometry.type.isin(['LineString', 'MultiLineString'])]
                if not riv_polys.empty:
                    riv_polys.plot(ax=ax, facecolor='#7dd3fc', edgecolor='#0284c7', linewidth=0.6, alpha=0.80, zorder=6)
                if not riv_lines.empty:
                    riv_lines.plot(ax=ax, color='#0284c7', linewidth=0.9, alpha=0.85, zorder=6)

            if gdf_roads is not None and not gdf_roads.empty:
                road_lines = gdf_roads[gdf_roads.geometry.type.isin(['LineString', 'MultiLineString'])]
                road_polys = gdf_roads[gdf_roads.geometry.type.isin(['Polygon', 'MultiPolygon'])]
                if not road_lines.empty:
                    road_lines.plot(ax=ax, color='#dc2626', linewidth=1.1, alpha=0.95, zorder=6)
                if not road_polys.empty:
                    road_polys.plot(ax=ax, facecolor='#f87171', edgecolor='#dc2626', linewidth=0.5, zorder=6)

            # =========================================================================
            # CÁC ĐỐI TƯỢNG BIÊN TẬP TƯƠNG TÁC
            # =========================================================================
            editable_texts = {}

            title_prefix = prov_meta['type']
            clean_title = prov_meta['name'].upper()
            title_artist = ax.set_title(f"BẢN ĐỒ HÀNH CHÍNH {title_prefix} {clean_title}", fontsize=15, fontweight='bold', fontfamily='serif', pad=28, color='#0f172a')
            editable_texts["[Tiêu đề] Bản đồ"] = title_artist

            # Tên tỉnh chính trung tâm
            t_main_prov = ax.text(
                prov_center_x, prov_center_y, f"{title_prefix} {clean_title}",
                ha='center', va='center', rotation=0.0,
                fontsize=18.0, fontweight='bold', fontfamily='serif',
                color='#1e1b4b', zorder=11, clip_on=True,
                path_effects=[pe.withStroke(linewidth=3.5, foreground="white")]
            )
            editable_texts[f"[Tỉnh chính] {title_prefix} {clean_title}"] = t_main_prov

            # Tỉnh lân cận
            if gdf_neighbors is not None and not gdf_neighbors.empty:
                nb_cols = [c for c in gdf_neighbors.columns if any(k in c.lower() for k in ['tinh', 'prov', 'name', 'city'])]
                nb_col = nb_cols[0] if nb_cols else gdf_neighbors.columns[0]
                for _, row in gdf_neighbors.iterrows():
                    visible_geom = row.geometry.intersection(canvas_box)
                    if not visible_geom.is_empty:
                        pt = safe_polylabel(visible_geom)
                        nb_name = str(row[nb_col]).replace("Tỉnh ", "").replace("Thành phố ", "TP. ").upper()
                        
                        vis_ratio = visible_geom.area / (dx * dy)
                        if vis_ratio < 0.02: nb_fsize = 7.5
                        elif vis_ratio < 0.05: nb_fsize = 8.5
                        elif vis_ratio < 0.10: nb_fsize = 9.5
                        else: nb_fsize = 10.5

                        t_nb = ax.annotate(
                            text=f"TỈNH {nb_name}" if "TP." not in nb_name else nb_name, 
                            xy=(pt.x, pt.y), ha='center', va='center', rotation=0.0,
                            fontsize=nb_fsize, fontweight='bold', fontfamily='serif', color='#334155',
                            zorder=9, clip_on=True, path_effects=[pe.withStroke(linewidth=2.4, foreground="white")]
                        )
                        editable_texts[f"Tỉnh: {nb_name}"] = t_nb

            # Quốc gia láng giềng
            if has_foreign:
                for idx, fg_name in enumerate(foreign_list):
                    offset_y = (0.37 if idx == 0 else 0.55) * dy
                    t_country = ax.annotate(
                        fg_name, xy=(minx + 0.045 * dx, miny + offset_y),
                        ha='center', va='center', rotation=0.0,
                        fontsize=12.5, fontweight='bold', fontfamily='serif', color='#1e293b',
                        zorder=9, clip_on=True, path_effects=[pe.withStroke(linewidth=3.2, foreground="white")]
                    )
                    editable_texts[f"[Quốc gia] {fg_name}"] = t_country

            # Vùng biển
            if has_coast:
                sea_label = prov_meta['sea']
                s_dir = prov_meta.get('sea_dir', 'E')
                sea_x = (minx - 0.03 * dx) if s_dir == 'W' else (maxx + 0.015 * dx)

                t_sea = ax.annotate(
                    sea_label, xy=(sea_x, miny + 0.26 * dy),
                    ha='center', va='center', rotation=0.0,
                    fontsize=13.0, fontweight='bold', fontstyle='italic', fontfamily='serif', color='#0284c7',
                    zorder=9, clip_on=True, path_effects=[pe.withStroke(linewidth=3.2, foreground="white")]
                )
                editable_texts[f"[Vùng biển] {sea_label}"] = t_sea

            # Tên sông
            min_feature_len = 0.04 * max(dx, dy)
            if gdf_rivers is not None and not gdf_rivers.empty:
                gdf_rivers_in_prov = gpd.clip(gdf_rivers, prov_outer)
                river_name_col = find_feature_name_col(gdf_rivers_in_prov, ['ten_song', 'tensong', 'ten', 'name', 'waterway'])
                if river_name_col and not gdf_rivers_in_prov.empty:
                    valid_riv = gdf_rivers_in_prov[gdf_rivers_in_prov[river_name_col].notna()].copy()
                    valid_riv['clean_name'] = valid_riv[river_name_col].astype(str).str.strip()
                    valid_riv = valid_riv[~valid_riv['clean_name'].str.lower().isin(['', 'none', 'nan', 'null', '0', 'unnamed'])]
                    valid_riv = valid_riv[~valid_riv['clean_name'].str.isdigit()]

                    for r_name, group in valid_riv.groupby('clean_name'):
                        line_parts = group[group.geometry.type.isin(['LineString', 'MultiLineString'])]
                        if not line_parts.empty:
                            m_geom = line_parts.geometry.union_all() if hasattr(line_parts.geometry, 'union_all') else line_parts.geometry.unary_union
                            if isinstance(m_geom, LineString): best_line = m_geom
                            elif isinstance(m_geom, MultiLineString): best_line = max(m_geom.geoms, key=lambda l: l.length)
                            else: best_line = None

                            if best_line is not None and best_line.length >= min_feature_len:
                                rx, ry, r_angle = get_line_label_pt_and_angle(best_line, is_projected)
                                if prov_outer.contains(shapely.geometry.Point(rx, ry)):
                                    t_riv = ax.text(
                                        rx, ry, r_name,
                                        ha='center', va='center', rotation=r_angle,
                                        fontsize=7.8, fontweight='normal', fontstyle='italic', fontfamily='serif',
                                        color='#0369a1', zorder=10, clip_on=True,
                                        path_effects=[pe.withStroke(linewidth=2.2, foreground="white")]
                                    )
                                    editable_texts[f"Sông: {r_name}"] = t_riv

            # Tên đường
            if gdf_roads is not None and not gdf_roads.empty:
                gdf_roads_in_prov = gpd.clip(gdf_roads, prov_outer)
                road_name_col = find_feature_name_col(gdf_roads_in_prov, ['ten_duong', 'tenduong', 'so_hieu', 'sohieu', 'ref', 'ten', 'name', 'highway', 'route'])
                if road_name_col and not gdf_roads_in_prov.empty:
                    valid_rd = gdf_roads_in_prov[gdf_roads_in_prov[road_name_col].notna()].copy()
                    valid_rd['clean_name'] = valid_rd[road_name_col].astype(str).str.strip()
                    valid_rd = valid_rd[~valid_rd['clean_name'].str.lower().isin(['', 'none', 'nan', 'null', '0', 'unnamed'])]
                    valid_rd = valid_rd[~valid_rd['clean_name'].str.isdigit()]

                    for rd_name, group in valid_rd.groupby('clean_name'):
                        line_parts = group[group.geometry.type.isin(['LineString', 'MultiLineString'])]
                        if not line_parts.empty:
                            m_geom = line_parts.geometry.union_all() if hasattr(line_parts.geometry, 'union_all') else line_parts.geometry.unary_union
                            if isinstance(m_geom, LineString): best_line = m_geom
                            elif isinstance(m_geom, MultiLineString): best_line = max(m_geom.geoms, key=lambda l: l.length)
                            else: best_line = None

                            if best_line is not None and best_line.length >= (min_feature_len * 1.2):
                                rx, ry, rd_angle = get_line_label_pt_and_angle(best_line, is_projected)
                                if prov_outer.contains(shapely.geometry.Point(rx, ry)):
                                    t_rd = ax.text(
                                        rx, ry, rd_name,
                                        ha='center', va='center', rotation=rd_angle,
                                        fontsize=7.2, fontweight='bold', fontfamily='serif',
                                        color='#991b1b', zorder=10, clip_on=True,
                                        path_effects=[pe.withStroke(linewidth=2.0, foreground="white")]
                                    )
                                    editable_texts[f"Đường: {rd_name}"] = t_rd

            # Gán nhãn xã/phường
            area_ref = (dx * dy)
            for _, row in gdf_communes.iterrows():
                geom = row.geometry
                raw_name = str(row.get(commune_name_col, ''))
                if not raw_name or raw_name.lower() in ['none', 'nan', ''] or raw_name.strip().isdigit():
                    continue

                clean_name = (raw_name.replace("Huyện ", "")
                                      .replace("Thị xã ", "TX. ")
                                      .replace("Thành phố ", "TP. ")
                                      .replace("Quận ", "Q. ")
                                      .replace("Xã ", "")
                                      .replace("Phường ", "P. ")
                                      .replace("Thị trấn ", "TT. "))

                center_pt = safe_polylabel(geom)
                rel_area = geom.area / area_ref
                f_size = 5.8 if rel_area < 0.005 else (6.5 if rel_area < 0.02 else (7.5 if rel_area > 0.08 else 6.8))

                txt = ax.text(
                    center_pt.x, center_pt.y, clean_name, ha='center', va='center', 
                    rotation=0.0,
                    fontsize=f_size, fontweight='bold', fontfamily='serif', color='#0f172a',
                    zorder=10, clip_on=True, path_effects=[pe.withStroke(linewidth=1.8, foreground="white")]
                )
                editable_texts[f"Xã/Phường: {clean_name}"] = txt

            # KIM CHỈ BẮC
            arrow_x = c_maxx - 0.05 * dx
            arrow_y = c_maxy - 0.07 * dy
            north_arrow_obj = DraggableNorthArrow(ax, arrow_x, arrow_y, dx, dy)
            editable_texts["[La bàn] Kim chỉ hướng Bắc"] = north_arrow_obj

            # THƯỚC TỶ LỆ
            if is_projected:
                width_km = dx / 1000.0
            else:
                km_per_deg = 111.32 * math.cos(math.radians(mean_lat))
                width_km = dx * km_per_deg

            if width_km < 35: bar_total_km = 10
            elif width_km < 70: bar_total_km = 20
            elif width_km < 140: bar_total_km = 30
            elif width_km < 250: bar_total_km = 40
            else: bar_total_km = 50

            half_km = bar_total_km / 2
            if is_projected:
                bar_len = bar_total_km * 1000.0
                half_len = half_km * 1000.0
            else:
                bar_len = bar_total_km / km_per_deg
                half_len = half_km / km_per_deg

            bar_h = 0.009 * dy
            sx = minx + 0.015 * dx
            sy = c_miny + 0.015 * dy
            scale_bar_obj = DraggableScaleBar(ax, sx, sy, dx, dy, half_len, bar_len, half_km, bar_total_km)
            editable_texts["[Thước đo] Thước tỷ lệ"] = scale_bar_obj

            # Bảng Chú giải
            legend_elements = []
            if has_foreign:
                legend_elements.append(mlines.Line2D([], [], color='#000000', linewidth=2.5, linestyle=(0, (6, 2, 1.2, 2, 1.2, 2)), label='Đường biên giới quốc gia'))

            legend_elements.append(mlines.Line2D([], [], color='#1e1b4b', linewidth=2.0, linestyle=(0, (6, 2, 1.5, 2)), label='Đường địa giới tỉnh/TP'))
            if total_communes > 1:
                legend_elements.append(mlines.Line2D([], [], color='#475569', linewidth=0.65, linestyle='-', label=f'Ranh giới {total_communes} xã / phường'))
            
            if has_coast:
                legend_elements.append(mlines.Line2D([], [], color='#0284c7', linewidth=0.85, linestyle='-', label='Đường bờ biển'))

            legend_elements.append(mlines.Line2D([], [], color='#dc2626', linewidth=1.2, label='Tuyến Quốc lộ'))
            legend_elements.append(mlines.Line2D([], [], color='#0284c7', linewidth=0.75, label='Hệ thống sông chính'))
            
            if has_coast:
                legend_elements.append(mpatches.Patch(facecolor='#bae6fd', edgecolor='#38bdf8', label=f"Vùng biển ({prov_meta['sea']})"))

            if has_foreign:
                for fg_name in foreign_list:
                    legend_elements.append(mpatches.Patch(facecolor='#ffffff', edgecolor='#cbd5e1', label=f'Lãnh thổ ({fg_name})'))

            if dem_artist is not None:
                legend_elements.append(mpatches.Patch(facecolor='#d1d5db', edgecolor='#9ca3af', label='Địa hình'))

            leg = ax.legend(
                handles=legend_elements, bbox_to_anchor=(0.015, 0.055), loc='lower left',
                frameon=True, facecolor='white', edgecolor='#94a3b8', framealpha=0.95,
                title='CHÚ GIẢI', title_fontproperties={'family': 'serif', 'weight': 'bold', 'size': 9},
                prop={'family': 'serif', 'size': 8.0}
            )
            leg.set_zorder(10)
            leg.set_draggable(True)

            for leg_txt in leg.get_texts():
                item_title = f"[Chú giải] {leg_txt.get_text()}"
                editable_texts[item_title] = leg_txt

            # ĐẶT TỌA ĐỘ GIỚI HẠN CHUẨN XÁC BAO KHÍT TỈNH
            ax.set_xlim(c_minx, c_maxx)
            ax.set_ylim(c_miny, c_maxy)

            # CẤU HÌNH KHUNG TỌA ĐỘ
            int_choice = self.grid_interval.get()
            if is_projected:
                ax.set_xlabel(f"Tọa độ X - Mét ({self.crs_choice.get()})", fontsize=9, fontfamily='serif', labelpad=8)
                ax.set_ylabel(f"Tọa độ Y - Mét ({self.crs_choice.get()})", fontsize=9, fontfamily='serif', labelpad=12)
                ax.xaxis.set_major_formatter(FuncFormatter(lambda val, pos: f"{int(val):,}"))
                ax.yaxis.set_major_formatter(FuncFormatter(lambda val, pos: f"{int(val):,}"))
                
                if "Dày" in int_choice: step = max(5000.0, round(dx / 10 / 5000) * 5000)
                elif "Thưa" in int_choice: step = max(20000.0, round(dx / 4 / 10000) * 10000)
                else:
                    raw_s = dx / 6.0
                    step = 10000.0 if raw_s < 15000 else (20000.0 if raw_s < 35000 else (50000.0 if raw_s < 75000 else 100000.0))
            else:
                ax.set_xlabel(f"Kinh độ ({self.crs_choice.get()})", fontsize=9, fontfamily='serif', labelpad=8)
                ax.set_ylabel(f"Vĩ độ ({self.crs_choice.get()})", fontsize=9, fontfamily='serif', labelpad=12)
                ax.xaxis.set_major_formatter(FuncFormatter(lambda val, pos: f"{val:.2f}°"))
                ax.yaxis.set_major_formatter(FuncFormatter(lambda val, pos: f"{val:.2f}°"))

                if "Dày" in int_choice: step = 0.1 if dx < 1.0 else 0.2
                elif "Thưa" in int_choice: step = 0.5 if dx < 1.5 else 1.0
                else:
                    step = 0.1 if dx < 0.6 else (0.2 if dx < 1.2 else (0.4 if dx < 2.5 else 0.5))

            ax.tick_params(axis='x', top=True, labeltop=True, bottom=True, labelbottom=True, labelsize=8.5, direction='out', length=4)
            ax.tick_params(axis='y', left=True, labelleft=True, right=True, labelright=True, labelrotation=90, labelsize=8.5, direction='out', length=4)

            if self.show_grid.get():
                ax.xaxis.set_major_locator(MultipleLocator(step))
                ax.yaxis.set_major_locator(MultipleLocator(step))
                line_s = ':' if ":" in self.grid_style.get() else ('--' if "--" in self.grid_style.get() else '-')
                ax.grid(color='#64748b', linestyle=line_s, linewidth=0.75, alpha=0.65, zorder=11)

            for tick in ax.get_xticklabels() + ax.get_yticklabels():
                tick.set_fontfamily('serif')

            fig.tight_layout()

            self.update_status(f"Hoàn thành bản đồ {prov_meta['name']}! Đang mở cửa sổ xem trước...", "green")
            self.root.after(0, lambda: MapEditorWindow(
                self.root, fig, ax, out_f, editable_texts, dem_artist, leg
            ))

        except Exception as e:
            traceback.print_exc()
            err_msg = str(e)
            self.update_status("Lỗi quá trình tạo bản đồ.", "red")
            self.root.after(0, lambda msg=err_msg: messagebox.showerror("Chi tiết lỗi", msg))
        finally:
            self.root.after(0, lambda: self.btn_run.config(state=tk.NORMAL))

if __name__ == "__main__":
    root = tk.Tk()
    app = MainMapApp(root)
    root.mainloop()