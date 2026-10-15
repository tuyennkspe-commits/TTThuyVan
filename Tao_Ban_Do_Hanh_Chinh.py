"""Bản đồ hành chính với DEM toàn cầu và giao thông/sông ngòi OpenStreetMap.
Cài thư viện: python -m pip install geopandas rasterio matplotlib numpy pandas pillow scipy
Lần đầu tải cần Internet; dữ liệu DEM/OSM được lưu đệm ngoài thư mục mã nguồn.
DEM nền phục vụ thể hiện bản đồ, không thay thế DEM khảo sát cho tính toán thủy văn.
"""
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
import pandas as pd
import io
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import urllib.request
import urllib.parse
import hashlib
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

# Global elevation for map shading. Terrarium pixels encode elevation in metres.
TERRAIN_TILE_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
DEM_GLOBAL = 'Toàn cầu: tự tải và lưu đệm'
DEM_LOCAL = 'Offline: dùng file GeoTIFF'

def terrain_cache_dir():
    root=os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'),'.cache')
    return os.path.join(root,'TTThuyVan','terrain-terrarium')

def terrain_tile_plan(bounds,max_tiles=36,max_zoom=13):
    west,south,east,north=map(float,bounds)
    if not np.isfinite([west,south,east,north]).all() or not -180<=west<east<=180 or not -85<=south<north<=85:
        raise ValueError('Khung DEM phải nằm trong kinh độ ±180°, vĩ độ ±85°, không cắt kinh tuyến 180°.')
    def xy(lon,lat,n):
        return (lon+180)/360*n,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n
    for z in range(max_zoom,-1,-1):
        n=2**z;x0,y0=xy(west,north,n);x1,y1=xy(east,south,n)
        xmin=max(0,int(math.floor(x0)));xmax=min(n-1,int(math.ceil(x1))-1)
        ymin=max(0,int(math.floor(y0)));ymax=min(n-1,int(math.ceil(y1))-1)
        if (xmax-xmin+1)*(ymax-ymin+1)<=max_tiles:
            return z,[(x,y) for y in range(ymin,ymax+1) for x in range(xmin,xmax+1)]
    raise ValueError('Không xác định được khung tải DEM.')

def decode_terrarium(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.size!=(256,256):raise ValueError('Ô DEM tải về không đúng kích thước 256×256.')
        pixels=np.array(image.convert('RGBA'),dtype=np.float32)
    heights=pixels[:,:,0]*256+pixels[:,:,1]+pixels[:,:,2]/256-32768
    heights[(pixels[:,:,3]==0)|(heights<=-32768)]=np.nan
    return heights.astype(np.float32)

def load_terrain_tile(z,x,y,cache_dir):
    path=os.path.join(cache_dir,str(z),str(x),f'{y}.png')
    if os.path.isfile(path):
        try:
            with open(path,'rb') as stream:return decode_terrarium(stream.read())
        except (OSError,ValueError):pass
    request=urllib.request.Request(TERRAIN_TILE_URL.format(z=z,x=x,y=y),headers={'User-Agent':'TTThuyVan-AdministrativeMap/1.0'})
    with urllib.request.urlopen(request,timeout=20) as response:
        data=response.read(2_000_001)
    if len(data)>2_000_000:raise ValueError('Ô DEM vượt kích thước cho phép.')
    heights=decode_terrarium(data)
    os.makedirs(os.path.dirname(path),exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path),suffix='.tmp',delete=False) as stream:
            temporary=stream.name;stream.write(data)
        os.replace(temporary,path);temporary=None
    finally:
        if temporary and os.path.exists(temporary):os.remove(temporary)
    return heights

def global_terrain(bounds,cache_dir,progress=None):
    z,tiles=terrain_tile_plan(bounds)
    xmin=min(x for x,y in tiles);ymin=min(y for x,y in tiles)
    xmax=max(x for x,y in tiles);ymax=max(y for x,y in tiles)
    mosaic=np.full(((ymax-ymin+1)*256,(xmax-xmin+1)*256),np.nan,dtype=np.float32)
    failures=[];completed=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(load_terrain_tile,z,x,y,cache_dir):(x,y) for x,y in tiles}
        for future in as_completed(pending):
            x,y=pending[future]
            try:mosaic[(y-ymin)*256:(y-ymin+1)*256,(x-xmin)*256:(x-xmin+1)*256]=future.result()
            except Exception as exc:failures.append(str(exc))
            completed+=1
            if progress:progress(f'Địa hình toàn cầu: {completed}/{len(tiles)} ô (mức {z})')
    if not np.isfinite(mosaic).any():raise ValueError('Không tải được DEM toàn cầu và chưa có ô lưu đệm: '+(failures[0] if failures else 'DEM không có giá trị.'))
    radius=20037508.342789244;pixel=2*radius/(2**z*256)
    transform=rasterio.transform.from_origin(-radius+xmin*256*pixel,radius-ymin*256*pixel,pixel,pixel)
    note=f'Thiếu {len(failures)}/{len(tiles)} ô địa hình; vùng thiếu để trống.' if failures else ''
    return mosaic,transform,'EPSG:3857',f'Terrain Tiles / Mapzen, AWS Open Data (z={z})',note

def local_terrain(path,bounds,target_crs):
    from rasterio.warp import transform_bounds
    with rasterio.open(path) as src:
        if src.crs is None:raise ValueError('DEM offline thiếu hệ tọa độ CRS; cần khai báo đúng CRS trước khi sử dụng.')
        bb=transform_bounds(target_crs,src.crs,*bounds,densify_pts=21)
        window=from_bounds(*bb,transform=src.transform)
        window=window.intersection(rasterio.windows.Window(0,0,src.width,src.height))
        ratio=max(1.,window.width/1500,window.height/1500)
        width=max(2,int(math.ceil(window.width/ratio)));height=max(2,int(math.ceil(window.height/ratio)))
        data=src.read(1,window=window,out_shape=(height,width),masked=True,resampling=Resampling.bilinear).astype(np.float32).filled(np.nan)
        transform=rasterio.windows.transform(window,src.transform)*rasterio.Affine.scale(window.width/width,window.height/height)
        return data,transform,src.crs,'DEM offline: '+os.path.basename(path),''

def shaded_terrain(data,transform,source_crs,bounds,target_crs,max_side=1100):
    from rasterio.warp import transform_bounds
    from pyproj import CRS
    from scipy.ndimage import distance_transform_edt
    crs=CRS.from_user_input(target_crs)
    geographic=transform_bounds(target_crs,'EPSG:4326',*bounds,densify_pts=21)
    lon=(geographic[0]+geographic[2])/2;lat=(geographic[1]+geographic[3])/2
    metric=crs if crs.is_projected and all(np.isclose(axis.unit_conversion_factor,1) for axis in crs.axis_info[:2]) else CRS.from_proj4(f'+proj=laea +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs')
    bb=transform_bounds(target_crs,metric,*bounds,densify_pts=21)
    span_x=bb[2]-bb[0];span_y=bb[3]-bb[1]
    width=max(3,int(max_side*span_x/max(span_x,span_y)));height=max(3,int(max_side*span_y/max(span_x,span_y)))
    grid=rasterio.transform.from_bounds(*bb,width,height)
    elevations=np.full((height,width),np.nan,dtype=np.float32)
    reproject(source=data,destination=elevations,src_transform=transform,src_crs=source_crs,src_nodata=np.nan,dst_transform=grid,dst_crs=metric,dst_nodata=np.nan,resampling=Resampling.bilinear)
    valid=np.isfinite(elevations)
    if not valid.any():raise ValueError('DEM không có dữ liệu trong khung bản đồ.')
    # Fill only for gradients; the original missing-data mask is restored afterwards.
    nearest=distance_transform_edt(~valid,return_distances=False,return_indices=True)
    filled=elevations[tuple(nearest)]
    shade=LightSource(azdeg=315,altdeg=45).hillshade(filled,vert_exag=1.8,dx=abs(grid.a),dy=abs(grid.e)).astype(np.float32)
    shade[~valid]=np.nan
    west,south,east,north=bounds
    display_width=max(3,int(max_side*(east-west)/max(east-west,north-south)))
    display_height=max(3,int(max_side*(north-south)/max(east-west,north-south)))
    display_grid=rasterio.transform.from_bounds(*bounds,display_width,display_height)
    display=np.full((display_height,display_width),np.nan,dtype=np.float32)
    reproject(source=shade,destination=display,src_transform=grid,src_crs=metric,src_nodata=np.nan,dst_transform=display_grid,dst_crs=target_crs,dst_nodata=np.nan,resampling=Resampling.bilinear)
    return display,display_grid

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

VECTOR_ONLINE='Online: OpenStreetMap + lưu đệm'
VECTOR_LOCAL='Offline: dùng Shapefile'
ROAD_MAIN='Đường chính'
ROAD_DETAIL='Thêm đường dân sinh'
OSM_ENDPOINTS=['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter']

def osm_frame(elements):
    records=[];seen=set()
    for el in elements:
        key=(el.get('type'),el.get('id'))
        if key in seen:continue
        seen.add(key);geometry=el.get('geometry',[])
        if len(geometry)<2:continue
        try:
            coordinates=[(float(pt['lon']),float(pt['lat'])) for pt in geometry]
            if not np.isfinite(coordinates).all():continue
            line=LineString(coordinates)
            if line.is_empty or line.length==0:continue
        except (KeyError,ValueError,TypeError):continue
        tags=el.get('tags',{})
        records.append(dict(osm_id=el.get('id'),name=tags.get('name:vi') or tags.get('name') or tags.get('ref'),ref=tags.get('ref'),highway=tags.get('highway'),waterway=tags.get('waterway'),geometry=line))
    if not records:return gpd.GeoDataFrame({'geometry':[]},geometry='geometry',crs='EPSG:4326')
    return gpd.GeoDataFrame(records,geometry='geometry',crs='EPSG:4326')

def osm_query_tile(bounds,kind,detail,cache_dir):
    west,south,east,north=bounds
    roads='motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link'
    if detail==ROAD_DETAIL:roads+='|unclassified|residential|living_street|service|track'
    query_tag=f'["highway"~"^({roads})$"]' if kind=='roads' else '["waterway"~"^(river|stream|canal|drain|ditch)$"]'
    key=hashlib.sha256(json.dumps([bounds,query_tag,1],sort_keys=True).encode()).hexdigest()
    path=os.path.join(cache_dir,'osm',key+'.json')
    if os.path.isfile(path):
        try:
            with open(path,encoding='utf-8') as stream:cached=json.load(stream)
            if isinstance(cached.get('elements'),list) and not cached.get('remark'):return cached['elements']
        except (OSError,ValueError,AttributeError):pass
    query=f'[out:json][timeout:30];way{query_tag}({south},{west},{north},{east});out geom;'
    failure=''
    for endpoint in OSM_ENDPOINTS:
        try:
            request=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'TTThuyVan-AdministrativeMap/1.0','Content-Type':'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(request,timeout=40) as response:
                data=response.read(32_000_001)
            if len(data)>32_000_000:raise ValueError('Dữ liệu OSM quá lớn; hãy chọn Đường chính hoặc thu nhỏ khung bản đồ.')
            result=json.loads(data.decode('utf-8'))
            if result.get('remark') or not isinstance(result.get('elements'),list):raise ValueError(result.get('remark','Phản hồi OSM không hợp lệ.'))
            os.makedirs(os.path.dirname(path),exist_ok=True)
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=os.path.dirname(path),suffix='.tmp',delete=False,mode='w',encoding='utf-8') as stream:
                    temporary=stream.name;json.dump(result,stream,ensure_ascii=False)
                os.replace(temporary,path);temporary=None
            finally:
                if temporary and os.path.exists(temporary):os.remove(temporary)
            return result['elements']
        except Exception as exc:failure=str(exc)
    raise ValueError('Không lấy được '+('đường giao thông' if kind=='roads' else 'sông ngòi')+' từ OSM: '+failure)

def online_vector_layer(bounds,kind,cache_dir,detail=ROAD_MAIN,progress=None):
    west,south,east,north=map(float,bounds)
    if not -180<=west<east<=180 or not -85<=south<north<=85:raise ValueError('Khung OSM ngoài phạm vi hỗ trợ.')
    nx=min(4,max(1,int(math.ceil((east-west)/.75))));ny=min(4,max(1,int(math.ceil((north-south)/.75))))
    elements=[];success=0;failed=0;streak=0
    for iy in range(ny):
        for ix in range(nx):
            tile=(west+(east-west)*ix/nx,south+(north-south)*iy/ny,west+(east-west)*(ix+1)/nx,south+(north-south)*(iy+1)/ny)
            try:elements.extend(osm_query_tile(tile,kind,detail,cache_dir));success+=1;streak=0
            except Exception:
                failed+=1;streak+=1
                if streak>=2:break
            if progress:progress(f'OSM {"giao thông" if kind=="roads" else "sông ngòi"}: {success+failed}/{nx*ny} ô')
        if streak>=2:break
    if not success:raise ValueError('OSM chưa tải được và chưa có dữ liệu lưu đệm cho khung này. Kiểm tra kết nối Internet hoặc dùng Shapefile offline.')
    missing=nx*ny-success
    note=f'OSM {kind}: thiếu {missing}/{nx*ny} ô; có thể thiếu đối tượng trên bản đồ.' if missing else ''
    frame=osm_frame(elements)
    if not frame.empty:frame=gpd.clip(frame,box(*bounds))
    return frame,note

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
        self.root.geometry(f"860x{min(940,max(680,self.root.winfo_screenheight()-90))}")
        self.root.resizable(True, True)

        base_dir = r"D:\Phanmem_TTthuyvan\XDungBando"
        
        self.shp_communes = tk.StringVar(value=os.path.join(base_dir, "VietNam_phuong-xa.shp"))
        self.shp_provinces = tk.StringVar(value=os.path.join(base_dir, "VietNam-34Tinh.shp"))
        self.shp_roads = tk.StringVar(value=os.path.join(base_dir, "GIAOTHONG.shp"))
        self.shp_rivers = tk.StringVar(value=os.path.join(base_dir, "Song_VN.shp"))
        self.shp_lakes = tk.StringVar(value="")
        self.dem_path = tk.StringVar(value=os.path.join(base_dir, "VietNam_DEM_SRTMGL1_30m_v3_USGS.tiff"))

        self.province_name = tk.StringVar(value="Hồ Chí Minh")
        
        self.vector_source = tk.StringVar(value=VECTOR_ONLINE)
        self.road_detail = tk.StringVar(value=ROAD_MAIN)
        self.use_dem = tk.BooleanVar(value=True)
        self.dem_source = tk.StringVar(value=DEM_GLOBAL)
        self.dem_cache = tk.StringVar(value=terrain_cache_dir())
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

        sources=ttk.Frame(tab_main);sources.grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,7))
        ttk.Label(sources,text='Đường giao thông, sông:').pack(side='left')
        ttk.Combobox(sources,textvariable=self.vector_source,values=[VECTOR_ONLINE,VECTOR_LOCAL],state='readonly',width=32).pack(side='left',padx=5)
        ttk.Combobox(sources,textvariable=self.road_detail,values=[ROAD_MAIN,ROAD_DETAIL],state='readonly',width=22).pack(side='left')
        
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

        ttk.Label(tab_main,text='Nguồn địa hình DEM:').grid(row=6,column=0,sticky='nw',pady=4)
        dem_box=ttk.Frame(tab_main);dem_box.grid(row=6,column=1,sticky='w',padx=5,pady=3)
        ttk.Combobox(dem_box,textvariable=self.dem_source,values=[DEM_GLOBAL,DEM_LOCAL],state='readonly',width=48).pack(anchor='w')
        ttk.Entry(dem_box,textvariable=self.dem_path,width=50).pack(anchor='w',pady=3)
        ttk.Label(dem_box,text='Toàn cầu: phủ cả nước lân cận, tự lưu để dùng lại.\nOffline: chọn GeoTIFF có phạm vi phủ mong muốn.',font=('Arial',8)).pack(anchor='w')
        dem_buttons=ttk.Frame(tab_main);dem_buttons.grid(row=6,column=2,sticky='n')
        ttk.Button(dem_buttons,text='Duyệt DEM…',command=lambda:self.browse_file(self.dem_path,'*.tif;*.tiff')).pack(fill='x')
        ttk.Button(dem_buttons,text='Thư mục lưu DEM…',command=self.choose_dem_cache).pack(fill='x',pady=3)

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

    def choose_dem_cache(self):
        folder=filedialog.askdirectory(title='Thư mục lưu đệm DEM toàn cầu',initialdir=self.dem_cache.get() if os.path.isdir(self.dem_cache.get()) else os.path.expanduser('~'))
        if folder:self.dem_cache.set(folder)

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

        self._dem_request=dict(mode=self.dem_source.get(),path=self.dem_path.get().strip(),cache=self.dem_cache.get())
        self._vector_request=dict(mode=self.vector_source.get(),detail=self.road_detail.get())
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
            vector_notices=[]
            vector_request=getattr(self,'_vector_request',dict(mode=VECTOR_ONLINE,detail=ROAD_MAIN))
            cache=getattr(self,'_dem_request',dict(cache=terrain_cache_dir()))['cache']
            osm_used=False
            def network_layer(kind,path):
                nonlocal osm_used
                if vector_request['mode']==VECTOR_LOCAL:return load_feature_layer_safe(path,target_crs,canvas_box)
                try:
                    layer,note=online_vector_layer(canvas_box_w,kind,cache,vector_request['detail'],lambda text:self.update_status(text,'orange'))
                    osm_used=True
                    if note:vector_notices.append(note)
                    return gpd.clip(layer.to_crs(target_crs),canvas_box) if not layer.empty else layer.to_crs(target_crs)
                except Exception as error:
                    layer=load_feature_layer_safe(path,target_crs,canvas_box)
                    vector_notices.append(str(error)+(' Đang dùng lớp offline, có thể thiếu phần nước ngoài.' if layer is not None and not layer.empty else ' Chưa có lớp thay thế.'))
                    return layer
            gdf_roads=network_layer('roads',self.shp_roads.get().strip())
            gdf_rivers=network_layer('rivers',self.shp_rivers.get().strip())
            gdf_lakes=load_feature_layer_safe(self.shp_lakes.get().strip(),target_crs,canvas_box)
            if gdf_lakes is not None and not gdf_lakes.empty:
                if gdf_rivers is not None and not gdf_rivers.empty:gdf_rivers=gpd.GeoDataFrame(pd.concat([gdf_rivers,gdf_lakes],ignore_index=True),crs=target_crs)
                else:gdf_rivers=gdf_lakes

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

            # 4. Elevation covers the map frame, including neighbouring countries.
            dem_artist=None;dem_notice='';dem_credit=''
            if self.use_dem.get():
                if not HAS_RASTERIO:
                    dem_notice='Chưa có rasterio nên chưa vẽ được DEM. Cài: python -m pip install rasterio scipy pillow'
                else:
                    request=getattr(self,'_dem_request',dict(mode=DEM_GLOBAL,path='',cache=terrain_cache_dir()))
                    try:
                        if request['mode']==DEM_GLOBAL:
                            try:
                                data,tr,src_crs,dem_credit,dem_notice=global_terrain(canvas_box_w,request['cache'],lambda text:self.update_status(text,'orange'))
                            except Exception as online_error:
                                if not os.path.isfile(request['path']):raise online_error
                                data,tr,src_crs,dem_credit,_=local_terrain(request['path'],canvas_box.bounds,target_crs)
                                dem_notice='DEM toàn cầu không tải được; đang dùng DEM offline, có thể thiếu địa hình ngoài Việt Nam. '+str(online_error)
                        else:
                            data,tr,src_crs,dem_credit,dem_notice=local_terrain(request['path'],canvas_box.bounds,target_crs)
                        final_shade,final_transform=shaded_terrain(data,tr,src_crs,canvas_box.bounds,target_crs)
                        # Do not use the original heuristic foreign/sea polygons to clip
                        # terrain: an outside-Vietnam polygon may contain foreign land.
                        dem_artist=ax.imshow(final_shade,extent=[c_minx,c_maxx,c_miny,c_maxy],origin='upper',cmap='gray',alpha=.28,zorder=3)
                    except Exception as error:
                        dem_notice='Chưa vẽ được địa hình DEM: '+str(error)
            credits=[]
            if dem_artist is not None and 'Terrain Tiles' in dem_credit:credits.append('Địa hình: '+dem_credit)
            if osm_used:credits.append('Giao thông, sông: © OpenStreetMap contributors (ODbL)')
            if credits:fig.text(.01,.005,' | '.join(credits),fontsize=5.5,color='#64748b')

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

            legend_elements.append(mlines.Line2D([], [], color='#dc2626', linewidth=1.2, label='Đường giao thông'))
            legend_elements.append(mlines.Line2D([], [], color='#0284c7', linewidth=0.75, label='Sông, suối và kênh'))
            
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

            dem_notice='\n'.join([note for note in [dem_notice,*vector_notices] if note])
            self.update_status(f"Hoàn thành bản đồ {prov_meta['name']}!"+(' '+dem_notice if dem_notice else ' Đang mở cửa sổ xem trước...'),'orange' if dem_notice else 'green')
            if dem_notice:self.root.after(0,lambda note=dem_notice:messagebox.showwarning('Thông tin địa hình DEM',note))
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