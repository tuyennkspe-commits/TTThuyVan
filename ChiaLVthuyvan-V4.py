"""Chia lưu vực — V8: Bản đồ giấy, DEM và kết hợp kiểm chứng đường phân thủy.
Ảnh giấy: nắn tọa độ từng mảnh, vẽ/chỉnh ranh, sông, hồ; không suy hướng chảy từ màu.
Có thể nội suy DEM từ vector đồng mức Z đã kiểm tra, không ngoại suy ngoài bao lồi.
Cài thư viện: python -m pip install numpy pysheds numba rasterio pyproj geopandas shapely matplotlib customtkinter pandas openpyxl scipy pillow ezdxf
Cao độ DEM phải có đơn vị mét; các cửa xả được tính lưu vực toàn phần độc lập.
"""
import numpy as np
if not hasattr(np, 'in1d'):
    np.in1d = np.isin

import os
import re
import json
import urllib.request
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import tempfile
import threading
import queue
import copy
import hashlib
from PIL import Image, ImageTk
Image.MAX_IMAGE_PIXELS = 180_000_000
from affine import Affine
from shapely.geometry import shape, LineString, Polygon, MultiPolygon, Point
from shapely.ops import unary_union, polygonize
from rasterio.features import shapes
from pyproj import CRS, Transformer
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

D8 = {64:(-1,0), 128:(-1,1), 1:(0,1), 2:(1,1), 4:(1,0), 8:(1,-1), 16:(0,-1), 32:(-1,-1)}

Grid = None

def hydrology_grid_class():
    # Paper-only work should not wait for pysheds' eagerly compiled routing kernels.
    global Grid
    if Grid is None:
        from pysheds.grid import Grid as ImportedGrid
        Grid = ImportedGrid
    return Grid


def metric_dem(source, destination):
    """Reject unknown CRS; warp non-metric/geographic/rotated grids to local UTM."""
    with rasterio.open(source) as src:
        if src.crs is None: raise ValueError('DEM thiếu hệ tọa độ; phải khai báo đúng CRS trước khi xử lý.')
        band = src.read(1, masked=True).astype(float)
        if np.any(~np.isfinite(band.compressed())):
            raise ValueError('DEM có cao độ NaN/vô cực chưa khai báo NoData.')
        crs = CRS(src.crs)
        metric = crs.is_projected and all(abs(a.unit_conversion_factor - 1) < 1e-9 for a in crs.axis_info[:2])
        if metric and src.transform.b == 0 and src.transform.d == 0 and src.transform.a > 0 and src.transform.e < 0:
            if np.any(np.ma.getmaskarray(band)):
                profile = dict(driver='GTiff', height=src.height, width=src.width, transform=src.transform, crs=src.crs, dtype='float64', nodata=-999999.0, count=1)
                with rasterio.open(destination, 'w', **profile) as dst: dst.write(band.filled(-999999.0), 1)
                return destination
            return source
        lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform((src.bounds.left+src.bounds.right)/2, (src.bounds.bottom+src.bounds.top)/2)
        if not -80 <= lat <= 84: raise ValueError('Ngoài miền UTM; hãy cung cấp DEM chiếu phẳng mét phù hợp.')
        target = CRS.from_epsg((32600 if lat >= 0 else 32700) + min(60, max(1, int((lon+180)//6)+1)))
        transform, width, height = calculate_default_transform(src.crs, target, src.width, src.height, *src.bounds)
        profile = dict(driver='GTiff', crs=target, transform=transform, width=width, height=height, dtype='float64', nodata=-999999.0, count=1)
        source_data = src.read(1, masked=True).astype(float).filled(-999999.0)
        with rasterio.open(destination, 'w', **profile) as dst:
            reproject(source_data, rasterio.band(dst, 1), src_transform=src.transform, src_crs=src.crs, src_nodata=-999999.0, dst_transform=transform, dst_crs=target, dst_nodata=-999999.0, resampling=Resampling.bilinear)
    return destination

def valid_dem(dem):
    data = np.asarray(dem, dtype=float)
    valid = np.isfinite(data)
    raster_mask = getattr(dem, 'mask', None)
    if raster_mask is not None: valid &= np.asarray(raster_mask, dtype=bool)
    nodata = getattr(dem, 'nodata', None)
    if nodata is not None: valid &= data != nodata
    return data, valid

def snap_outlet(x, y, transform, acc, valid, radius=2):
    c, r = ~transform * (x, y); r, c = int(np.floor(r)), int(np.floor(c))
    if not 0 <= r < valid.shape[0] or not 0 <= c < valid.shape[1]: raise ValueError('Cửa xả nằm ngoài phạm vi DEM.')
    r0, r1 = max(0, r-radius), min(valid.shape[0], r+radius+1)
    c0, c1 = max(0, c-radius), min(valid.shape[1], c+radius+1)
    local = np.where(valid[r0:r1, c0:c1], np.asarray(acc)[r0:r1, c0:c1], -np.inf)
    if not np.any(np.isfinite(local)): raise ValueError('Không có ô DEM hợp lệ gần cửa xả.')
    best = np.nanmax(local); candidates = np.argwhere(local == best)
    rr, cc = min(candidates, key=lambda rc: (rc[0]+r0-r)**2 + (rc[1]+c0-c)**2)
    return int(rr+r0), int(cc+c0)

def terrain_slope(data, valid, dx, dy):
    z = np.where(valid, data, np.nan)
    def derivative(axis, spacing):
        before = np.full_like(z, np.nan); after = before.copy()
        if axis == 1: before[:, 1:] = z[:, :-1]; after[:, :-1] = z[:, 1:]
        else: before[1:, :] = z[:-1, :]; after[:-1, :] = z[1:, :]
        both = np.isfinite(before) & np.isfinite(after)
        return np.where(both, (after-before)/(2*spacing), np.where(np.isfinite(after), (after-z)/spacing, np.where(np.isfinite(before), (z-before)/spacing, np.nan)))
    return np.hypot(derivative(1, dx), derivative(0, dy)) * 1000

def detect_water_flats_from_dem(dem, flooded, acc, transform, crs, max_slope_pm=18.0, min_area_ha=1.5):
    """
    Dò tìm các mặt hồ phẳng thực tế trên DEM vệ tinh (nơi chưa có trên OSM):
    Kết hợp các ô có độ dốc cục bộ thấp (mặt nước phẳng) HOẶC bị lấp trũng (dep_depth > 0.15m),
    có liên thông với mạng lưới dòng chảy tích lũy (acc >= 80) và diện tích >= min_area_ha.
    """
    import geopandas as gpd
    data, valid = valid_dem(dem)
    dx, dy = abs(transform.a), abs(transform.e)
    cell_area_m2 = dx * dy
    min_cells = max(4, int(np.ceil((min_area_ha * 10000.0) / cell_area_m2)))

    slope_pm = terrain_slope(data, valid, dx, dy)
    dep = np.where(valid, np.maximum(0.0, np.asarray(flooded, dtype=float) - data), 0.0)

    # Ứng viên mặt hồ: vùng rất phẳng hoặc vùng trũng đã điền đầy
    candidate = valid & ((slope_pm <= max_slope_pm) | (dep >= 0.25))

    # Phân cụm liên thông 8 hướng để kiểm tra từng mặt hồ độc lập
    rows, cols = candidate.shape
    visited = np.zeros((rows, cols), dtype=bool)
    water_mask = np.zeros((rows, cols), dtype=bool)
    acc_arr = np.asarray(acc)

    for r in range(rows):
        for c in range(cols):
            if candidate[r, c] and not visited[r, c]:
                # BFS gom cụm nhưng chỉ gom các ô có cao độ chênh lệch nhỏ (cùng 1 mặt nước phẳng <= 1.2m)
                seed_z = data[r, c]
                stack = [(r, c)]
                visited[r, c] = True
                cluster = [(r, c)]
                max_acc_in_cluster = acc_arr[r, c]

                while stack:
                    cr, cc = stack.pop()
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            if dr == 0 and dc == 0: continue
                            nr, nc = cr + dr, cc + dc
                            if 0 <= nr < rows and 0 <= nc < cols and candidate[nr, nc] and not visited[nr, nc]:
                                if abs(data[nr, nc] - seed_z) <= 1.2:
                                    visited[nr, nc] = True
                                    stack.append((nr, nc))
                                    cluster.append((nr, nc))
                                    if acc_arr[nr, nc] > max_acc_in_cluster:
                                        max_acc_in_cluster = acc_arr[nr, nc]

                # Điều kiện là mặt hồ thực tế: Đủ số ô diện tích VÀ nằm trên suối/thung lũng tụ thủy (acc lớn)
                if len(cluster) >= min_cells and max_acc_in_cluster >= 80:
                    for pr, pc in cluster:
                        water_mask[pr, pc] = True

    polys = [shape(g).buffer(0) for g, v in shapes(water_mask.astype('uint8'), mask=water_mask, transform=transform, connectivity=8) if v == 1]
    if not polys:
        return gpd.GeoDataFrame({'geometry': []}, crs=crs)
    merged = unary_union(polys)
    geom_list = [merged] if merged.geom_type == 'Polygon' else list(getattr(merged, 'geoms', []))
    return gpd.GeoDataFrame({'geometry': geom_list}, crs=crs)

def read_kml_kmz_polygons(file_path, target_crs):
    """Đọc trực tiếp các Polygon vẽ từ Google Earth (.kml hoặc .kmz)."""
    import geopandas as gpd
    if file_path.lower().endswith('.kmz'):
        with zipfile.ZipFile(file_path, 'r') as z:
            kml_files = [f for f in z.namelist() if f.lower().endswith('.kml')]
            if not kml_files:
                raise ValueError("File KMZ không chứa dữ liệu KML bên trong.")
            raw_xml = z.read(kml_files[0])
    else:
        with open(file_path, 'rb') as f:
            raw_xml = f.read()

    root = ET.fromstring(raw_xml)
    polys = []
    for elem in root.iter():
        if elem.tag.endswith('Polygon'):
            for coord_elem in elem.iter():
                if coord_elem.tag.endswith('coordinates') and coord_elem.text:
                    pts = []
                    for token in coord_elem.text.strip().split():
                        parts = token.split(',')
                        if len(parts) >= 2:
                            pts.append((float(parts[0]), float(parts[1])))
                    if len(pts) >= 3:
                        poly = Polygon(pts)
                        if not poly.is_valid:
                            poly = poly.buffer(0)
                        if not poly.is_empty:
                            polys.append(poly)
                    break
    if not polys:
        raise ValueError("Không tìm thấy vùng Polygon nào trong file KML/KMZ!")
    gdf = gpd.GeoDataFrame({'geometry': polys}, crs="EPSG:4326")
    if target_crs is not None:
        gdf = gdf.to_crs(target_crs)
    return gdf

def fetch_osm_water_polygons(bbox_metric, metric_crs):
    """Tải tự động toàn bộ mặt nước thực tế (hồ chứa, ao, đập, thủy sản) từ OpenStreetMap."""
    import geopandas as gpd
    xmin, ymin, xmax, ymax = bbox_metric
    transformer = Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True)
    lon1, lat1 = transformer.transform(xmin, ymin)
    lon2, lat2 = transformer.transform(xmax, ymax)
    south, north = min(lat1, lat2), max(lat1, lat2)
    west, east = min(lon1, lon2), max(lon1, lon2)

    overpass_query = f"""
    [out:json][timeout:45];
    (
      way["natural"="water"]({south},{west},{north},{east});
      relation["natural"="water"]({south},{west},{north},{east});
      way["landuse"~"reservoir|basin|aquaculture"]({south},{west},{north},{east});
      relation["landuse"~"reservoir|basin|aquaculture"]({south},{west},{north},{east});
      way["water"]({south},{west},{north},{east});
      relation["water"]({south},{west},{north},{east});
      way["waterway"="riverbank"]({south},{west},{north},{east});
      relation["waterway"="riverbank"]({south},{west},{north},{east});
    );
    out geom;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    data = None
    last_err = None
    for url in endpoints:
        try:
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode({'data': overpass_query}).encode('utf-8'),
                headers={'User-Agent': 'GeoCatchmentPro/3.0'}
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            break
        except Exception as e:
            last_err = e

    if data is None:
        raise ConnectionError(f"Không thể kết nối máy chủ OpenStreetMap: {last_err}")

    polys = []
    for el in data.get('elements', []):
        tags = el.get('tags', {})
        water_type = tags.get('water', '')
        if water_type in ('stream', 'canal', 'ditch', 'drain') or tags.get('waterway') in ('stream', 'canal', 'ditch', 'drain'):
            continue

        if el.get('type') == 'way' and 'geometry' in el:
            coords = [(pt['lon'], pt['lat']) for pt in el['geometry']]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                p = Polygon(coords)
                if not p.is_valid:
                    p = p.buffer(0)
                if not p.is_empty:
                    polys.append(p)
        elif el.get('type') == 'relation' and 'members' in el:
            outer_lines = []
            inner_lines = []
            for m in el['members']:
                if 'geometry' in m:
                    c = [(pt['lon'], pt['lat']) for pt in m['geometry']]
                    if len(c) >= 2:
                        role = m.get('role', 'outer')
                        if role == 'inner':
                            inner_lines.append(LineString(c))
                        else:
                            outer_lines.append(LineString(c))
            if outer_lines:
                outer_polys = list(polygonize(unary_union(outer_lines)))
                inner_polys = list(polygonize(unary_union(inner_lines))) if inner_lines else []
                if outer_polys:
                    rel_geom = unary_union(outer_polys)
                    if inner_polys:
                        rel_geom = rel_geom.difference(unary_union(inner_polys))
                    if not rel_geom.is_empty:
                        polys.append(rel_geom)

    if not polys:
        return gpd.GeoDataFrame({'geometry': []}, crs=metric_crs)

    merged = unary_union(polys)
    if merged.geom_type == 'Polygon':
        geom_list = [merged]
    elif merged.geom_type == 'MultiPolygon':
        geom_list = list(merged.geoms)
    else:
        geom_list = [g for g in getattr(merged, 'geoms', []) if g.geom_type in ('Polygon', 'MultiPolygon')]

    gdf = gpd.GeoDataFrame({'geometry': geom_list}, crs="EPSG:4326").to_crs(metric_crs)
    return gdf

def measure_basin(mask, dem, fdir, acc, outlet, transform, threshold, dep_depth=None, min_sink_depth=0.5, lake_union=None, use_dem_sink=False):
    if int(threshold) != threshold or threshold < 1:
        raise ValueError('Ngưỡng tạo sông phải là số nguyên dương, tính theo số ô góp nước.')
    data, valid = valid_dem(dem)
    mask = np.asarray(mask, dtype=bool) & valid
    if not mask[outlet]: raise ValueError('Cửa xả không thuộc lưu vực hợp lệ.')
    dx, dy = abs(transform.a), abs(transform.e)
    if dx <= 0 or dy <= 0 or transform.b != 0 or transform.d != 0:
        raise ValueError('Cần lưới thẳng trục với kích thước ô dương.')
    polygons = [shape(g) for g, v in shapes(mask.astype('uint8'), mask=mask, transform=transform, connectivity=4) if v == 1]
    polygon = unary_union(polygons)
    slopes = terrain_slope(data, valid, dx, dy)[mask]
    slope = float(np.nanmean(slopes)) if np.any(np.isfinite(slopes)) else np.nan
    streams = (np.asarray(acc) >= threshold) & mask
    edges = {}
    for r, c in np.argwhere(streams):
        p = (int(r), int(c))
        if p == outlet: continue
        direction = D8.get(int(fdir[p]))
        if direction is None: continue
        q = (p[0]+direction[0], p[1]+direction[1])
        if 0 <= q[0] < mask.shape[0] and 0 <= q[1] < mask.shape[1] and mask[q] and streams[q]:
            edges[p] = (q, float(np.hypot(direction[1]*dx, direction[0]*dy)))
    distances = {outlet: 0.0}
    for source in edges:
        path = []; seen = set(); p = source
        while p not in distances and p in edges and p not in seen:
            seen.add(p); path.append(p); p = edges[p][0]
        distance = distances.get(p, np.nan)
        for node in reversed(path):
            distance = distance + edges[node][1]; distances[node] = distance
    connected = {p: edge for p, edge in edges.items() if np.isfinite(distances.get(p, np.nan))}
    best = max((p for p in connected), key=lambda p: distances[p], default=outlet)
    main_nodes = [best]; main_edges = set(); p = best
    while p != outlet:
        main_edges.add(p); p = connected[p][0]; main_nodes.append(p)
    def xy(p): return transform * (p[1]+.5, p[0]+.5)
    main = LineString([xy(p) for p in main_nodes]) if len(main_nodes) > 1 else None
    branches = [LineString([xy(p), xy(q)]) for p, (q, length) in connected.items() if p not in main_edges]
    length = distances[best] if best != outlet else 0.0
    source_z = float(data[best]) if main is not None else np.nan
    out_z = float(data[outlet])
    drop_slope = (source_z - out_z) / length * 1000 if length > 0 else np.nan

    # --- TÍNH DIỆN TÍCH VÀ TỶ LỆ AO HỒ ---
    basin_area_km2 = float(mask.sum() * dx * dy / 1e6)
    lake_area_km2 = 0.0
    clipped_lakes = None

    if lake_union is not None and not lake_union.is_empty:
        inter = polygon.intersection(lake_union)
        if not inter.is_empty:
            lake_area_km2 = float(inter.area / 1e6)
            clipped_lakes = inter
    elif use_dem_sink and dep_depth is not None:
        sink_mask = mask & (dep_depth >= min_sink_depth)
        lake_area_km2 = float(sink_mask.sum() * dx * dy / 1e6)

    lake_area_km2 = min(lake_area_km2, basin_area_km2)
    lake_pct = (lake_area_km2 / basin_area_km2 * 100.0) if basin_area_km2 > 0 else 0.0

    return dict(
        geometry=polygon,
        DienTich=basin_area_km2,
        DT_AoHo=lake_area_km2,
        TyLe_AoHo=lake_pct,
        Doc_LV_pm=slope,
        Z_Nguon=source_z,
        Z_CuaXa=out_z,
        Dai_SC=length/1000,
        Doc_SC_pm=drop_slope,
        Dai_SNhanh=sum(e[1] for p, e in connected.items() if p not in main_edges)/1000,
        main=main,
        branches=branches,
        clipped_lakes=clipped_lakes
    )

from numba import njit
@njit(cache=False)
def _catchment_d8(directions, valid, outlet_row, outlet_col):
    rows, cols = directions.shape
    result = np.zeros((rows, cols), dtype=np.bool_)
    stack = np.empty(rows*cols, dtype=np.int64)
    stack[0] = outlet_row*cols + outlet_col; size = 1
    result[outlet_row, outlet_col] = True
    drs = (-1, -1, 0, 1, 1, 1, 0, -1)
    dcs = (0, 1, 1, 1, 0, -1, -1, -1)
    incoming = (4, 8, 16, 32, 64, 128, 1, 2)
    while size:
        size -= 1; index = stack[size]; r = index // cols; c = index % cols
        for k in range(8):
            nr = r + drs[k]; nc = c + dcs[k]
            if 0 <= nr < rows and 0 <= nc < cols and valid[nr, nc] and not result[nr, nc] and directions[nr, nc] == incoming[k]:
                result[nr, nc] = True; stack[size] = nr*cols + nc; size += 1
    return result

from heapq import heappush, heappop

@njit(cache=False)
def _fill_depressions_without_generators(elevation, valid):
    filled = elevation.copy()
    rows, cols = filled.shape
    visited = np.zeros((rows, cols), dtype=np.bool_)
    heap = [(0.0, 0, 0)]
    heap.pop()
    for r in range(rows):
        for c in range(cols):
            if not valid[r, c]: continue
            boundary = r == 0 or c == 0 or r == rows-1 or c == cols-1
            if not boundary:
                for dr in range(-1, 2):
                    for dc in range(-1, 2):
                        if not valid[r+dr, c+dc]: boundary = True
            if boundary:
                visited[r, c] = True
                heappush(heap, (filled[r, c], r, c))
    while len(heap) > 0:
        height, r, c = heappop(heap)
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                nr, nc = r+dr, c+dc
                if 0 <= nr < rows and 0 <= nc < cols and valid[nr, nc] and not visited[nr, nc]:
                    visited[nr, nc] = True
                    filled[nr, nc] = max(filled[nr, nc], height)
                    heappush(heap, (filled[nr, nc], nr, nc))
    return filled

def condition_depressions(dem):
    elevation, valid = valid_dem(dem)
    filled = dem.astype(np.float64)
    filled[:] = _fill_depressions_without_generators(elevation, valid)
    return filled

def catchment_d8(fdir, valid, outlet):
    if not valid[outlet]: raise ValueError('Cửa xả nằm trên NoData.')
    return _catchment_d8(np.asarray(fdir), np.asarray(valid, dtype=np.bool_), outlet[0], outlet[1])


try:
    import geopandas as gpd
    from shapely.geometry import shape, LineString, MultiLineString
    HAS_GPD = True
except ImportError:
    HAS_GPD = False

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")
ctk.ThemeManager.theme["CTkFont"]["family"]="Segoe UI" if os.name=="nt" else "DejaVu Sans"

# ================= BẢN ĐỒ GIẤY / DEM KẾT HỢP =================
def finite_value(value):
    result=float(str(value).strip().replace(',', '.'))
    if not np.isfinite(result):raise ValueError('Giá trị phải là số hữu hạn.')
    return result


def require_metric_crs(crs):
    crs=CRS.from_user_input(crs)
    if not crs.is_projected or len(crs.axis_info)<2 or any(abs(a.unit_conversion_factor-1)>1e-9 for a in crs.axis_info[:2]):
        raise ValueError('Cần CRS phẳng đơn vị mét để tính diện tích/chiều dài; không gán tọa độ mét cho EPSG:4326.')
    return crs


def fit_paper_affine(gcps):
    """Fit only training GCPs; report held-out residuals separately."""
    train=[p for p in gcps if not p.get('check',False)]
    if len(train)<3:raise ValueError('Cần ít nhất 3 điểm nắn không thẳng hàng (nên 6–12), chưa kể điểm kiểm tra.')
    source=np.array([[p['px'],p['py']] for p in train],dtype=float)
    target=np.array([[p['x'],p['y']] for p in train],dtype=float)
    if not np.isfinite(source).all() or not np.isfinite(target).all():raise ValueError('Điểm nắn có giá trị không hợp lệ.')
    center=source.mean(axis=0);scale=max(float(source.std()),1e-12)
    design=np.column_stack(((source-center)/scale,np.ones(len(source))))
    if np.linalg.matrix_rank(design)<3:raise ValueError('Điểm nắn thẳng hàng; chọn điểm phân bố quanh bản đồ.')
    coef=np.linalg.lstsq(design,target,rcond=None)[0];linear=coef[:2]/scale;origin=coef[2]-center@linear
    if abs(np.linalg.det(linear))<1e-15:raise ValueError('Tọa độ đích suy biến; kiểm tra X/Y.')
    matrix=np.array([[linear[0,0],linear[1,0],origin[0]], [linear[0,1],linear[1,1],origin[1]], [0.,0.,1.]])
    residual=[]
    for p in gcps:
        predicted=(matrix @ [p['px'],p['py'],1])[:2]
        residual.append(float(np.linalg.norm(predicted-[p['x'],p['y']])))
    return matrix,np.array(residual)


def pixel_world(matrix,points):
    points=np.asarray(points,dtype=float).reshape(-1,2)
    return (np.column_stack((points,np.ones(len(points)))) @ np.asarray(matrix).T)[:,:2]


class PaperMap:
    """One independently calibrated sheet. Do not treat a pasted collage as one grid."""
    def __init__(self,path,matrix=None,crs='',gcps=None):
        from PIL import Image
        self.path=os.path.abspath(path);self.gcps=list(gcps or [])
        self.matrix=None if matrix is None else np.array(matrix,dtype=float)
        self.crs=str(crs);self.artist=None;self.visible=True
        self.calibrated_signature=None
        with Image.open(path) as im:
            self.width,self.height=im.size
        if self.width*self.height>180_000_000:
            raise ValueError('Mảnh ảnh vượt 180 triệu pixel; cắt mảnh giữ nguyên độ phân giải trước khi nạp.')
        if matrix is None:
            try:
                with rasterio.open(path) as dataset:
                    if dataset.crs:
                        t=dataset.transform
                        self.matrix=np.array([[t.a,t.b,t.c+.5*(t.a+t.b)],[t.d,t.e,t.f+.5*(t.d+t.e)],[0,0,1.]])
                        self.crs=dataset.crs.to_wkt()
            except rasterio.errors.RasterioIOError:pass
            if self.matrix is None:
                base=os.path.splitext(path)[0]
                for suffix in ('.tfw','.jgw','.pgw','.jpgw','.wld'):
                    if os.path.isfile(base+suffix):
                        self.read_worldfile(base+suffix);break
                if os.path.isfile(base+'.prj'):
                    with open(base+'.prj',encoding='utf-8') as handle:self.crs=CRS.from_wkt(handle.read()).to_wkt()

    def read_worldfile(self,path):
        with open(path,encoding='utf-8-sig') as handle:values=[finite_value(v) for v in handle.read().split()]
        if len(values)!=6:raise ValueError('World File cần đúng 6 hệ số A,D,B,E,C,F.')
        a,d,b,e,c,f=values
        matrix=np.array([[a,b,c],[d,e,f],[0.,0.,1.]])
        if abs(a*e-b*d)<1e-15:raise ValueError('World File suy biến.')
        self.matrix=matrix;self.calibrated_signature=None

    def fit(self,crs):
        CRS.from_user_input(crs)
        matrix,errors=fit_paper_affine(self.gcps)
        self.matrix=matrix;self.crs=str(crs)
        self.calibrated_signature=json.dumps(self.gcps,sort_keys=True)
        return errors

    def check_ready(self):
        if self.matrix is None or not self.crs:raise ValueError('Mảnh bản đồ chưa nắn hoặc chưa khai báo CRS.')
        if self.matrix.shape!=(3,3) or not np.isfinite(self.matrix).all():raise ValueError('Ma trận nắn không hợp lệ.')
        if self.calibrated_signature is not None and self.calibrated_signature!=json.dumps(self.gcps,sort_keys=True):
            raise ValueError('Điểm khống chế đã đổi; tính lại phép nắn trước khi dùng.')
        return CRS.from_user_input(self.crs)

    def preview(self,target_crs,max_dimension=2400,target_bounds=None):
        """Reproject a visible source window; zoom reads source detail, not an upscaled overview."""
        from affine import Affine
        from rasterio.transform import from_bounds
        source_crs=self.check_ready();target_crs=CRS.from_user_input(target_crs)
        border=[]
        for u in np.linspace(-.5,self.width-.5,21):border.extend([[u,-.5],[u,self.height-.5]])
        for v in np.linspace(-.5,self.height-.5,21):border.extend([[-.5,v],[self.width-.5,v]])
        world=pixel_world(self.matrix,border)
        x,y=Transformer.from_crs(source_crs,target_crs,always_xy=True).transform(world[:,0],world[:,1],errcheck=True)
        left,right,bottom,top=float(np.min(x)),float(np.max(x)),float(np.min(y)),float(np.max(y))
        if not np.isfinite([left,right,bottom,top]).all() or right<=left or top<=bottom:raise ValueError('Phạm vi ảnh sau chuyển CRS không hợp lệ.')
        x0,y0,x1,y1=0,0,self.width,self.height
        if target_bounds is not None:
            l,r,b,t=target_bounds
            left,right,bottom,top=max(left,l),min(right,r),max(bottom,b),min(top,t)
            if right<=left or top<=bottom:return None,None
            corners=np.array([[left,bottom],[left,top],[right,top],[right,bottom]])
            sx,sy=Transformer.from_crs(target_crs,source_crs,always_xy=True).transform(corners[:,0],corners[:,1],errcheck=True)
            pixel=pixel_world(np.linalg.inv(self.matrix),np.column_stack((sx,sy)))
            x0=max(0,int(np.floor(pixel[:,0].min()))-3);y0=max(0,int(np.floor(pixel[:,1].min()))-3)
            x1=min(self.width,int(np.ceil(pixel[:,0].max()))+4);y1=min(self.height,int(np.ceil(pixel[:,1].max()))+4)
            if x1<=x0 or y1<=y0:return None,None
        ratio=min(1.,max_dimension/max(x1-x0,y1-y0))
        size=(max(1,round((x1-x0)*ratio)),max(1,round((y1-y0)*ratio)))
        with Image.open(self.path) as original:
            rgba=np.array(original.crop((x0,y0,x1,y1)).convert('RGBA').resize(size,Image.Resampling.BILINEAR))
        rgba[:,:,3]=np.where(np.min(rgba[:,:,:3],axis=2)>250,0,rgba[:,:,3])
        a,b,c=self.matrix[0];d,e,f=self.matrix[1]
        src_transform=Affine(a,b,c-.5*(a+b),d,e,f-.5*(d+e))*Affine.translation(x0,y0)*Affine.scale((x1-x0)/size[0],(y1-y0)/size[1])
        ratio=max_dimension/max(right-left,top-bottom)
        # Do not allocate a needlessly large raster for a small source window.
        ratio=min(ratio,max(size[0]/(right-left),size[1]/(top-bottom)))
        w=max(1,round((right-left)*ratio));h=max(1,round((top-bottom)*ratio))
        dst_transform=from_bounds(left,bottom,right,top,w,h)
        out=np.zeros((h,w,4),dtype=np.uint8)
        for channel in range(4):
            reproject(rgba[:,:,channel],out[:,:,channel],src_transform=src_transform,src_crs=source_crs,
                      dst_transform=dst_transform,dst_crs=target_crs,
                      resampling=Resampling.nearest if channel==3 else Resampling.bilinear)
        return out,[left,right,bottom,top]


def apply_paper_constraints(dem,features,burn_depth=0.,ridge_height=0.):
    """Change ROUTING terrain only, not source elevations used by statistics."""
    from rasterio.features import rasterize
    data,valid=valid_dem(dem)
    if burn_depth<0 or ridge_height<0 or max(burn_depth,ridge_height)>100:
        raise ValueError('Mức điều chỉnh DEM phải trong 0–100 m; nên chọn nhỏ và kiểm chứng tại hiện trường.')
    rivers=[(LineString(f['points']),1) for f in features if f['kind'] in ('river','main')]
    ridges=[(LineString(f['points']),1) for f in features if f['kind']=='ridge']
    shape=data.shape;transform=dem.affine
    river_mask=(rasterize(rivers,out_shape=shape,transform=transform,all_touched=True)>0)&valid if rivers and burn_depth else np.zeros(shape,bool)
    ridge_mask=(rasterize(ridges,out_shape=shape,transform=transform,all_touched=True)>0)&valid if ridges and ridge_height else np.zeros(shape,bool)
    if np.any(river_mask & ridge_mask):raise ValueError('Đường sông và đường phân thủy cùng đi qua một ô DEM; sửa điểm giao trước khi áp dụng.')
    routed=dem.astype(np.float64)
    routed[river_mask]=data[river_mask]-burn_depth
    routed[ridge_mask]=data[ridge_mask]+ridge_height
    return routed,int(river_mask.sum()),int(ridge_mask.sum())


def manual_basin_metrics(polygon,basin_id,features,dem=None,outlet=None,lakes=None):
    """Exact polygon area; no fabricated slopes or elevations without data."""
    from rasterio.features import geometry_mask
    if polygon.is_empty or not polygon.is_valid or polygon.area<=0:
        raise ValueError('Ranh lưu vực tự giao hoặc không có diện tích; chỉnh đỉnh trước khi chốt.')
    result=dict(ID_LuuVuc=int(basin_id),geometry=polygon,DienTich=polygon.area/1e6,
                DT_AoHo=np.nan,TyLe_AoHo=np.nan,Doc_LV_pm=np.nan,Z_Nguon=np.nan,Z_CuaXa=np.nan,
                Dai_SC=np.nan,Doc_SC_pm=np.nan,Dai_SNhanh=np.nan,Nguon='BAN_DO_GIAY',PhuDEM_pct=np.nan)
    if lakes is not None and not lakes.is_empty:
        lake_area=polygon.intersection(lakes).area
        result.update(DT_AoHo=lake_area/1e6,TyLe_AoHo=100*lake_area/polygon.area)
    sample=None
    if dem is not None:
        data,valid=valid_dem(dem);transform=dem.affine
        mask=geometry_mask([polygon.__geo_interface__],data.shape,transform,invert=True)
        selected=mask & valid
        if mask.any():
            coverage=selected.sum()*abs(transform.a*transform.e)/polygon.area
            result['PhuDEM_pct']=min(100.,100*coverage)
            if coverage>=.98 and selected.any():
                slope=terrain_slope(data,valid,abs(transform.a),abs(transform.e))[selected]
                result['Doc_LV_pm']=float(np.nanmean(slope)) if np.isfinite(slope).any() else np.nan
        def sample(xy):
            col,row=~transform * xy;row,col=int(np.floor(row)),int(np.floor(col))
            return float(data[row,col]) if 0<=row<data.shape[0] and 0<=col<data.shape[1] and valid[row,col] else np.nan
        if outlet is not None:result['Z_CuaXa']=sample(outlet)
    mains=[f for f in features if f['kind']=='main' and f.get('basin_id')==basin_id]
    if len(mains)>1:raise ValueError(f'LV_{basin_id} có nhiều sông chính; giữ đúng một đường đã kiểm chứng.')
    if mains:
        main=mains[0];line=LineString(main['points'])
        if not polygon.buffer(1e-7).covers(line):raise ValueError(f'Sông chính LV_{basin_id} vượt ra ngoài ranh; kiểm tra lại.')
        length=line.length;result['Dai_SC']=length/1000
        if sample is not None:
            start_z=sample(line.coords[0]);end_z=sample(line.coords[-1])
        else:
            start_z=main.get('z_start',np.nan);end_z=main.get('z_end',np.nan)
            start_z=np.nan if start_z is None else float(start_z);end_z=np.nan if end_z is None else float(end_z)
        result['Z_Nguon']=start_z
        if outlet is None or Point(outlet).distance(Point(line.coords[-1]))<max(1.,line.length*.01):
            result['Z_CuaXa']=end_z
            if length>0 and np.isfinite(start_z) and np.isfinite(end_z):result['Doc_SC_pm']=(start_z-end_z)/length*1000
    return result


def contours_to_dem(vector_path,destination,target_crs,resolution=10.,elevation_field='ELEVATION',source_crs=None,layer_filter='*'):
    """Linear TIN only inside the convex hull; no invented exterior elevations."""
    import fnmatch
    from scipy.interpolate import LinearNDInterpolator
    from shapely import get_coordinates
    from rasterio.transform import from_origin
    target_crs=require_metric_crs(target_crs);resolution=finite_value(resolution)
    if resolution<=0:raise ValueError('Cỡ ô nội suy phải >0 m.')
    samples=[];line_count=0;source_lines=[]
    def collect(geometry,z=None):
        nonlocal line_count
        if geometry.is_empty:return
        if geometry.geom_type.startswith('Multi') or geometry.geom_type=='GeometryCollection':
            for part in geometry.geoms:collect(part,z)
            return
        if geometry.geom_type not in ('LineString','Point'):return
        coords=get_coordinates(geometry,include_z=True)
        if z is None:
            if not np.isfinite(coords[:,2]).all():raise ValueError('Có đối tượng chưa có Z. Chọn đúng cột cao độ hoặc dữ liệu 3D đã kiểm tra.')
            if geometry.geom_type=='LineString' and np.ptp(coords[:,2])>.05:raise ValueError('Đường đồng mức có Z thay đổi dọc nét; kiểm tra dữ liệu nguồn.')
            z=float(np.mean(coords[:,2]))
        z=finite_value(z)
        if geometry.geom_type=='Point':samples.append((geometry.x,geometry.y,z));return
        source_lines.append((LineString(coords[:,:2]),z))
        line_count+=1
        for i in range(len(coords)-1):
            a,b=coords[i,:2],coords[i+1,:2]
            n=max(1,int(np.ceil(np.linalg.norm(b-a)/(2*resolution))))
            if n>150000 or len(samples)+n>150000:raise ValueError('Quá 150.000 điểm nội suy; cắt vùng nhỏ hơn hoặc tăng cỡ ô.')
            for t in np.linspace(0.,1.,n+1):
                xy=a*(1-t)+b*t;samples.append((xy[0],xy[1],z))
    if str(vector_path).lower().endswith('.dxf'):
        import ezdxf
        if source_crs is None:raise ValueError('DXF không có CRS đáng tin cậy; khai báo CRS nguồn của DXF.')
        transform=Transformer.from_crs(source_crs,target_crs,always_xy=True)
        for entity in ezdxf.readfile(vector_path).modelspace():
            if not fnmatch.fnmatchcase(entity.dxf.layer,layer_filter):continue
            coords=[]
            if entity.dxftype()=='POLYLINE':coords=[tuple(v.dxf.location) for v in entity.vertices]
            elif entity.dxftype()=='LWPOLYLINE':
                if any(abs(p[2])>1e-12 for p in entity.get_points('xyb')):
                    raise ValueError('DXF có cung bulge; chuyển cung thành polyline đủ dày trước khi nội suy.')
                z=float(entity.dxf.elevation);coords=[(p[0],p[1],z) for p in entity.get_points('xy')]
            elif entity.dxftype()=='POINT':coords=[tuple(entity.dxf.location)]
            if coords:
                if entity.dxftype() in ('POLYLINE','LWPOLYLINE') and (getattr(entity,'is_closed',False) or getattr(entity,'closed',False)):
                    if coords[-1]!=coords[0]:coords.append(coords[0])
                points=np.array(coords);x,y=transform.transform(points[:,0],points[:,1],errcheck=True)
                world=np.column_stack((x,y,points[:,2]))
                collect(Point(world[0]) if len(world)==1 else LineString(world))
    else:
        frame=gpd.read_file(vector_path)
        if frame.crs is None:
            if source_crs is None:raise ValueError('Lớp đồng mức thiếu CRS. Khai báo CRS nguồn chính xác.')
            frame=frame.set_crs(source_crs)
        frame=frame.to_crs(target_crs)
        for _,row in frame.iterrows():
            z=finite_value(row[elevation_field]) if elevation_field and elevation_field in frame.columns else None
            collect(row.geometry,z)
    if len(samples)<3:raise ValueError('Không đủ đường/điểm có cao độ để nội suy.')
    if source_lines:
        from shapely.strtree import STRtree
        tree=STRtree([line for line,z in source_lines])
        for i,(line,z) in enumerate(source_lines):
            for j in tree.query(line,predicate='intersects'):
                j=int(j)
                if j>i and abs(z-source_lines[j][1])>.05:
                    raise ValueError('Đường đồng mức khác cao độ giao/chồng nhau; sửa dữ liệu trước khi tạo DEM.')
    samples=np.array(samples,dtype=float)
    if not np.isfinite(samples).all():raise ValueError('Tọa độ/cao độ nguồn có NaN hoặc vô cực.')
    keys=np.round(samples[:,:2],3);unique,indices,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    minima=np.full(len(unique),np.inf);maxima=np.full(len(unique),-np.inf)
    np.minimum.at(minima,inverse,samples[:,2]);np.maximum.at(maxima,inverse,samples[:,2])
    if np.any(maxima-minima>.05):raise ValueError('Cùng một vị trí có nhiều cao độ khác nhau; sửa đường đồng mức giao/chồng trước.')
    samples=samples[indices]
    if np.unique(np.round(samples[:,2],3)).size<2:raise ValueError('Mọi đường có cùng cao độ; không thể suy ra địa hình để chia lưu vực.')
    center=samples[:,:2].mean(axis=0)
    if np.linalg.matrix_rank(samples[:,:2]-center)<2:raise ValueError('Điểm cao độ thẳng hàng; không thể tạo bề mặt 2D.')
    low=samples[:,:2].min(axis=0);high=samples[:,:2].max(axis=0)
    width=max(1,int(np.ceil((high[0]-low[0])/resolution)));height=max(1,int(np.ceil((high[1]-low[1])/resolution)))
    if width*height>4_000_000:raise ValueError('DEM nội suy vượt 4 triệu ô. Tăng cỡ ô hoặc cắt vùng nguồn.')
    transform=from_origin(low[0],high[1],resolution,resolution)
    interpolator=LinearNDInterpolator(samples[:,:2]-center,samples[:,2],fill_value=np.nan)
    profile=dict(driver='GTiff',height=height,width=width,count=1,dtype='float32',crs=target_crs,
                 transform=transform,nodata=-999999.,compress='deflate')
    valid_count=0
    fd,temp_destination=tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(destination)),suffix='.tif')
    os.close(fd)
    try:
        with rasterio.open(temp_destination,'w',**profile) as dst:
            for row in range(0,height,256):
                count=min(256,height-row)
                xs=low[0]+(np.arange(width)+.5)*resolution;ys=high[1]-(row+np.arange(count)+.5)*resolution
                x,y=np.meshgrid(xs,ys)
                values=interpolator(x-center[0],y-center[1]);valid_count+=np.isfinite(values).sum()
                dst.write(np.where(np.isfinite(values),values,-999999.).astype(np.float32),1,
                          window=rasterio.windows.Window(0,row,width,count))
            dst.update_tags(SOURCE='INTERPOLATED_CONTOURS_NOT_SURVEYED_DEM',CONTOUR_FILE=os.path.basename(vector_path),
                            METHOD='Linear TIN; no extrapolation outside convex hull',VERTICAL_UNITS='m')
        if valid_count<4:raise ValueError('Không đủ ô hợp lệ trong miền nội suy; giảm cỡ ô hoặc bổ sung số liệu.')
        os.replace(temp_destination,destination)
    finally:
        if os.path.exists(temp_destination):os.unlink(temp_destination)
    return dict(points=len(samples),lines=line_count,width=width,height=height,valid=int(valid_count),path=str(destination))


class GeoCatchmentApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("GeoCatchment Pro V8 — Bản đồ giấy + DEM + Kiểm chứng ranh lưu vực")
        self.geometry("1280x860")
        self.minsize(1000, 720)

        self.grid_obj = None
        self.dem = None
        self.flooded_dem = None
        self.dep_depth = None
        self.lake_gdf = None
        self.dem_workspace = tempfile.TemporaryDirectory(prefix="luuvuc-dem-")
        self.fdir = None
        self.acc = None
        self.extent = []
        self.shp_paths = []
        self.lake_shp_path = ""

        self.xmin = self.xmax = self.ymin = self.ymax = 0

        self.app_state = {
            'points': [],
            'scatter_points': None,
            'catchment_overlay': None,
            'sink_overlay': None,
            'lake_base_plot': [],
            'lake_basin_plot': [],
            'current_lake_pts': [],     # Các đỉnh đang chấm khi vẽ thêm hồ
            'temp_lake_line': None,     # Đường nối tạm khi đang vẽ hồ
            'gdf_out': None,
            'gdf_lakes_out': None,
            'snapped_texts': [],
            'gdf_streams': None,
            'stream_plot': [],
            'mode': 'add'
        }

        self.paper_maps=[];self.paper_basins=[];self.paper_features=[];self.paper_cache={}
        self.map_crs=None;self.paper_artists=[];self.paper_mode=None;self.paper_temp=[]
        self.paper_active_id=None;self.paper_drag=None;self.paper_cursor=None;self.paper_history=[]
        self.paper_busy=False;self.paper_queue=queue.Queue();self.project_dirty=False
        self.paper_view_job=None;self.paper_view_updating=False
        self.paper_burn=tk.StringVar(value='2');self.paper_raise=tk.StringVar(value='2')
        self.applied_paper_signature=None
        self.dem_provenance="DEM"
        self.setup_ui()
        self.setup_paper_tools()
        self.protocol('WM_DELETE_WINDOW',self.paper_close)

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkScrollableFrame(self, width=360, corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_rowconfigure(11, weight=1)

        lbl_title1 = ctk.CTkLabel(self.left_panel, text="1. DỮ LIỆU ĐẦU VÀO", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_title1.grid(row=0, column=0, padx=16, pady=(10, 2), sticky="w")

        self.txt_dem = ctk.CTkEntry(self.left_panel, placeholder_text="File DEM (.tif)", width=240)
        self.txt_dem.grid(row=1, column=0, padx=16, pady=2, sticky="w")
        ctk.CTkButton(self.left_panel, text="Duyệt", width=60, command=self.chon_file_dem).grid(row=1, column=0, padx=16, pady=2, sticky="e")

        # Khung chọn file Ao hồ (.shp, .kml, .kmz, .geojson)
        self.frame_lake = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_lake.grid(row=2, column=0, padx=16, pady=2, sticky="we")
        self.txt_lake = ctk.CTkEntry(self.frame_lake, placeholder_text="File Ao hồ (.shp/.kml/.kmz/.geojson)", width=215)
        self.txt_lake.pack(side="left")
        ctk.CTkButton(self.frame_lake, text="🗑", width=28, fg_color="#e74c3c", hover_color="#c0392b", command=self.xoa_file_aoho).pack(side="right", padx=(3, 0))
        ctk.CTkButton(self.frame_lake, text="Chọn", width=52, command=self.chon_file_aoho).pack(side="right")

        # Khung 2 nút: Tải OSM & Tự động dò mặt hồ phẳng từ DEM
        self.frame_auto_lake = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_auto_lake.grid(row=3, column=0, padx=16, pady=2, sticky="we")

        self.btn_osm_lake = ctk.CTkButton(
            self.frame_auto_lake,
            text="🌐 1. Tải hồ OSM",
            width=145,
            height=28,
            fg_color="#16a085",
            hover_color="#1abc9c",
            font=ctk.CTkFont(size=11, weight="bold"),
            state="disabled",
            command=self.tai_aoho_tu_osm
        )
        self.btn_osm_lake.pack(side="left")

        self.btn_detect_flat = ctk.CTkButton(
            self.frame_auto_lake,
            text="🔍 2. Dò mặt hồ DEM",
            width=155,
            height=28,
            fg_color="#8e44ad",
            hover_color="#9b59b6",
            font=ctk.CTkFont(size=11, weight="bold"),
            state="disabled",
            command=self.do_mat_ho_phang_dem
        )
        self.btn_detect_flat.pack(side="right")

        self.frame_nen = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_nen.grid(row=4, column=0, padx=16, pady=2, sticky="we")

        self.btn_chon_nen = ctk.CTkButton(self.frame_nen, text="➕ Thêm lớp nền", width=140, height=28, command=self.chon_file_nen)
        self.btn_chon_nen.pack(side="left")

        self.btn_xoa_nen = ctk.CTkButton(self.frame_nen, text="🗑 Xóa nền", width=105, height=28, fg_color="#e74c3c", hover_color="#c0392b", command=self.xoa_file_nen)
        self.btn_xoa_nen.pack(side="right")

        self.txt_list_nen = ctk.CTkTextbox(self.left_panel, height=42, width=300)
        self.txt_list_nen.grid(row=5, column=0, padx=16, pady=(0, 2), sticky="we")
        self.txt_list_nen.insert("1.0", "Chưa có bản đồ nền nào...")
        self.txt_list_nen.configure(state="disabled")

        self.btn_load = ctk.CTkButton(self.left_panel, text="🔄 NẠP VÀ XỬ LÝ BẢN ĐỒ", height=34, fg_color="#2980b9", hover_color="#3498db", font=ctk.CTkFont(weight="bold"), command=self.load_data)
        self.btn_load.grid(row=6, column=0, padx=16, pady=(6, 8), sticky="we")

        lbl_title2 = ctk.CTkLabel(self.left_panel, text="2. CÔNG CỤ TƯƠNG TÁC", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_title2.grid(row=7, column=0, padx=16, pady=2, sticky="w")

        self.tools_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.tools_frame.grid(row=8, column=0, padx=16, sticky="nwe")

        self.btn_add = ctk.CTkButton(self.tools_frame, text="📍 CHẾ ĐỘ: THÊM CỬA XẢ", height=30, state="disabled", command=lambda: self.set_mode('add'))
        self.btn_add.pack(pady=2, fill="x")

        self.btn_del = ctk.CTkButton(self.tools_frame, text="✖ CHẾ ĐỘ: XÓA CỬA XẢ", height=30, state="disabled", command=lambda: self.set_mode('delete'))
        self.btn_del.pack(pady=2, fill="x")

        # Chế độ vẽ thêm hồ và xóa hồ trực tiếp trên bản đồ
        self.frame_draw_lake = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
        self.frame_draw_lake.pack(pady=2, fill="x")

        self.btn_draw_lake = ctk.CTkButton(
            self.frame_draw_lake,
            text="✏️ VẼ THÊM HỒ (Chuột trái/phải)",
            width=210,
            height=30,
            state="disabled",
            command=lambda: self.set_mode('draw_lake')
        )
        self.btn_draw_lake.pack(side="left")

        self.btn_del_lake = ctk.CTkButton(
            self.frame_draw_lake,
            text="✖ Xóa 1 Hồ",
            width=88,
            height=30,
            state="disabled",
            command=lambda: self.set_mode('del_lake')
        )
        self.btn_del_lake.pack(side="right")

        self.frame_thresh = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
        self.frame_thresh.pack(pady=(5, 2), fill="x")
        ctk.CTkLabel(self.frame_thresh, text="Ngưỡng sông (số ô góp nước):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.txt_thresh = ctk.CTkEntry(self.frame_thresh, width=65, height=26)
        self.txt_thresh.insert(0, "500")
        self.txt_thresh.pack(side="right")
        self.txt_thresh.bind("<KeyRelease>", lambda event: self.invalidate_results())

        self.var_use_dem_sink = tk.BooleanVar(value=False)
        self.chk_dem_sink = ctk.CTkCheckBox(
            self.tools_frame,
            text="Chỉ dùng hố trũng DEM (khi không dùng lớp Hồ)",
            variable=self.var_use_dem_sink,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18,
            command=self.invalidate_results
        )
        self.chk_dem_sink.pack(pady=(3, 1), anchor="w")

        self.frame_sink = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
        self.frame_sink.pack(pady=(1, 3), fill="x")
        ctk.CTkLabel(self.frame_sink, text="Ngưỡng sâu trũng DEM (m):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.txt_sink_depth = ctk.CTkEntry(self.frame_sink, width=65, height=26)
        self.txt_sink_depth.insert(0, "0.5")
        self.txt_sink_depth.pack(side="right")
        self.txt_sink_depth.bind("<KeyRelease>", lambda event: self.invalidate_results())

        self.btn_calc = ctk.CTkButton(self.tools_frame, text="TÍNH LƯU VỰC, SÔNG & AO HỒ", fg_color="#d35400", hover_color="#e67e22", font=ctk.CTkFont(weight="bold"), height=36, state="disabled", command=self.chay_chia_luu_vuc)
        self.btn_calc.pack(pady=(6, 2), fill="x")

        self.btn_clear = ctk.CTkButton(self.tools_frame, text="🗑️ Làm sạch cửa xả", fg_color="#7f8c8d", hover_color="#95a5a6", height=28, state="disabled", command=self.clear_all)
        self.btn_clear.pack(pady=2, fill="x")

        self.frame_export = ctk.CTkFrame(self.left_panel, corner_radius=8, fg_color="#ecf0f1")
        self.frame_export.grid(row=9, column=0, padx=16, pady=(6, 4), sticky="nwe")

        ctk.CTkLabel(self.frame_export, text="3. XUẤT DỮ LIỆU", font=ctk.CTkFont(size=14, weight="bold"), text_color="#2c3e50").pack(anchor="w", padx=10, pady=(5, 2))

        ctk.CTkLabel(self.frame_export, text="Hệ tọa độ (CRS):", font=ctk.CTkFont(size=12), text_color="#2c3e50").pack(anchor="w", padx=10)
        self.crs_options = [
            "Giữ nguyên CRS tính toán",
            "EPSG:4326 (WGS 84 - Địa lý)",
            "EPSG:32648 (UTM Zone 48N)",
            "EPSG:3405 (VN-2000 / UTM 48N)",
            "EPSG:3406 (VN-2000 / UTM 49N)"
        ]
        self.cmb_crs = ctk.CTkComboBox(self.frame_export, values=self.crs_options, width=290, height=26, fg_color="white", text_color="black")
        self.cmb_crs.pack(padx=10, pady=3)

        self.btn_save = ctk.CTkButton(self.frame_export, text="💾 LƯU SHAPEFILE KẾT QUẢ", fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(weight="bold"), height=34, state="disabled", command=self.luu_ket_qua)
        self.btn_save.pack(padx=10, pady=(2, 8), fill="x")

        self.lbl_status = ctk.CTkLabel(self.left_panel, text="💡 Sẵn sàng. Hãy chọn file DEM rồi nhấn Nạp bản đồ.", text_color="gray", wraplength=310, justify="left")
        self.lbl_status.grid(row=10, column=0, padx=16, pady=6, sticky="sw")

        self.right_panel = ctk.CTkFrame(self, corner_radius=0, fg_color="white")
        self.right_panel.grid(row=0, column=1, sticky="nsew")

        self.fig = Figure(figsize=(8, 6))
        self.ax = self.fig.add_subplot(111)
        self.fig.patch.set_facecolor('#ffffff')
        self.fig.subplots_adjust(left=0.05, right=0.98, top=0.95, bottom=0.05)
        self.ax.axis('off')
        self.ax.text(0.5, 0.5, "Khu vực hiển thị Bản đồ", ha='center', va='center', color='gray', fontsize=14)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.right_panel)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.toolbar_frame = ctk.CTkFrame(self.right_panel, corner_radius=0, height=40)
        self.toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.toolbar_frame)
        self.toolbar.update()

        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)

    def chon_file_dem(self):
        p = filedialog.askopenfilename(filetypes=(("TIF files", "*.tif;*.tiff"), ("All", "*.*")))
        if p:
            self.txt_dem.delete(0, "end"); self.txt_dem.insert(0, p)
            self.invalidate_results()
            self.btn_calc.configure(state="disabled")
            self.btn_osm_lake.configure(state="disabled")
            self.btn_detect_flat.configure(state="disabled")
            self.grid_obj = self.dem = self.fdir = self.acc = self.dep_depth = self.flooded_dem = None

    def chon_file_aoho(self):
        p = filedialog.askopenfilename(
            title="Chọn lớp Ao hồ / Mặt nước (.shp, .kml, .kmz, .geojson)",
            filetypes=(("Vector & Google Earth", "*.shp;*.kml;*.kmz;*.geojson;*.gpkg"), ("All", "*.*"))
        )
        if p:
            self.lake_shp_path = p
            self.txt_lake.delete(0, "end")
            self.txt_lake.insert(0, p)
            self.invalidate_results()
            if self.grid_obj is not None:
                self.nap_file_aoho_da_chon()

    def xoa_file_aoho(self):
        self.lake_shp_path = ""
        self.lake_gdf = None
        self.txt_lake.delete(0, "end")
        self.xoa_hien_thi_aoho_nen()
        self.invalidate_results()
        self.canvas.draw_idle()
        self.update_status("🗑 Đã xóa toàn bộ lớp Ao hồ.")

    def xoa_hien_thi_aoho_nen(self):
        for artist in self.app_state['lake_base_plot']:
            try: artist.remove()
            except: pass
        self.app_state['lake_base_plot'] = []

    def ve_lop_aoho_nen(self):
        self.xoa_hien_thi_aoho_nen()
        if self.lake_gdf is not None and not self.lake_gdf.empty:
            before = set(self.ax.collections) | set(self.ax.patches)
            self.lake_gdf.plot(ax=self.ax, facecolor='#00a8ff', edgecolor='#0052cc', alpha=0.55, linewidth=0.8, zorder=2.5)
            after = set(self.ax.collections) | set(self.ax.patches)
            self.app_state['lake_base_plot'] = list(after - before)
            self.canvas.draw_idle()

    def gop_them_ao_ho(self, gdf_new, label_prefix="[Kết hợp]"):
        """Gộp lớp hồ mới vào lớp hồ hiện có mà không làm mất dữ liệu hồ đã tải trước đó."""
        if gdf_new is None or gdf_new.empty:
            return
        if self.lake_gdf is None or self.lake_gdf.empty:
            all_geoms = list(gdf_new.geometry)
        else:
            all_geoms = list(self.lake_gdf.geometry) + list(gdf_new.geometry)
        merged = unary_union(all_geoms)
        if merged.geom_type == 'Polygon':
            geom_list = [merged]
        elif merged.geom_type == 'MultiPolygon':
            geom_list = list(merged.geoms)
        else:
            geom_list = [g for g in getattr(merged, 'geoms', []) if g.geom_type in ('Polygon', 'MultiPolygon')]

        self.lake_gdf = gpd.GeoDataFrame({'geometry': geom_list}, crs=self.grid_obj.crs)
        self.txt_lake.delete(0, "end")
        self.txt_lake.insert(0, f"{label_prefix} {len(self.lake_gdf)} mặt hồ")
        self.ve_lop_aoho_nen()
        self.invalidate_results()

    def nap_file_aoho_da_chon(self):
        lake_path_input = self.txt_lake.get().strip()
        if not lake_path_input or lake_path_input.startswith("["):
            return
        if not os.path.exists(lake_path_input):
            raise ValueError(f"Không tìm thấy file Ao hồ: {lake_path_input}")

        if lake_path_input.lower().endswith(('.kml', '.kmz')):
            gdf_lake = read_kml_kmz_polygons(lake_path_input, self.grid_obj.crs)
        else:
            gdf_lake = gpd.read_file(lake_path_input)
            if gdf_lake.crs is None:
                raise ValueError("Lớp Shapefile Ao hồ thiếu hệ tọa độ (CRS)!")
            if self.grid_obj.crs and gdf_lake.crs != self.grid_obj.crs:
                gdf_lake = gdf_lake.to_crs(self.grid_obj.crs)

        gdf_lake = gdf_lake[gdf_lake.geometry.notnull() & gdf_lake.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
        if gdf_lake.empty:
            raise ValueError("File Ao hồ không chứa đối tượng vùng (Polygon/MultiPolygon) hợp lệ!")
        self.gop_them_ao_ho(gdf_lake, label_prefix="[File+OSM]")
        self.update_status(f"✅ Đã gộp thêm ao hồ từ file: {os.path.basename(lake_path_input)} (Tổng: {len(self.lake_gdf)} hồ)")

    def tai_aoho_tu_osm(self):
        if self.grid_obj is None:
            messagebox.showwarning("Cảnh báo", "Hãy nạp bản đồ DEM trước khi tải Ao hồ từ OSM!")
            return
        try:
            self.update_status("🌐 Đang kết nối OpenStreetMap để tải các hồ chứa, ao đập thực tế...")
            gdf_osm = fetch_osm_water_polygons(self.grid_obj.bbox, self.grid_obj.crs)
            if gdf_osm.empty:
                messagebox.showinfo("Thông báo", "Không tìm thấy hồ chứa nào trên OSM trong vùng này.\nHãy bấm nút '🔍 2. Dò mặt hồ DEM' hoặc dùng nút '✏️ VẼ THÊM HỒ'!")
                return
            self.gop_them_ao_ho(gdf_osm, label_prefix="[OSM]")
            tong_dt = self.lake_gdf.geometry.area.sum() / 1e6
            self.update_status(f"✅ Đã tải & gộp {len(self.lake_gdf)} mặt hồ (Tổng DT: {tong_dt:.2f} km²).")
        except Exception as e:
            messagebox.showerror("Lỗi tải dữ liệu OSM", str(e))

    def do_mat_ho_phang_dem(self):
        """Dò tự động các mặt hồ phẳng trên DEM (những hồ chưa được vẽ trên OSM như hồ ở LV_1)."""
        if self.grid_obj is None or self.dem is None:
            messagebox.showwarning("Cảnh báo", "Hãy nạp bản đồ DEM trước!")
            return
        try:
            self.update_status("🔍 Đang quét các vùng mặt nước phẳng (Hydro-Flat) dọc mạng lưới suối trên DEM...")
            gdf_flat = detect_water_flats_from_dem(
                self.dem, self.flooded_dem, self.acc, self.dem.affine, self.grid_obj.crs,
                max_slope_pm=18.0, min_area_ha=1.5
            )
            if gdf_flat.empty:
                messagebox.showinfo("Kết quả dò DEM", "Không phát hiện thêm vùng mặt nước phẳng lớn nào trên DEM.\nBạn có thể dùng nút '✏️ VẼ THÊM HỒ' để chấm trực tiếp hồ lên bản đồ!")
                return
            self.gop_them_ao_ho(gdf_flat, label_prefix="[OSM+DEM Flat]")
            self.update_status(f"✅ Đã dò thêm {len(gdf_flat)} mặt hồ phẳng từ DEM! Tổng số hồ hiện tại: {len(self.lake_gdf)}.")
            messagebox.showinfo(
                "Đã dò mặt hồ phẳng từ DEM",
                f"Đã phát hiện và bổ sung {len(gdf_flat)} vùng mặt hồ phẳng từ địa hình DEM!\n"
                "• Nếu có vùng phẳng nào không phải hồ, bạn chỉ cần chọn nút '✖ Xóa 1 Hồ' rồi click vào vùng đó để xóa.\n"
                "• Hoặc chọn '✏️ VẼ THÊM HỒ' để khoanh chính xác lòng hồ bạn muốn."
            )
        except Exception as e:
            messagebox.showerror("Lỗi dò mặt hồ DEM", str(e))

    def chon_file_nen(self):
        paths = filedialog.askopenfilenames(title="Chọn các lớp bản đồ nền", filetypes=(("Shapefiles", "*.shp"), ("All", "*.*")))
        if paths:
            for p in paths:
                if p not in self.shp_paths:
                    self.shp_paths.append(p)
            self.cap_nhat_hien_thi_nen()

    def xoa_file_nen(self):
        self.shp_paths = []
        self.cap_nhat_hien_thi_nen()

    def cap_nhat_hien_thi_nen(self):
        self.txt_list_nen.configure(state="normal")
        self.txt_list_nen.delete("1.0", "end")
        if not self.shp_paths:
            self.txt_list_nen.insert("1.0", "Chưa có bản đồ nền nào...")
        else:
            for i, p in enumerate(self.shp_paths):
                ten_file = os.path.basename(p)
                self.txt_list_nen.insert("end", f"{i+1}. {ten_file}\n")
        self.txt_list_nen.configure(state="disabled")

    def update_status(self, msg):
        self.lbl_status.configure(text=msg)
        self.update()

    def clear_temp_lake_drawing(self):
        self.app_state['current_lake_pts'] = []
        if self.app_state['temp_lake_line'] is not None:
            try: self.app_state['temp_lake_line'].remove()
            except: pass
            self.app_state['temp_lake_line'] = None
        self.canvas.draw_idle()

    def set_mode(self, mode):
        self.clear_temp_lake_drawing()
        self.app_state['mode'] = mode
        self.paper_mode=None;self.paper_temp=[]

        # Reset button styles
        for btn in (self.btn_add, self.btn_del, self.btn_draw_lake, self.btn_del_lake):
            btn.configure(fg_color="transparent", border_width=1, border_color="gray")

        if mode == 'add':
            self.btn_add.configure(fg_color="#3498db", border_width=0)
            self.update_status("👉 Chế độ THÊM CỬA XẢ: Click chuột trái lên sông/cầu để thêm cửa xả.")
        elif mode == 'delete':
            self.btn_del.configure(fg_color="#e74c3c", border_width=0)
            self.update_status("👉 Chế độ XÓA CỬA XẢ: Click vào điểm cửa xả màu đỏ để xóa.")
        elif mode == 'draw_lake':
            self.btn_draw_lake.configure(fg_color="#0097e6", border_width=0)
            self.update_status("✏️ Chế độ VẼ THÊM HỒ: Click CHUỘT TRÁI quanh chu vi hồ (theo nhánh suối) -> Click CHUỘT PHẢI để khép kín hồ!")
        elif mode == 'del_lake':
            self.btn_del_lake.configure(fg_color="#c0392b", border_width=0)
            self.update_status("✖ Chế độ XÓA 1 HỒ: Click chuột trái trực tiếp vào vùng hồ màu xanh nào bạn muốn xóa bỏ.")

    def _load_dem_data(self):
        dem_path = self.txt_dem.get()
        if not dem_path:
            messagebox.showwarning("Cảnh báo", "Bạn chưa chọn file DEM!")
            return

        try:
            self.update_status("⏳ Đang đọc và xử lý DEM... Xin chờ!")

            self.btn_calc.configure(state="disabled")
            self.btn_save.configure(state="disabled")
            with rasterio.open(dem_path) as source_dataset:
                self.dem_provenance='DEM_TIN' if source_dataset.tags().get('SOURCE')=='INTERPOLATED_CONTOURS_NOT_SURVEYED_DEM' else 'DEM'
            dem_path = metric_dem(dem_path, os.path.join(self.dem_workspace.name, "dem_metric.tif"))
            self.grid_obj = hydrology_grid_class().from_raster(dem_path)
            self.dem = self.grid_obj.read_raster(dem_path)
            self._switch_map_crs(self.grid_obj.crs)
            xmin, ymin, xmax, ymax = self.grid_obj.bbox
            self.cols, self.rows = self.grid_obj.shape[1], self.grid_obj.shape[0]
            self.cell_w, self.cell_h = (xmax - xmin) / self.cols, (ymax - ymin) / self.rows
            self.extent = [xmin, xmax, ymin, ymax]

            self.xmin, self.xmax, self.ymin, self.ymax = xmin, xmax, ymin, ymax

            self.update_status("Đang xử lý hố trũng bằng Priority-Flood...")
            routing_dem = self._routing_dem()
            flooded = condition_depressions(routing_dem)
            self.flooded_dem = flooded
            raw_elev, valid_mask = valid_dem(self.dem)
            self.dep_depth = np.where(valid_mask, np.maximum(0.0, np.asarray(flooded, dtype=float) - np.asarray(routing_dem,dtype=float)), 0.0)

            self.update_status("Đang xử lý vùng địa hình bằng phẳng...")
            inflated = self.grid_obj.resolve_flats(flooded)
            self.dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
            self.update_status("Đang xác định hướng dòng chảy D8...")
            self.fdir = self.grid_obj.flowdir(inflated, dirmap=self.dirmap)
            self.update_status("Đang tính tích lũy dòng chảy...")
            self.acc = self.grid_obj.accumulation(self.fdir, dirmap=self.dirmap)

            self.ax.clear()
            self.ax.axis('on')
            self.app_state['lake_base_plot'] = []
            self.app_state['lake_basin_plot'] = []
            acc_img = np.where(self.acc > 0, self.acc, 1)
            self.ax.imshow(np.log(acc_img), extent=self.extent, cmap='Blues', zorder=1)

            if self.shp_paths and HAS_GPD:
                colors = ['red', 'green', '#9b59b6', '#e67e22', '#1abc9c', '#f1c40f']
                for idx, path in enumerate(self.shp_paths):
                    try:
                        gdf = gpd.read_file(path)
                        if gdf.crs is None: raise ValueError('Lớp nền thiếu hệ tọa độ; không tự gán CRS.')
                        if self.grid_obj.crs and gdf.crs and gdf.crs != self.grid_obj.crs:
                            gdf = gdf.to_crs(self.grid_obj.crs)
                        color = colors[idx % len(colors)]
                        gdf.plot(ax=self.ax, facecolor='none', edgecolor=color, linewidth=1.2, zorder=2)
                    except Exception as e:
                        print(f"Lỗi tải lớp {path}: {e}")

            self.lake_gdf = None
            lake_path_input = self.txt_lake.get().strip()
            if lake_path_input and not lake_path_input.startswith("["):
                self.nap_file_aoho_da_chon()
            elif self.var_auto_osm.get():
                try:
                    self.update_status("🌐 Đang tự động tải lớp Ao hồ thực tế từ bản đồ OpenStreetMap...")
                    gdf_osm = fetch_osm_water_polygons(self.grid_obj.bbox, self.grid_obj.crs)
                    if not gdf_osm.empty:
                        self.gop_them_ao_ho(gdf_osm, label_prefix="[OSM]")
                except Exception as osm_err:
                    print(f"Không tự tải được OSM khi nạp DEM: {osm_err}")

            self.canvas.draw()

            self.btn_add.configure(state="normal")
            self.btn_del.configure(state="normal")
            self.btn_draw_lake.configure(state="normal")
            self.btn_del_lake.configure(state="normal")
            self.btn_calc.configure(state="normal")
            self.btn_clear.configure(state="normal")
            self.btn_osm_lake.configure(state="normal")
            self.btn_detect_flat.configure(state="normal")
            self.clear_all()
            if self.lake_gdf is not None and not self.lake_gdf.empty:
                self.update_status(f"✅ Đã nạp DEM và {len(self.lake_gdf)} hồ OSM! Nếu thiếu hồ (như ở LV_1), bấm '🔍 2. Dò mặt hồ DEM' hoặc '✏️ VẼ THÊM HỒ'.")
            else:
                self.update_status("Đã nạp DEM. Hãy bấm '🌐 1. Tải hồ OSM', '🔍 2. Dò mặt hồ DEM' hoặc '✏️ VẼ THÊM HỒ'.")
            self.set_mode('add')

        except Exception as e:
            messagebox.showerror("Lỗi nạp dữ liệu", str(e))
            self.grid_obj = self.dem = self.fdir = self.acc = self.dep_depth = None
            self.update_status("❌ Có lỗi xảy ra khi nạp bản đồ; kết quả cũ không được dùng lại.")

    def on_scroll(self, event):
        if event.inaxes != self.ax: return
        cur_xlim, cur_ylim = self.ax.get_xlim(), self.ax.get_ylim()
        if event.xdata is None or event.ydata is None: return

        base_scale = 1.2
        scale = 1/base_scale if event.button == 'up' else base_scale if event.button == 'down' else 1
        new_w, new_h = (cur_xlim[1]-cur_xlim[0])*scale, (cur_ylim[1]-cur_ylim[0])*scale

        rx, ry = (cur_xlim[1]-event.xdata)/(cur_xlim[1]-cur_xlim[0]), (cur_ylim[1]-event.ydata)/(cur_ylim[1]-cur_ylim[0])
        self.ax.set_xlim([event.xdata - new_w*(1-rx), event.xdata + new_w*rx])
        self.ax.set_ylim([event.ydata - new_h*(1-ry), event.ydata + new_h*ry])
        self.canvas.draw_idle()

    def _dem_click(self, event):
        if self.toolbar.mode != '' or event.inaxes != self.ax:
            return
        if self.dem is None or event.xdata is None or event.ydata is None:
            return

        cx, cy = event.xdata, event.ydata
        mode = self.app_state['mode']

        # 1. Chế độ thêm cửa xả
        if mode == 'add' and event.button == 1:
            self.invalidate_results()
            self.app_state['points'].append((cx, cy))
            self.draw_points()

        # 2. Chế độ xóa cửa xả
        elif mode == 'delete' and event.button == 1:
            if not self.app_state['points']: return
            kc_min, idx_xoa = float('inf'), -1
            for i, (px, py) in enumerate(self.app_state['points']):
                kc = (px - cx)**2 + (py - cy)**2
                if kc < kc_min: kc_min, idx_xoa = kc, i

            nguong = ((self.ax.get_xlim()[1] - self.ax.get_xlim()[0]) * 0.02) ** 2
            if kc_min < nguong and idx_xoa != -1:
                self.invalidate_results()
                self.app_state['points'].pop(idx_xoa)
                self.draw_points()

        # 3. Chế độ VẼ THÊM HỒ BẰNG CHUỘT TRỰC TIẾP TRÊN BẢN ĐỒ
        elif mode == 'draw_lake':
            if event.button == 1:  # Chuột trái: thêm đỉnh đa giác hồ
                self.app_state['current_lake_pts'].append((cx, cy))
                pts = self.app_state['current_lake_pts']
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                if self.app_state['temp_lake_line'] is not None:
                    try: self.app_state['temp_lake_line'].remove()
                    except: pass
                line = Line2D(xs, ys, color='#00e5ff', marker='o', markersize=5, linewidth=2.0, linestyle='--', zorder=15)
                self.ax.add_line(line)
                self.app_state['temp_lake_line'] = line
                self.canvas.draw_idle()
                self.update_status(f"✏️ Đã chấm {len(pts)} đỉnh hồ. Click chuột trái để chấm tiếp, hoặc CLICK CHUỘT PHẢI để hoàn thành hồ!")

            elif event.button == 3:  # Chuột phải: khép kín Polygon hồ
                pts = self.app_state['current_lake_pts']
                if len(pts) < 3:
                    messagebox.showwarning("Chưa đủ đỉnh", "Cần chấm ít nhất 3 đỉnh bằng chuột trái trước khi click chuột phải để khép kín hồ!")
                    return
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                self.clear_temp_lake_drawing()
                if not poly.is_empty:
                    gdf_drawn = gpd.GeoDataFrame({'geometry': [poly]}, crs=self.grid_obj.crs)
                    self.gop_them_ao_ho(gdf_drawn, label_prefix="[Đã vẽ+OSM]")
                    dt_ha = poly.area / 1e4
                    self.update_status(f"✅ Đã vẽ thêm hồ mới rộng {dt_ha:.2f} ha ({poly.area/1e6:.3f} km²)! Hãy bấm Tính lưu vực để cập nhật.")

        # 4. Chế độ XÓA 1 HỒ TRÊN BẢN ĐỒ
        elif mode == 'del_lake' and event.button == 1:
            if self.lake_gdf is None or self.lake_gdf.empty:
                return
            pt = Point(cx, cy)
            contains_mask = self.lake_gdf.geometry.contains(pt)
            if not contains_mask.any():
                # Thử tìm hồ gần nhất trong bán kính nhỏ
                tol = (self.ax.get_xlim()[1] - self.ax.get_xlim()[0]) * 0.01
                contains_mask = self.lake_gdf.geometry.distance(pt) <= tol
            if contains_mask.any():
                self.lake_gdf = self.lake_gdf[~contains_mask].reset_index(drop=True)
                self.txt_lake.delete(0, "end")
                self.txt_lake.insert(0, f"[Còn lại] {len(self.lake_gdf)} mặt hồ")
                self.ve_lop_aoho_nen()
                self.invalidate_results()
                self.update_status(f"🗑 Đã xóa hồ tại vị trí click! Còn lại {len(self.lake_gdf)} mặt hồ.")

    def invalidate_results(self):
        self.app_state['gdf_out'] = self.app_state['gdf_streams'] = self.app_state['gdf_lakes_out'] = None
        self.btn_save.configure(state="disabled")

    def draw_points(self):
        if self.app_state['scatter_points']:
            try: self.app_state['scatter_points'].remove()
            except: pass
            self.app_state['scatter_points'] = None

        if self.app_state['points']:
            xs, ys = [p[0] for p in self.app_state['points']], [p[1] for p in self.app_state['points']]
            self.app_state['scatter_points'] = self.ax.scatter(xs, ys, c='red', marker='^', s=80, edgecolor='black', zorder=10)
        self.canvas.draw_idle()

    def _calculate_dem_basins(self):
        if not self.app_state['points']:
            messagebox.showinfo("Báo cáo", "Vui lòng chấm ít nhất 1 cửa xả!")
            return

        self.update_status("⚙️ Đang phân chia ranh giới, tính thông số lưu vực và diện tích ao hồ... Xin chờ!")
        self.update()

        try:
            if self.app_state['catchment_overlay']: self.app_state['catchment_overlay'].remove()
            if self.app_state['sink_overlay']: self.app_state['sink_overlay'].remove()
            for artist in self.app_state['lake_basin_plot']: artist.remove()
            for t in self.app_state['snapped_texts']: t.remove()
            for line in self.app_state['stream_plot']: line.remove()
        except: pass

        self.app_state['catchment_overlay'] = None
        self.app_state['sink_overlay'] = None
        self.app_state['lake_basin_plot'] = []
        self.app_state['snapped_texts'] = []
        self.app_state['stream_plot'], self.app_state['gdf_streams'] = [], None
        self.app_state['gdf_out'] = self.app_state['gdf_lakes_out'] = None
        self.btn_save.configure(state="disabled")

        try:
            if not HAS_GPD: raise ValueError("Cần cài geopandas và shapely để tính và xuất lưu vực.")
            threshold = int(self.txt_thresh.get())
            if threshold < 1: raise ValueError("Ngưỡng tạo sông phải là số nguyên dương.")

            min_sink_depth = float(self.txt_sink_depth.get())
            if min_sink_depth <= 0:
                raise ValueError("Ngưỡng sâu trũng DEM phải lớn hơn 0 (ví dụ: 0.3 hoặc 0.5 m).")

            use_dem_sink = bool(self.var_use_dem_sink.get())
            lake_union = unary_union(self.lake_gdf.geometry) if (self.lake_gdf is not None and not self.lake_gdf.empty) else None

            _, valid = valid_dem(self.dem)
            from scipy.ndimage import binary_erosion
            dem_boundary=valid & ~binary_erosion(valid,structure=np.ones((3,3),bool),border_value=0)
            transform = self.dem.affine
            combined = np.zeros(self.dem.shape, dtype=np.int32)
            combined_sinks = np.zeros(self.dem.shape, dtype=bool)
            records = []; snapped_coords = []; used = set()
            tat_ca_nhanh_song = []; tat_ca_song_chinh = []
            main_basin_ids = []; branch_basin_ids = []
            clipped_lake_records = []

            for basin_id, (x, y) in enumerate(self.app_state['points'], 1):
                outlet = snap_outlet(x, y, transform, self.acc, valid)
                if outlet in used: raise ValueError("Hai cửa xả được bắt vào cùng một ô; hãy chỉnh lại vị trí.")
                used.add(outlet)
                r, c = outlet
                snapped_coords.append(transform * (c+.5, r+.5))
                catch = catchment_d8(self.fdir, valid, outlet)
                mask = (np.asarray(catch) != 0) & valid

                metrics = measure_basin(
                    mask, self.dem, self.fdir, self.acc, outlet, transform, threshold,
                    dep_depth=self.dep_depth, min_sink_depth=min_sink_depth,
                    lake_union=lake_union, use_dem_sink=use_dem_sink
                )
                main = metrics.pop('main'); branches = metrics.pop('branches')
                clipped_lakes = metrics.pop('clipped_lakes')
                if clipped_lakes is not None and not clipped_lakes.is_empty:
                    clipped_lake_records.append({
                        'ID_LuuVuc': basin_id,
                        'DT_AoHo': metrics['DT_AoHo'],
                        'TyLe_AoHo': metrics['TyLe_AoHo'],
                        'geometry': clipped_lakes
                    })

                if main is not None:
                    tat_ca_song_chinh.append(main); main_basin_ids.append(basin_id)
                tat_ca_nhanh_song.extend(branches)
                branch_basin_ids.extend([basin_id]*len(branches))
                records.append(dict(ID_LuuVuc=basin_id, Nguon=self.dem_provenance+('+GIAY' if self.applied_paper_signature else ''), PhuDEM_pct=100., BienDEM=bool(np.any(mask & dem_boundary)), **metrics))
                combined[mask] = basin_id
                if lake_union is None and use_dem_sink and self.dep_depth is not None:
                    combined_sinks |= (mask & (self.dep_depth >= min_sink_depth))

            self.app_state['gdf_out'] = gpd.GeoDataFrame(records, crs=self.grid_obj.crs)
            if clipped_lake_records:
                self.app_state['gdf_lakes_out'] = gpd.GeoDataFrame(clipped_lake_records, crs=self.grid_obj.crs)
        except Exception as exc:
            self.update_status("Không thể tính lưu vực: " + str(exc))
            messagebox.showerror("Lỗi tính lưu vực", str(exc))
            return

        # Vẽ sông suối
        if tat_ca_nhanh_song or tat_ca_song_chinh:
            if tat_ca_nhanh_song:
                lines_nhanh = []
                for geom in tat_ca_nhanh_song:
                    if geom.geom_type == 'LineString':
                        lines_nhanh.append(np.array(geom.coords))
                    elif geom.geom_type == 'MultiLineString':
                        for part in geom.geoms:
                            lines_nhanh.append(np.array(part.coords))

                lc_nhanh = LineCollection(lines_nhanh, colors='#3498db', linewidths=1.0, zorder=4)
                self.ax.add_collection(lc_nhanh)
                self.app_state['stream_plot'].append(lc_nhanh)

            if tat_ca_song_chinh:
                lines_chinh = []
                for geom in tat_ca_song_chinh:
                    if geom.geom_type == 'LineString':
                        lines_chinh.append(np.array(geom.coords))
                    elif geom.geom_type == 'MultiLineString':
                        for part in geom.geoms:
                            lines_chinh.append(np.array(part.coords))

                lc_chinh = LineCollection(lines_chinh, colors='#000080', linewidths=2.8, zorder=5)
                self.ax.add_collection(lc_chinh)
                self.app_state['stream_plot'].append(lc_chinh)

            ds_geom = []
            ds_loai = []
            for g in tat_ca_song_chinh:
                ds_geom.append(g)
                ds_loai.append("Song_Chinh")
            for g in tat_ca_nhanh_song:
                ds_geom.append(g)
                ds_loai.append("Song_Nhanh")

            self.app_state['gdf_streams'] = gpd.GeoDataFrame({
                'ID_LuuVuc': main_basin_ids + branch_basin_ids,
                'Loai_Song': ds_loai,
                'geometry': ds_geom
            }, crs=self.grid_obj.crs)

        plot_data = np.where(combined > 0, combined, np.nan)
        self.app_state['catchment_overlay'] = self.ax.imshow(plot_data, extent=self.extent, cmap='tab10', alpha=0.45, zorder=3)

        # Tô nổi bật các Ao hồ nằm trong lưu vực
        if self.app_state['gdf_lakes_out'] is not None and not self.app_state['gdf_lakes_out'].empty:
            before = set(self.ax.collections) | set(self.ax.patches)
            self.app_state['gdf_lakes_out'].plot(ax=self.ax, facecolor='#0044ff', edgecolor='#ffffff', alpha=0.85, linewidth=0.9, zorder=6)
            after = set(self.ax.collections) | set(self.ax.patches)
            self.app_state['lake_basin_plot'] = list(after - before)
        elif np.any(combined_sinks):
            sink_plot = np.where(combined_sinks, 1.0, np.nan)
            self.app_state['sink_overlay'] = self.ax.imshow(sink_plot, extent=self.extent, cmap='winter', alpha=0.85, zorder=3.5)

        for idx, (sx, sy) in enumerate(snapped_coords):
            t = self.ax.text(sx, sy, f" LV_{idx+1}", color='black', fontsize=10, fontweight='bold',
                             bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=2), zorder=11)
            self.app_state['snapped_texts'].append(t)

        self.draw_points()
        self.btn_save.configure(state="normal")
        self.update_status(f"✅ Đã phân chia và thống kê xong {len(self.app_state['points'])} lưu vực (kèm tỷ lệ ao hồ)!")

        if (self.app_state['gdf_out']['Doc_SC_pm'] < 0).any():
            messagebox.showwarning("Kiểm tra cao độ DEM", "Có cao độ đầu sông thấp hơn cửa xả trên DEM gốc. Kiểm tra hố trũng, công trình chắn dòng và việc làm đầy DEM; không coi độ dốc âm là giá trị thiết kế.")
        if 'BienDEM' in self.app_state['gdf_out'] and self.app_state['gdf_out']['BienDEM'].any():
            messagebox.showwarning('Lưu vực chạm biên dữ liệu','Có lưu vực chạm biên DEM hoặc cạnh NoData. Kiểm tra khả năng thiếu phần thượng lưu, nhất là DEM nội suy từ đồng mức.')
        self.hien_thi_bang_thong_ke()

    def hien_thi_bang_thong_ke(self):
        if self.app_state['gdf_out'] is None: return

        df = self.app_state['gdf_out'].drop(columns='geometry')

        top = ctk.CTkToplevel(self)
        top.title("Kết quả Thống kê Lưu vực & Ao hồ")
        top.geometry("1180x440")
        top.attributes("-topmost", True)

        if self.workflow.get()=='Bản đồ giấy — vẽ ranh':
            phuong_phap_ho='Ranh giấy / ranh DEM chỉnh; dữ liệu thiếu để trống, không thay bằng 0'
        elif self.lake_gdf is not None and not self.lake_gdf.empty:
            phuong_phap_ho = f"Theo lớp Mặt nước ({len(self.lake_gdf)} hồ từ OSM / Dò phẳng DEM / Tự vẽ)"
        elif self.var_use_dem_sink.get():
            phuong_phap_ho = f"Theo hố trũng DEM (sâu ≥ {self.txt_sink_depth.get()} m)"
        else:
            phuong_phap_ho = "Chưa có hồ trong lưu vực (Bấm '🔍 2. Dò mặt hồ DEM' hoặc '✏️ VẼ THÊM HỒ')"

        lbl = ctk.CTkLabel(
            top,
            text=f"BẢNG THÔNG SỐ ĐỊA HÌNH & TỶ LỆ AO HỒ CÁC LƯU VỰC ({phuong_phap_ho})",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        lbl.pack(pady=10)

        frame_tb = ctk.CTkFrame(top)
        frame_tb.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        columns = (
            "ID",
            "Diện tích (km²)",
            "DT Ao hồ (km²)",
            "Tỷ lệ Ao hồ (%)",
            "Độ dốc LV (‰)",
            "Z đầu sông (m)",
            "Z cửa xả (m)",
            "Sông chính (km)",
            "Độ dốc Sông (‰)",
            "Sông nhánh (km)",
            "Nguồn ranh",
            "DEM phủ (%)"
        )
        tree = ttk.Treeview(frame_tb, columns=columns, show="headings", height=8, selectmode="extended")

        for col in columns:
            tree.heading(col, text=col)
            width = 70 if col == "ID" else 110
            tree.column(col, anchor="center", width=width)

        for _, row in df.iterrows():
            tree.insert("", tk.END, values=(
                f"LV_{int(row['ID_LuuVuc'])}",
                (f"{row['DienTich']:.3f}" if np.isfinite(row['DienTich']) else '—'),
                (f"{row['DT_AoHo']:.3f}" if np.isfinite(row['DT_AoHo']) else '—'),
                (f"{row['TyLe_AoHo']:.2f}" if np.isfinite(row['TyLe_AoHo']) else '—'),
                (f"{row['Doc_LV_pm']:.3f}" if np.isfinite(row['Doc_LV_pm']) else '—'),
                (f"{row['Z_Nguon']:.3f}" if np.isfinite(row['Z_Nguon']) else '—'),
                (f"{row['Z_CuaXa']:.3f}" if np.isfinite(row['Z_CuaXa']) else '—'),
                (f"{row['Dai_SC']:.3f}" if np.isfinite(row['Dai_SC']) else '—'),
                (f"{row['Doc_SC_pm']:.3f}" if np.isfinite(row['Doc_SC_pm']) else '—'),
                (f"{row['Dai_SNhanh']:.3f}" if np.isfinite(row['Dai_SNhanh']) else '—'),
                str(row.get('Nguon','DEM')),
                (f"{row['PhuDEM_pct']:.3f}" if np.isfinite(row.get('PhuDEM_pct',np.nan)) else '—')
            ))

        tree.grid(row=0,column=0,sticky='nsew')
        frame_tb.grid_rowconfigure(0,weight=1);frame_tb.grid_columnconfigure(0,weight=1)

        scrollbar = ttk.Scrollbar(frame_tb, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(frame_tb,orient='horizontal',command=tree.xview)
        tree.configure(xscrollcommand=horizontal.set);horizontal.grid(row=1,column=0,sticky='ew')

        def copy_to_clipboard(selected_only=False):
            lines = ["\t".join(columns)]
            items = tree.selection() if selected_only else tree.get_children()
            if not items:
                items = tree.get_children()

            for item in items:
                vals = tree.item(item)['values']
                lines.append("\t".join(str(v) for v in vals))

            clipboard_text = "\n".join(lines)
            top.clipboard_clear()
            top.clipboard_append(clipboard_text)
            top.update()

            so_dong = len(items)
            messagebox.showinfo(
                "Đã sao chép!",
                f"Đã copy {so_dong} dòng thông số vào bộ nhớ tạm.\n\n👉 Bạn hãy mở Excel và nhấn Ctrl + V để dán."
            )

        def copy_shortcut(event=None):
            copy_to_clipboard(selected_only=bool(tree.selection()))

        tree.bind("<Control-c>", copy_shortcut)
        tree.bind("<Control-C>", copy_shortcut)

        def export_excel():
            file_path = filedialog.asksaveasfilename(
                title="Lưu kết quả ra Excel",
                defaultextension=".xlsx",
                filetypes=[("Excel File", "*.xlsx"), ("CSV UTF-8", "*.csv"), ("All Files", "*.*")],
                initialfile="ThongSo_LuuVuc_AoHo.xlsx"
            )
            if not file_path:
                return

            try:
                col_order = ['ID_LuuVuc', 'DienTich', 'DT_AoHo', 'TyLe_AoHo', 'Doc_LV_pm', 'Z_Nguon', 'Z_CuaXa', 'Dai_SC', 'Doc_SC_pm', 'Dai_SNhanh', 'Nguon', 'PhuDEM_pct']
                df_export = df[col_order].copy()
                numeric_columns = df_export.select_dtypes(include=[np.number]).columns.drop("ID_LuuVuc")
                df_export[numeric_columns] = df_export[numeric_columns].round(3)
                df_export['ID_LuuVuc'] = df_export['ID_LuuVuc'].apply(lambda x: f"LV_{int(x)}")
                df_export.columns = columns

                if file_path.endswith('.csv'):
                    df_export.to_csv(file_path, index=False, encoding='utf-8-sig', float_format='%.3f')
                else:
                    try:
                        import pandas as pd
                        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                            df_export.to_excel(writer, index=False)
                            worksheet = writer.sheets['Sheet1']
                            for cells in worksheet.iter_rows(min_row=2, min_col=2):
                                for cell in cells:
                                    cell.number_format = '0.000'
                    except Exception:
                        csv_path = os.path.splitext(file_path)[0] + ".csv"
                        df_export.to_csv(csv_path, index=False, encoding='utf-8-sig', float_format='%.3f')
                        file_path = csv_path

                messagebox.showinfo("Thành công", f"Đã xuất file dữ liệu thành công:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Lỗi xuất file", f"Không thể lưu file:\n{e}")

        frame_btn = ctk.CTkFrame(top, fg_color="transparent")
        frame_btn.pack(fill="x", padx=15, pady=(0, 5))

        btn_copy = ctk.CTkButton(
            frame_btn,
            text="📋 Sao chép bảng (Dán vào Excel)",
            fg_color="#2980b9",
            hover_color="#3498db",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: copy_to_clipboard(selected_only=False)
        )
        btn_copy.pack(side="left", padx=(0, 10))

        btn_export = ctk.CTkButton(
            frame_btn,
            text="📊 Xuất ra file Excel (.xlsx)",
            fg_color="#27ae60",
            hover_color="#2ecc71",
            font=ctk.CTkFont(weight="bold"),
            command=export_excel
        )
        btn_export.pack(side="left")

        ctk.CTkLabel(
            top,
            text="*Mẹo: Khi xuất Shapefile, phần mềm sẽ xuất kèm cả file *_AoHo.shp để bạn tái sử dụng cho các lần sau.",
            font=ctk.CTkFont(size=11, slant="italic")
        ).pack(pady=(0, 10))

    def clear_all(self):
        self.clear_temp_lake_drawing()
        self.app_state['points'], self.app_state['gdf_out'], self.app_state['gdf_streams'], self.app_state['gdf_lakes_out'] = [], None, None, None
        self.btn_save.configure(state="disabled")

        try:
            if self.app_state['catchment_overlay']: self.app_state['catchment_overlay'].remove()
            if self.app_state['sink_overlay']: self.app_state['sink_overlay'].remove()
            for artist in self.app_state['lake_basin_plot']: artist.remove()
            for t in self.app_state['snapped_texts']: t.remove()
            for line in self.app_state['stream_plot']: line.remove()
        except: pass

        self.app_state['catchment_overlay'] = None
        self.app_state['sink_overlay'] = None
        self.app_state['lake_basin_plot'] = []
        self.app_state['snapped_texts'], self.app_state['stream_plot'] = [], []

        self.draw_points()
        self.update_status("🧹 Đã làm sạch các điểm cửa xả trên bản đồ.")

    def _save_result_vectors(self):
        if self.app_state['gdf_out'] is None: return

        selected_crs = self.cmb_crs.get()
        if self.app_state['gdf_out'].crs is None:
            messagebox.showerror("Thiếu hệ tọa độ", "Không tự gán WGS84 cho dữ liệu chưa biết CRS.")
            return
        target_epsg = None

        if "Giữ nguyên" not in selected_crs:
            match = re.search(r'(?:EPSG:)?(\d+)', selected_crs.upper())
            if match:
                target_epsg = int(match.group(1))
            else:
                messagebox.showerror("Lỗi nhận diện CRS", "Không nhận diện được mã số EPSG.\nHãy nhập dạng số hoặc chữ (VD: 3405 hoặc EPSG:3405).")
                return

        gdf_luuvuc_save = self.app_state['gdf_out'].copy()
        gdf_song_save = self.app_state['gdf_streams'].copy() if self.app_state['gdf_streams'] is not None else None
        gdf_aoho_save = self.app_state['gdf_lakes_out'].copy() if self.app_state['gdf_lakes_out'] is not None else None

        if target_epsg is not None:
            try:
                self.update_status(f"⏳ Đang chuyển đổi sang hệ tọa độ EPSG:{target_epsg}...")
                self.update()

                gdf_luuvuc_save = gdf_luuvuc_save.to_crs(epsg=target_epsg)
                if gdf_song_save is not None:
                    gdf_song_save = gdf_song_save.to_crs(epsg=target_epsg)
                if gdf_aoho_save is not None:
                    gdf_aoho_save = gdf_aoho_save.to_crs(epsg=target_epsg)
            except Exception as e:
                messagebox.showerror("Lỗi chuyển hệ tọa độ", f"Mã EPSG không hợp lệ hoặc thiếu dữ liệu tham chiếu trong máy:\n{e}")
                self.update_status("⚠️ Lỗi chuyển đổi tọa độ.")
                return

        out_file = filedialog.asksaveasfilename(
            title="Lưu file Ranh Giới, Sông Suối & Ao Hồ", defaultextension=".shp",
            filetypes=[("Shapefile", "*.shp"), ("GeoJSON", "*.geojson")], initialfile="KetQua.shp"
        )
        if out_file:
            try:
                base, ext = os.path.splitext(out_file)
                file_luuvuc = f"{base}_LuuVuc{ext}"
                file_song = f"{base}_SongSuoi{ext}"
                file_aoho = f"{base}_AoHo{ext}"

                driver = None if ext.lower() == '.shp' else 'GeoJSON'
                if driver=='GeoJSON':
                    gdf_luuvuc_save=gdf_luuvuc_save.to_crs(4326)
                    if gdf_song_save is not None:gdf_song_save=gdf_song_save.to_crs(4326)
                    if gdf_aoho_save is not None:gdf_aoho_save=gdf_aoho_save.to_crs(4326)
                kwargs = {'encoding': 'utf-8'} if driver is None else {'driver': driver, 'encoding': 'utf-8'}

                gdf_luuvuc_save.to_file(file_luuvuc, **kwargs)
                msg = f"- Lưu vực: {os.path.basename(file_luuvuc)}"

                if gdf_song_save is not None and not gdf_song_save.empty:
                    gdf_song_save.to_file(file_song, **kwargs)
                    msg += f"\n- Sông suối: {os.path.basename(file_song)}"

                if gdf_aoho_save is not None and not gdf_aoho_save.empty:
                    gdf_aoho_save.to_file(file_aoho, **kwargs)
                    msg += f"\n- Ao hồ trong lưu vực: {os.path.basename(file_aoho)}"

                messagebox.showinfo("Thành công", f"Đã xuất dữ liệu thành công!\n\n{msg}")
                self.update_status("💾 Đã lưu thành công bộ Shapefile kết quả!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi lưu file:\n{e}")

    def setup_paper_tools(self):
        frame=ctk.CTkFrame(self.right_panel,corner_radius=0)
        frame.pack(side='top',fill='x',before=self.canvas_widget,padx=5,pady=4)
        self.workflow=tk.StringVar(value='DEM tự động')
        ctk.CTkOptionMenu(frame,variable=self.workflow,values=['DEM tự động','Bản đồ giấy — vẽ ranh','DEM + bản đồ giấy'],
                         command=lambda value:self._workflow_changed()).grid(row=0,column=0,padx=4,pady=4,sticky='w')
        ctk.CTkButton(frame,text='Nạp ảnh giấy…',width=125,command=self.open_paper_map).grid(row=0,column=1,padx=4)
        ctk.CTkButton(frame,text='Mảnh ảnh / nắn tọa độ…',width=165,command=self.paper_map_manager).grid(row=0,column=2,padx=4)
        ctk.CTkButton(frame,text='Lưu vực từ ảnh…',width=135,command=self.paper_basin_manager).grid(row=0,column=3,padx=4)
        actions=ctk.CTkOptionMenu(frame,values=['Công cụ ảnh giấy','Tạo DEM từ đồng mức Z…','Tuyến sông / phân thủy…','Lưu dự án…','Mở dự án…','Hướng dẫn…'],
                                 command=self.paper_action)
        actions.grid(row=0,column=4,padx=4,sticky='e');frame.grid_columnconfigure(4,weight=1)
        self.paper_alpha=tk.DoubleVar(value=.75);self.paper_visible=tk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame,text='Hiện ảnh',variable=self.paper_visible,width=90,command=self._refresh_paper_visibility).grid(row=1,column=0,padx=4,pady=4,sticky='w')
        ctk.CTkSlider(frame,from_=0,to=1,variable=self.paper_alpha,command=lambda v:self._refresh_paper_visibility()).grid(row=1,column=1,padx=4,sticky='we')
        self.use_paper_constraints=tk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame,text='Hiệu chỉnh hướng chảy bằng tuyến đã kiểm tra',variable=self.use_paper_constraints,
                        command=self.invalidate_results).grid(row=1,column=2,columnspan=3,padx=4,sticky='w')
        self.var_auto_osm=tk.BooleanVar(value=False)
        self.fig.canvas.mpl_connect('key_press_event',self.paper_key)
        self.fig.canvas.mpl_connect('motion_notify_event',self.paper_motion)
        self.fig.canvas.mpl_connect('button_release_event',self.paper_release)
        self.after(100,self._paper_poll)

    def paper_action(self,value):
        actions={'Tạo DEM từ đồng mức Z…':self.paper_dem_dialog,'Tuyến sông / phân thủy…':self.paper_feature_manager,
                 'Lưu dự án…':self.save_paper_project,'Mở dự án…':self.load_paper_project,'Hướng dẫn…':self.paper_help}
        if value in actions:actions[value]()

    def _paper_guard(self,fn):
        if self.paper_busy:messagebox.showinfo('Đang xử lý','Chờ tác vụ hiện tại hoàn tất.');return
        try:return fn()
        except Exception as exc:messagebox.showerror('Bản đồ giấy',str(exc))

    def _workflow_changed(self):
        self.paper_mode=None;self.paper_temp=[]
        if self.workflow.get()=='Bản đồ giấy — vẽ ranh':
            self.btn_calc.configure(state='normal' if self.map_crs is not None else 'disabled')
            self.update_status('Bản đồ giấy: mở Lưu vực từ ảnh để vẽ đường phân thủy và gán cửa xả. Không tự suy ra hướng chảy từ màu ảnh.')
        elif self.dem is not None:self.btn_calc.configure(state='normal')
        self._render_paper_vectors()

    def _switch_map_crs(self,new_crs):
        new_crs=require_metric_crs(new_crs)
        if self.map_crs is not None and not CRS(self.map_crs).equals(new_crs):
            from shapely.ops import transform as geom_transform
            convert=Transformer.from_crs(self.map_crs,new_crs,always_xy=True)
            def points(pts):
                if not pts:return pts
                a=np.array(pts);x,y=convert.transform(a[:,0],a[:,1],errcheck=True)
                return np.column_stack((x,y)).tolist()
            for record in self.paper_basins:
                if record.get('geometry'):
                    record['geometry']=geom_transform(convert.transform,shape(record['geometry'])).__geo_interface__
                else:
                    record['points']=points(record['points']);record['holes']=[points(r) for r in record.get('holes',[])]
                if record.get('outlet') is not None:record['outlet']=points([record['outlet']])[0]
            for feature in self.paper_features:feature['points']=points(feature['points'])
            self.app_state['points']=[tuple(p) for p in points(self.app_state['points'])]
        self.map_crs=new_crs;self.paper_cache={}

    def open_paper_map(self):
        if self.paper_busy:return
        paths=filedialog.askopenfilenames(title='Chọn từng mảnh bản đồ cùng lưới tọa độ',filetypes=[('Ảnh bản đồ','*.tif *.tiff *.jpg *.jpeg *.png *.bmp')])
        for path in paths:
            try:
                paper=PaperMap(path);self.paper_maps.append(paper)
                if paper.matrix is None or not paper.crs:self.calibrate_paper(paper)
                else:self._show_paper_layer(paper,fit_view=self.dem is None)
                self.project_dirty=True
            except Exception as exc:messagebox.showerror('Nạp ảnh',str(exc))
        if self.paper_maps:
            self.workflow.set('DEM + bản đồ giấy' if self.dem is not None else 'Bản đồ giấy — vẽ ranh');self._workflow_changed()

    def _show_paper_layer(self,paper,fit_view=False):
        source=paper.check_ready()
        if self.map_crs is None:
            if source.is_projected and abs(source.axis_info[0].unit_conversion_factor-1)<1e-9:target=source
            else:
                middle=pixel_world(paper.matrix,[[paper.width/2,paper.height/2]])[0]
                lon,lat=Transformer.from_crs(source,4326,always_xy=True).transform(*middle,errcheck=True)
                if not -80<=lat<=84:raise ValueError('Ngoài miền UTM; cần chọn CRS phẳng mét phù hợp.')
                target=CRS.from_epsg((32600 if lat>=0 else 32700)+max(1,min(60,int((lon+180)//6)+1)))
            self._switch_map_crs(target)
        key=(paper.path,paper.matrix.tobytes(),paper.crs,self.map_crs.to_wkt())
        if key not in self.paper_cache:self.paper_cache[key]=paper.preview(self.map_crs)
        rgba,extent=self.paper_cache[key]
        old_view=(self.ax.get_xlim(),self.ax.get_ylim())
        keep_view=bool(self.ax.images or self.dem is not None) and not fit_view
        if paper.artist is not None:
            try:paper.artist.remove()
            except (ValueError,NotImplementedError):pass
        paper.artist=self.ax.imshow(rgba,extent=extent,origin='upper',alpha=self.paper_alpha.get(),zorder=1.8)
        paper.artist.set_visible(self.paper_visible.get() and paper.visible)
        self.ax.axis('on');self.ax.set_aspect('equal')
        if fit_view:
            extents=[im.get_extent() for im in self.ax.images if im.get_visible()]
            self.ax.set_xlim(min(e[0] for e in extents),max(e[1] for e in extents))
            self.ax.set_ylim(min(e[2] for e in extents),max(e[3] for e in extents))
        elif keep_view:
            self.ax.set_xlim(old_view[0]);self.ax.set_ylim(old_view[1])
        if self.dem is None:
            self.btn_add.configure(state='normal');self.btn_del.configure(state='normal');self.btn_calc.configure(state='normal')
        self.canvas.draw_idle()
        self._connect_paper_view()

    def _connect_paper_view(self):
        if getattr(self,'paper_view_registry',None) is self.ax.callbacks:return
        self.paper_view_registry=self.ax.callbacks
        self.ax.callbacks.connect('xlim_changed',lambda axis:self._queue_paper_view())
        self.ax.callbacks.connect('ylim_changed',lambda axis:self._queue_paper_view())

    def _queue_paper_view(self):
        if self.paper_view_updating or not self.paper_maps:return
        if self.paper_view_job is not None:
            try:self.after_cancel(self.paper_view_job)
            except tk.TclError:pass
        self.paper_view_job=self.after(180,self._update_paper_view)

    def _update_paper_view(self):
        self.paper_view_job=None
        if self.paper_busy or self.map_crs is None or not self.paper_visible.get():return
        bounds=(*sorted(self.ax.get_xlim()),*sorted(self.ax.get_ylim()))
        self.paper_view_updating=True
        try:
            for paper in self.paper_maps:
                if paper.artist is None or not paper.visible:continue
                try:
                    rgba,extent=paper.preview(self.map_crs,max_dimension=min(2600,max(1000,self.canvas_widget.winfo_width()*2)),target_bounds=bounds)
                    paper.artist.set_visible(rgba is not None)
                    if rgba is not None:paper.artist.set_data(rgba);paper.artist.set_extent(extent)
                except Exception as exc:
                    paper.artist.set_visible(False);self.lbl_status.configure(text='Kiểm tra lớp ảnh: '+str(exc))
            self.ax.set_xlim(bounds[:2]);self.ax.set_ylim(bounds[2:]);self.canvas.draw_idle()
        finally:self.paper_view_updating=False

    def _render_paper_maps(self):
        for paper in self.paper_maps:
            if paper.matrix is not None and paper.crs:
                try:self._show_paper_layer(paper)
                except Exception as exc:self.lbl_status.configure(text='Ảnh chưa hiển thị: '+str(exc))

    def _refresh_paper_visibility(self):
        for paper in self.paper_maps:
            if paper.artist is not None:
                paper.artist.set_alpha(self.paper_alpha.get());paper.artist.set_visible(self.paper_visible.get() and paper.visible)
        self.canvas.draw_idle()
        if self.paper_visible.get():self._queue_paper_view()

    def paper_map_manager(self):
        dialog=ctk.CTkToplevel(self);dialog.title('Các mảnh bản đồ giấy');dialog.geometry('820x450')
        tree=ttk.Treeview(dialog,columns=('name','size','crs'),show='headings')
        for name,title,width in [('name','Mảnh ảnh',260),('size','Pixel gốc',140),('crs','Hệ tọa độ / trạng thái',350)]:
            tree.heading(name,text=title);tree.column(name,width=width)
        tree.pack(fill='both',expand=True,padx=10,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            for i,p in enumerate(self.paper_maps):tree.insert('','end',iid=str(i),values=(os.path.basename(p.path),f'{p.width} × {p.height}',CRS(p.crs).to_string() if p.crs else 'Chưa nắn / chưa CRS'))
        def selected():
            ids=tree.selection()
            if not ids:raise ValueError('Chọn mảnh ảnh trước.')
            return self.paper_maps[int(ids[0])]
        def calibrate():self.calibrate_paper(selected());refresh()
        def remove():
            paper=selected()
            if paper.artist is not None:
                try:paper.artist.remove()
                except ValueError:pass
            self.paper_maps.remove(paper);self.project_dirty=True;refresh();self.canvas.draw_idle()
        def show():self._show_paper_layer(selected(),True)
        bar=ctk.CTkFrame(dialog);bar.pack(fill='x',padx=10,pady=6)
        for title,fn in [('Nạp ảnh…',self.open_paper_map),('Nắn / sửa điểm',calibrate),('Xem mảnh',show),('Xóa lớp ảnh',remove)]:
            ctk.CTkButton(bar,text=title,width=150,command=lambda f=fn:self._paper_guard(f)).pack(side='left',padx=4)
        refresh()

    def calibrate_paper(self,paper):
        from matplotlib.figure import Figure
        dialog=ctk.CTkToplevel(self);dialog.title('Nắn mảnh bản đồ — '+os.path.basename(paper.path));dialog.geometry('1180x820')
        controls=ctk.CTkFrame(dialog,width=350);controls.pack(side='left',fill='y',padx=6,pady=6)
        right=ctk.CTkFrame(dialog);right.pack(side='right',fill='both',expand=True)
        ctk.CTkLabel(controls,text='CRS nguồn ảnh (EPSG hoặc WKT)').pack(anchor='w',padx=5)
        crs_entry=ctk.CTkEntry(controls,width=330);crs_entry.pack(fill='x',padx=5,pady=4);crs_entry.insert(0,paper.crs)
        checkvar=tk.BooleanVar(value=False);ctk.CTkCheckBox(controls,text='Điểm kiểm tra độc lập',variable=checkvar).pack(padx=5,pady=5)
        tree=ttk.Treeview(controls,columns=('id','x','y','role'),show='headings',height=10)
        for key,title,width in [('id','#',35),('x','X / Easting',110),('y','Y / Northing',110),('role','Loại',45)]:tree.heading(key,text=title);tree.column(key,width=width)
        tree.pack(fill='x',padx=5,pady=4)
        label=ctk.CTkLabel(controls,text='Bấm giao lưới rõ nét để thêm điểm.\nX=Easting, Y=Northing.\nPhân bố điểm quanh mảnh ảnh.',wraplength=320);label.pack(padx=5,pady=8)
        figure=Figure(figsize=(8,7));axis=figure.add_subplot(111)
        canvas=FigureCanvasTkAgg(figure,master=right);canvas.get_tk_widget().pack(fill='both',expand=True)
        toolbar=NavigationToolbar2Tk(canvas,right);toolbar.update()
        with Image.open(paper.path) as im:
            preview=im.convert('RGB');preview.thumbnail((3000,3000),Image.Resampling.BILINEAR)
        view_job=[None];updating=[False]
        def update_crop():
            view_job[0]=None
            if not dialog.winfo_exists() or not axis.images:return
            left,right=sorted(axis.get_xlim());top,bottom=sorted(axis.get_ylim())
            x0=max(0,int(np.floor(left+.5)));y0=max(0,int(np.floor(top+.5)))
            x1=min(paper.width,int(np.ceil(right+.5)));y1=min(paper.height,int(np.ceil(bottom+.5)))
            if x1<=x0 or y1<=y0:return
            with Image.open(paper.path) as original:
                patch=original.crop((x0,y0,x1,y1)).convert('RGB');patch.thumbnail((2400,2400),Image.Resampling.BILINEAR)
            old=(axis.get_xlim(),axis.get_ylim());updating[0]=True
            try:
                axis.images[0].set_data(patch);axis.images[0].set_extent((x0-.5,x1-.5,y1-.5,y0-.5))
                axis.set_xlim(old[0]);axis.set_ylim(old[1]);canvas.draw_idle()
            finally:updating[0]=False
        def queue_crop(axis=None):
            if updating[0]:return
            if view_job[0] is not None:
                try:dialog.after_cancel(view_job[0])
                except tk.TclError:pass
            view_job[0]=dialog.after(120,update_crop)
        def cleanup_view(event):
            if event.widget is dialog and view_job[0] is not None:
                try:dialog.after_cancel(view_job[0])
                except tk.TclError:pass
                view_job[0]=None
        dialog.bind('<Destroy>',cleanup_view,add='+')
        def refresh():
            tree.delete(*tree.get_children())
            for i,p in enumerate(paper.gcps):tree.insert('','end',iid=str(i),values=(i+1,f"{p['x']:.3f}",f"{p['y']:.3f}",'KT' if p['check'] else 'Nắn'))
            old=(axis.get_xlim(),axis.get_ylim());axis.clear()
            axis.imshow(preview,extent=(-.5,paper.width-.5,paper.height-.5,-.5))
            for i,p in enumerate(paper.gcps):
                axis.plot(p['px'],p['py'],'+' if p['check'] else 'x',color='magenta');axis.annotate(str(i+1),(p['px'],p['py']),color='magenta')
            if old[0]!=(0.,1.):axis.set_xlim(old[0]);axis.set_ylim(old[1])
            axis.set_xlabel('Pixel X');axis.set_ylabel('Pixel Y');canvas.draw_idle()
            axis.callbacks.connect('xlim_changed',queue_crop);axis.callbacks.connect('ylim_changed',queue_crop)
            queue_crop()
        def click(event):
            if event.inaxes!=axis or event.button!=1 or toolbar.mode:return
            px,py=event.xdata,event.ydata
            if not 0<=px<paper.width or not 0<=py<paper.height:return
            try:
                x=simpledialog.askstring('X / Easting','Nhập X của giao lưới:',parent=dialog)
                if x is None:return
                y=simpledialog.askstring('Y / Northing','Nhập Y của giao lưới:',parent=dialog)
                if y is None:return
                paper.gcps.append(dict(px=px,py=py,x=finite_value(x),y=finite_value(y),check=checkvar.get()))
                self.project_dirty=True;refresh()
            except Exception as exc:messagebox.showerror('Điểm nắn',str(exc),parent=dialog)
        def edit():
            ids=tree.selection()
            if not ids:return
            p=paper.gcps[int(ids[0])]
            x=simpledialog.askstring('Sửa X','X / Easting:',initialvalue=str(p['x']),parent=dialog)
            if x is None:return
            y=simpledialog.askstring('Sửa Y','Y / Northing:',initialvalue=str(p['y']),parent=dialog)
            if y is None:return
            p['x']=finite_value(x);p['y']=finite_value(y);self.project_dirty=True;refresh()
        def delete():
            paper.gcps=[p for i,p in enumerate(paper.gcps) if str(i) not in tree.selection()];self.project_dirty=True;refresh()
        def fit():
            crs_text=crs_entry.get().strip();crs_text='EPSG:'+crs_text if crs_text.isdigit() else crs_text
            errors=paper.fit(crs_text);unit=CRS(paper.crs).axis_info[0].unit_name
            train=[v for p,v in zip(paper.gcps,errors) if not p['check']];checks=[v for p,v in zip(paper.gcps,errors) if p['check']]
            message=f'RMSE nắn: {np.sqrt(np.mean(np.square(train))):.3f} {unit}.'
            message+=f'\nRMSE KT: {np.sqrt(np.mean(np.square(checks))):.3f} {unit}.' if checks else '\nChưa có điểm kiểm tra độc lập.'
            label.configure(text=message+'\nKhớp 3 điểm tối thiểu không bảo đảm độ chính xác toàn mảnh.')
            self.paper_cache={};self._show_paper_layer(paper,fit_view=self.dem is None);self.project_dirty=True
        def worldfile():
            path=filedialog.askopenfilename(parent=dialog,filetypes=[('World File','*.tfw *.jgw *.pgw *.wld *.jpgw')])
            if path:paper.read_worldfile(path);label.configure(text='Đã nạp 6 hệ số. Nhập CRS rồi bấm Áp dụng CRS / World File.')
        def apply_world():
            if paper.matrix is None:raise ValueError('Chưa có World File hoặc phép nắn.')
            paper.crs=CRS.from_user_input(crs_entry.get().strip()).to_wkt()
            self.paper_cache={};self._show_paper_layer(paper,self.dem is None);self.project_dirty=True
        for title,fn in [('Sửa X/Y điểm chọn',edit),('Xóa điểm chọn',delete),('Tính nắn affine & sai số',fit),('Nạp World File…',worldfile),('Áp dụng CRS / World File',apply_world)]:
            ctk.CTkButton(controls,text=title,command=lambda f=fn:self._paper_guard(f)).pack(fill='x',padx=5,pady=4)
        ctk.CTkLabel(controls,text='Ảnh ghép lệch lưới: tách từng mảnh và nắn riêng.\nAffine không sửa phối cảnh hoặc giấy co giãn cục bộ.',wraplength=320).pack(padx=5,pady=8)
        figure.canvas.mpl_connect('button_press_event',click);refresh()

    def _paper_snapshot(self):
        self.paper_history.append((copy.deepcopy(self.paper_basins),copy.deepcopy(self.paper_features)))
        self.paper_history=self.paper_history[-20:]

    def _paper_invalidate(self):
        self.project_dirty=True;self.invalidate_results()

    def start_paper_draw(self,kind,basin_id=None):
        if self.map_crs is None:raise ValueError('Nắn bản đồ hoặc nạp DEM có tọa độ trước.')
        if kind in ('basin','edit_basin','outlet','main'):
            self.workflow.set('Bản đồ giấy — vẽ ranh')
        self.paper_mode=kind;self.paper_temp=[];self.paper_active_id=basin_id;self.paper_drag=None
        self.update_status(f'Vẽ {kind}: bấm các đỉnh; Enter/chuột phải hoàn tất, Backspace lùi, Esc hủy. Sông chính vẽ từ nguồn xuống cửa xả.')
        self._render_paper_vectors()

    def basin_geometry(self,record):
        return shape(record['geometry']) if record.get('geometry') else Polygon(record['points'],record.get('holes',[]))

    def _render_paper_vectors(self):
        for artist in self.paper_artists:
            try:artist.remove()
            except (ValueError,NotImplementedError):pass
        self.paper_artists=[]
        for record in self.paper_basins:
            geometry=self.basin_geometry(record)
            boundaries=[geometry] if geometry.geom_type=='Polygon' else list(geometry.geoms)
            for poly in boundaries:
                for ring in [poly.exterior,*poly.interiors]:
                    xy=np.asarray(ring.coords)[:,:2];line=Line2D(xy[:,0],xy[:,1],color='#ff00aa' if record['id']==self.paper_active_id else '#e77700',
                        linewidth=2 if record.get('reviewed') else 1.2,zorder=12)
                    self.ax.add_line(line);self.paper_artists.append(line)
            center=geometry.representative_point()
            self.paper_artists.append(self.ax.text(center.x,center.y,f"G{record['id']}",fontsize=10,color='#ae0066',zorder=13))
            if record.get('outlet'):
                x,y=record['outlet'];line,=self.ax.plot(x,y,'s',color='#de006f',zorder=14);self.paper_artists.append(line)
            if self.paper_mode=='edit_basin' and record['id']==self.paper_active_id and record.get('points'):
                xy=np.array(record['points']);line,=self.ax.plot(xy[:,0],xy[:,1],'o',markersize=4,color='magenta',zorder=15);self.paper_artists.append(line)
        for feature in self.paper_features:
            xy=np.array(feature['points']);kind=feature['kind'];color={'river':'#0077ff','main':'#000099','ridge':'#ec3030','lake':'#00bbcc'}[kind]
            if kind=='lake':xy=np.vstack((xy,xy[0]))
            line=Line2D(xy[:,0],xy[:,1],color=color,linewidth=1.7,linestyle='--' if kind=='ridge' else '-',zorder=11)
            self.ax.add_line(line);self.paper_artists.append(line)
        if self.paper_temp:
            xy=np.array(self.paper_temp);line=Line2D(xy[:,0],xy[:,1],color='magenta',marker='o',markersize=4,zorder=16)
            self.ax.add_line(line);self.paper_artists.append(line)
        self.canvas.draw_idle()

    def on_click(self,event):
        if self.paper_busy or self.toolbar.mode or event.inaxes!=self.ax or event.xdata is None:return
        self.canvas_widget.focus_set();point=[event.xdata,event.ydata]
        if self.paper_mode:
            if self.paper_mode in ('basin','river','ridge','main','lake'):
                if event.button==1:self.paper_temp.append(point);self._render_paper_vectors()
                elif event.button==3:self._paper_guard(self.finish_paper_draw)
            elif self.paper_mode=='outlet' and event.button==1:
                record=next(r for r in self.paper_basins if r['id']==self.paper_active_id)
                geometry=self.basin_geometry(record);tol=max(1.,np.sqrt(geometry.area)*.01)
                if not geometry.buffer(tol).covers(Point(point)):messagebox.showwarning('Cửa xả','Cửa xả nằm xa ranh lưu vực đã vẽ.');return
                self._paper_snapshot();record['outlet']=point;record['reviewed']=False;self._paper_invalidate();self._render_paper_vectors()
            elif self.paper_mode=='edit_basin' and event.button==1:self._paper_guard(lambda:self.edit_paper_vertex(point,event))
            return
        if self.dem is None and self.map_crs is not None:
            if self.app_state['mode']=='add' and event.button==1:self.app_state['points'].append(tuple(point));self.draw_points();self._paper_invalidate()
            return
        self._dem_click(event)
        self.project_dirty=True

    def finish_paper_draw(self):
        kind=self.paper_mode;points=self.paper_temp
        if kind not in ('basin','river','ridge','main','lake'):return
        if len(points)<(3 if kind in ('basin','lake') else 2):raise ValueError('Chưa đủ đỉnh.')
        geometry=Polygon(points) if kind in ('basin','lake') else LineString(points)
        if not geometry.is_valid or not geometry.is_simple or geometry.is_empty:raise ValueError('Đường/ranh tự giao; dùng Backspace để sửa trước khi kết thúc.')
        if kind=='basin':
            if geometry.area<=0:raise ValueError('Lưu vực không có diện tích.')
            self._paper_snapshot();identifier=max([r['id'] for r in self.paper_basins],default=0)+1
            self.paper_basins.append(dict(id=identifier,points=copy.deepcopy(points),holes=[],reviewed=False,outlet=None,source='BAN_DO_GIAY'))
            self.paper_active_id=identifier
        else:
            record=dict(kind=kind,points=copy.deepcopy(points),basin_id=self.paper_active_id,reviewed=False)
            if kind=='main':
                if self.paper_active_id is None:raise ValueError('Chọn lưu vực trong bảng trước khi vẽ sông chính.')
                for field,text in [('z_start','Cao độ đầu sông (m), có thể bỏ trống nếu chưa biết:'),('z_end','Cao độ cửa xả (m), có thể bỏ trống:')]:
                    value=simpledialog.askstring('Cao độ đọc từ bản đồ',text,parent=self)
                    record[field]=None if not value or not value.strip() else finite_value(value)
                if any(f['kind']=='main' and f.get('basin_id')==self.paper_active_id for f in self.paper_features):
                    raise ValueError('Lưu vực đã có sông chính; xóa tuyến cũ trong bảng tuyến trước khi vẽ lại.')
            self._paper_snapshot();self.paper_features.append(record)
        self.paper_temp=[];self.paper_mode=None;self._paper_invalidate();self._render_paper_vectors()
        self.update_status('Đã lưu nét vẽ. Đối chiếu đường phân thủy/sông và xác nhận kiểm tra trước khi xuất.')

    def paper_key(self,event):
        if self.paper_busy:return
        if event.key in ('enter','return'):self._paper_guard(self.finish_paper_draw)
        elif event.key=='escape':self.paper_temp=[];self.paper_mode=None;self.paper_drag=None;self._render_paper_vectors()
        elif event.key=='backspace' and self.paper_temp:self.paper_temp.pop();self._render_paper_vectors()
        elif event.key=='ctrl+z':self.paper_undo()
        elif event.key=='delete' and self.paper_mode=='edit_basin' and self.paper_cursor is not None:
            self._paper_guard(self.delete_paper_vertex)

    def paper_undo(self):
        if self.paper_busy or not self.paper_history:return
        self.paper_basins,self.paper_features=self.paper_history.pop();self.paper_drag=None;self.paper_active_id=None
        self._paper_invalidate();self._render_paper_vectors()

    def edit_paper_vertex(self,point,event):
        record=next(r for r in self.paper_basins if r['id']==self.paper_active_id)
        if not record.get('points'):raise ValueError('Lưu vực nhiều phần: giữ nguyên hình học hoặc vẽ lại từng ranh; không tự bỏ các phần nhỏ.')
        points=np.array(record['points']);screen=self.ax.transData.transform(points);mouse=self.ax.transData.transform(point)
        if event.key and 'shift' in event.key:
            index=min(range(len(points)),key=lambda i:LineString([screen[i],screen[(i+1)%len(points)]]).distance(Point(mouse)))
            if LineString([screen[index],screen[(index+1)%len(points)]]).distance(Point(mouse))>12:raise ValueError('Bấm gần cạnh muốn chèn đỉnh.')
            self._paper_snapshot();record['points'].insert(index+1,point);record['reviewed']=False
            self._paper_invalidate();self._render_paper_vectors()
        else:
            distance=np.linalg.norm(screen-mouse,axis=1);index=int(distance.argmin())
            if distance[index]>12:raise ValueError('Bấm gần đỉnh để kéo; Shift+bấm trên cạnh để chèn.')
            self._paper_snapshot();self.paper_drag=(record['id'],index)

    def paper_motion(self,event):
        if event.inaxes!=self.ax or event.xdata is None:return
        self.paper_cursor=[event.xdata,event.ydata]
        if self.paper_drag is None or self.paper_busy:return
        record=next(r for r in self.paper_basins if r['id']==self.paper_drag[0]);record['points'][self.paper_drag[1]]=self.paper_cursor.copy()
        record['reviewed']=False;record['source']='DEM_CHINH' if record['source'].startswith('DEM') else 'BAN_DO_GIAY'
        self._paper_invalidate();self._render_paper_vectors()

    def paper_release(self,event):self.paper_drag=None

    def delete_paper_vertex(self):
        record=next(r for r in self.paper_basins if r['id']==self.paper_active_id)
        if not record.get('points') or len(record['points'])<=3:return
        screen=self.ax.transData.transform(record['points']);mouse=self.ax.transData.transform(self.paper_cursor)
        distance=np.linalg.norm(screen-mouse,axis=1)
        if distance.min()>12:return
        self._paper_snapshot();record['points'].pop(int(distance.argmin()));record['reviewed']=False
        self._paper_invalidate();self._render_paper_vectors()

    def paper_basin_manager(self):
        if self.paper_busy:return
        dialog=ctk.CTkToplevel(self);dialog.title('Lưu vực từ bản đồ giấy / chỉnh ranh DEM');dialog.geometry('1050x590')
        tree=ttk.Treeview(dialog,columns=('id','area','source','check','out'),show='headings',selectmode='browse')
        for key,title,width in [('id','LV',70),('area','Diện tích km²',150),('source','Nguồn ranh',200),('check','Đã kiểm tra',150),('out','Cửa xả',260)]:
            tree.heading(key,text=title);tree.column(key,width=width)
        tree.pack(fill='both',expand=True,padx=10,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.paper_basins:
                geometry=self.basin_geometry(r);out=r.get('outlet')
                tree.insert('','end',iid=str(r['id']),values=(r['id'],f'{geometry.area/1e6:.3f}',r['source'],'Có' if r.get('reviewed') else 'Chưa',
                    f'{out[0]:.3f}; {out[1]:.3f}' if out else 'Chưa gán'))
        def selected():
            ids=tree.selection()
            if not ids:raise ValueError('Chọn một lưu vực trong bảng.')
            return next(r for r in self.paper_basins if str(r['id'])==ids[0])
        def draw():dialog.destroy();self.start_paper_draw('basin')
        def edit():
            r=selected()
            if not r.get('points'):raise ValueError('Lưu vực nhiều phần được giữ đầy đủ; không chỉnh kéo đỉnh như một đa giác đơn. Có thể vẽ ranh mới để đối chiếu.')
            dialog.destroy();self.start_paper_draw('edit_basin',r['id'])
        def outlet():r=selected();dialog.destroy();self.start_paper_draw('outlet',r['id'])
        def main():r=selected();dialog.destroy();self.start_paper_draw('main',r['id'])
        def review():
            r=selected();geometry=self.basin_geometry(r)
            if not geometry.is_valid:raise ValueError('Ranh tự giao; sửa đỉnh trước khi xác nhận.')
            if r.get('outlet') is None:raise ValueError('Gán vị trí cửa xả để xác nhận ranh thủy văn.')
            if not geometry.buffer(max(1.,np.sqrt(geometry.area)*.01)).covers(Point(r['outlet'])):raise ValueError('Cửa xả nằm xa lưu vực.')
            if not messagebox.askyesno('Xác nhận kiểm tra','Đã đối chiếu đường phân thủy, hướng chảy, cửa xả và phạm vi bản đồ?'):return
            self._paper_snapshot();r['reviewed']=True;self._paper_invalidate();self._render_paper_vectors();refresh()
        def delete():
            r=selected()
            if not messagebox.askyesno('Xóa lưu vực',f"Xóa lưu vực {r['id']} và sông chính gắn với lưu vực này?"):return
            self._paper_snapshot();self.paper_basins.remove(r)
            self.paper_features=[f for f in self.paper_features if not (f['kind']=='main' and f.get('basin_id')==r['id'])]
            self.paper_active_id=None;self._paper_invalidate();self._render_paper_vectors();refresh()
        def take_dem():
            frame=self.app_state['gdf_out']
            if frame is None or frame.empty:raise ValueError('Tính kết quả DEM trước rồi chuyển ranh sang chỉnh trên ảnh.')
            if 'Nguon' in frame and not frame['Nguon'].str.startswith('DEM').all():raise ValueError('Kết quả hiện tại không phải ranh DEM.')
            self._paper_snapshot();identifier=max([r['id'] for r in self.paper_basins],default=0)+1
            for _,row in frame.iterrows():
                geometry=row.geometry
                r=dict(id=identifier,source='DEM_CHINH',reviewed=False,outlet=None)
                if geometry.geom_type=='Polygon':r.update(points=np.array(geometry.exterior.coords)[:-1,:2].tolist(),holes=[np.array(ring.coords)[:-1,:2].tolist() for ring in geometry.interiors])
                else:r['geometry']=geometry.__geo_interface__
                i=int(row['ID_LuuVuc'])-1
                if 0<=i<len(self.app_state['points']):r['outlet']=list(self.app_state['points'][i])
                self.paper_basins.append(r);identifier+=1
            self.workflow.set('Bản đồ giấy — vẽ ranh')
            self._paper_invalidate();self._render_paper_vectors();refresh()
        def zoom(event=None):
            r=selected();self.paper_active_id=r['id'];left,bottom,right,top=self.basin_geometry(r).bounds
            pad=max(right-left,top-bottom)*.1;self.ax.set_xlim(left-pad,right+pad);self.ax.set_ylim(bottom-pad,top+pad);self._render_paper_vectors()
        rows=ctk.CTkFrame(dialog);rows.pack(fill='x',padx=10,pady=8)
        actions=[('Vẽ ranh mới',draw),('Sửa đỉnh',edit),('Gán cửa xả',outlet),('Vẽ sông chính',main),('Xác nhận',review),('Xóa',delete),('Nhận ranh DEM',take_dem),('Undo',lambda:(self.paper_undo(),refresh()))]
        for i,(title,fn) in enumerate(actions):ctk.CTkButton(rows,text=title,width=120,command=lambda f=fn:self._paper_guard(f)).grid(row=i//4,column=i%4,padx=4,pady=4,sticky='ew')
        for i in range(4):rows.grid_columnconfigure(i,weight=1)
        ctk.CTkLabel(dialog,text='Bấm đúp để xem ranh. Sửa đỉnh: kéo, Shift+bấm chèn, Delete xóa. Ranh sửa không còn là kết quả DEM thuần.',wraplength=950).pack(pady=5)
        tree.bind('<Double-1>',lambda e:self._paper_guard(zoom));refresh()

    def paper_feature_manager(self):
        if self.paper_busy:return
        dialog=ctk.CTkToplevel(self);dialog.title('Tuyến kiểm chứng từ bản đồ giấy');dialog.geometry('920x600')
        tree=ttk.Treeview(dialog,columns=('id','kind','length','basin','check'),show='headings')
        for key,title,width in [('id','#',50),('kind','Loại nét',150),('length','Chiều dài m / diện tích hồ m²',260),('basin','LV',80),('check','Đã kiểm tra',140)]:tree.heading(key,text=title);tree.column(key,width=width)
        tree.pack(fill='both',expand=True,padx=10,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            for i,f in enumerate(self.paper_features):
                value=Polygon(f['points']).area if f['kind']=='lake' else LineString(f['points']).length
                tree.insert('','end',iid=str(i),values=(i+1,f['kind'],f'{value:.3f}',f.get('basin_id') or '—','Có' if f.get('reviewed') else 'Chưa'))
        def review():
            ids=tree.selection()
            if not ids:raise ValueError('Chọn tuyến/vùng trước.')
            if not messagebox.askyesno('Kiểm chứng tuyến','Đã đối chiếu loại nét, vị trí, quan hệ sông–phân thủy với bản đồ?'):return
            self._paper_snapshot()
            for i in ids:self.paper_features[int(i)]['reviewed']=True
            self._paper_invalidate();refresh()
        def delete():
            ids=set(map(int,tree.selection()))
            if not ids:raise ValueError('Chọn tuyến/vùng cần xóa.')
            self._paper_snapshot();self.paper_features=[f for i,f in enumerate(self.paper_features) if i not in ids]
            self._paper_invalidate();self._render_paper_vectors();refresh()
        def draw(kind):dialog.destroy();self.start_paper_draw(kind)
        tools=ctk.CTkFrame(dialog);tools.pack(fill='x',padx=10,pady=4)
        for label,fn in [('Vẽ sông',lambda:draw('river')),('Vẽ phân thủy',lambda:draw('ridge')),('Vẽ hồ',lambda:draw('lake')),('Xác nhận',review),('Xóa nét',delete)]:
            ctk.CTkButton(tools,text=label,width=150,command=lambda f=fn:self._paper_guard(f)).pack(side='left',padx=3)
        params=ctk.CTkFrame(dialog);params.pack(fill='x',padx=10,pady=5)
        for label,var in [('Hạ tuyến sông (m):',self.paper_burn),('Nâng tuyến phân thủy (m):',self.paper_raise)]:
            ctk.CTkLabel(params,text=label).pack(side='left',padx=4);ctk.CTkEntry(params,textvariable=var,width=80).pack(side='left',padx=4)
        ctk.CTkLabel(dialog,text='Chỉ tuyến đã xác nhận mới được dùng khi bật Hiệu chỉnh hướng chảy. DEM gốc giữ nguyên; cao độ điều chỉnh chỉ dùng để tính hướng chảy.\nĐiều chỉnh có thể làm đổi ranh và tạo hố/đập giả; phải tính lại và kiểm tra. Đường sông không được cắt phân thủy trong cùng ô DEM.',wraplength=850).pack(padx=10,pady=10)
        refresh()

    def paper_routing_signature(self):
        if not self.use_paper_constraints.get():return None
        features=[f for f in self.paper_features if f.get('reviewed') and f['kind'] in ('river','main','ridge')]
        if not features:raise ValueError('Đã bật hiệu chỉnh nhưng chưa có tuyến sông/phân thủy được xác nhận kiểm tra.')
        return json.dumps(dict(features=features,burn=finite_value(self.paper_burn.get()),raise_by=finite_value(self.paper_raise.get())),sort_keys=True)

    def _routing_dem(self):
        self.applied_paper_signature=self.paper_routing_signature()
        if self.applied_paper_signature is None:return self.dem
        features=[f for f in self.paper_features if f.get('reviewed')]
        routed,rivers,ridges=apply_paper_constraints(self.dem,features,finite_value(self.paper_burn.get()),finite_value(self.paper_raise.get()))
        self.lbl_status.configure(text=f'Hiệu chỉnh hướng chảy: {rivers} ô sông, {ridges} ô phân thủy. DEM gốc không đổi.')
        return routed

    def load_data(self):
        if self.paper_busy:return
        if not self.txt_dem.get().strip():
            if self.map_crs is not None and self.paper_maps:
                self.workflow.set('Bản đồ giấy — vẽ ranh');self._workflow_changed();self._render_paper_maps();return
            messagebox.showinfo('Dữ liệu','Chọn DEM hoặc nạp/nắn ảnh giấy trước.');return
        self.paper_busy=True
        try:
            self._load_dem_data()
            if self.dem is not None:
                self._render_paper_maps();self._render_paper_vectors()
                if self.paper_maps and self.workflow.get()!='Bản đồ giấy — vẽ ranh':self.workflow.set('DEM + bản đồ giấy')
        finally:self.paper_busy=False

    def chay_chia_luu_vuc(self):
        if self.paper_busy:return
        self.paper_mode=None;self.paper_temp=[]
        if self.workflow.get()=='Bản đồ giấy — vẽ ranh':self._paper_guard(self.calculate_paper_basins);return
        if self.dem is None:messagebox.showinfo('DEM','Nạp DEM để tính tự động hoặc chọn Bản đồ giấy — vẽ ranh.');return
        try:
            if self.workflow.get()=='DEM + bản đồ giấy':self.paper_maps_check()
            if self.paper_routing_signature()!=self.applied_paper_signature:
                points=self.app_state['points'].copy();self.load_data()
                if self.dem is None:return
                self.app_state['points']=points;self.draw_points()
            self._calculate_dem_basins();self._render_paper_vectors()
        except Exception as exc:messagebox.showerror('Chia lưu vực',str(exc))

    def calculate_paper_basins(self):
        if self.map_crs is None:raise ValueError('Chưa có hệ tọa độ bản đồ.')
        require_metric_crs(self.map_crs)
        if not self.paper_basins:raise ValueError('Mở Lưu vực từ ảnh, vẽ/nhận ranh và gán cửa xả trước.')
        self.paper_maps_check()
        records=[];streams=[];lake_records=[]
        lakes=[Polygon(f['points']) for f in self.paper_features if f['kind']=='lake' and f.get('reviewed')]
        if self.lake_gdf is not None and not self.lake_gdf.empty:
            lake_frame=self.lake_gdf.to_crs(self.map_crs);lakes.extend(lake_frame.geometry)
        lake_union=unary_union(lakes) if lakes else None
        for record in self.paper_basins:
            geometry=self.basin_geometry(record)
            metrics=manual_basin_metrics(geometry,record['id'],self.paper_features,self.dem,record.get('outlet'),lake_union)
            metrics['Nguon']=record['source'];metrics['KiemTra']=bool(record.get('reviewed'))
            records.append(metrics)
            for f in self.paper_features:
                if f['kind']=='main' and f.get('basin_id')==record['id']:
                    streams.append(dict(ID_LuuVuc=record['id'],Loai_Song='Song_Chinh_Giay',geometry=LineString(f['points'])))
            if lake_union is not None:
                clip=geometry.intersection(lake_union)
                if not clip.is_empty:lake_records.append(dict(ID_LuuVuc=record['id'],geometry=clip))
        self.app_state['gdf_out']=gpd.GeoDataFrame(records,crs=self.map_crs)
        self.app_state['gdf_streams']=gpd.GeoDataFrame(streams,crs=self.map_crs) if streams else None
        self.app_state['gdf_lakes_out']=gpd.GeoDataFrame(lake_records,crs=self.map_crs) if lake_records else None
        self.btn_save.configure(state='normal');self._render_paper_vectors()
        self.update_status(f'Đã tính {len(records)} lưu vực từ ranh ảnh. Số liệu thiếu để trống; chỉ xuất ranh đã xác nhận.')
        self.hien_thi_bang_thong_ke()

    def paper_maps_check(self):
        for paper in self.paper_maps:paper.check_ready()

    def luu_ket_qua(self):
        if self.paper_busy:return
        frame=self.app_state['gdf_out']
        if frame is None:return
        if 'KiemTra' not in frame:
            self._save_result_vectors();return
        if not frame['KiemTra'].any():messagebox.showinfo('Chưa kiểm tra','Xác nhận ranh/cửa xả trong Lưu vực từ ảnh trước khi xuất.');return
        original={key:self.app_state[key] for key in ('gdf_out','gdf_streams','gdf_lakes_out')}
        try:
            valid_frame=frame[frame['KiemTra']].copy();ids=set(valid_frame['ID_LuuVuc'])
            self.app_state['gdf_out']=valid_frame
            for key in ('gdf_streams','gdf_lakes_out'):
                value=self.app_state[key]
                if value is not None:self.app_state[key]=value[value['ID_LuuVuc'].isin(ids)].copy()
            self._save_result_vectors()
        finally:self.app_state.update(original)

    def paper_dem_dialog(self):
        if self.paper_busy:return
        path=filedialog.askopenfilename(title='Đồng mức đã gán cao độ / điểm cao độ',filetypes=[('Vector Z','*.shp *.geojson *.gpkg *.dxf')])
        if not path:return
        try:
            default=self.map_crs.to_string() if self.map_crs is not None else ''
            crs=simpledialog.askstring('CRS nguồn / đích','CRS nguồn nếu file thiếu CRS (DXF) và CRS mét dùng cho DEM:',initialvalue=default,parent=self)
            if not crs:return
            target=require_metric_crs(crs)
            resolution=simpledialog.askstring('Cỡ ô nội suy','Cỡ ô (m). Ô nhỏ không tự làm tăng độ chính xác:',initialvalue='10',parent=self)
            if resolution is None:return
            resolution=finite_value(resolution)
            field=simpledialog.askstring('Cao độ','Tên cột cao độ cho lớp 2D (bỏ trống nếu hình học có Z):',initialvalue='ELEVATION',parent=self)
            if field is None:return
            layer='*'
            if path.lower().endswith('.dxf'):
                layer=simpledialog.askstring('Layer đồng mức','Chỉ lấy layer (ví dụ DM_*), tránh khung/chữ/đường khác:',initialvalue='DM_*',parent=self)
                if layer is None:return
            destination=filedialog.asksaveasfilename(title='DEM NỘI SUY từ đồng mức, không phải DEM đo',defaultextension='.tif',filetypes=[('GeoTIFF','*.tif')])
            if not destination:return
            self.update_status('Đang nội suy DEM từ cao độ đã kiểm tra; không ngoại suy ra ngoài miền điểm…')
            def done(result):
                self.txt_dem.delete(0,'end');self.txt_dem.insert(0,destination)
                self.update_status(f"Đã tạo DEM nội suy {result['width']}×{result['height']} ô từ {result['points']} điểm. Nạp DEM để chia; kiểm tra các lưu vực chạm biên dữ liệu.")
                messagebox.showinfo('DEM nội suy','Đã tạo DEM từ đồng mức. Đây là bề mặt nội suy, có thể thiếu sống núi/khe suối.\nKhông ngoại suy ngoài bao lồi. Cần kiểm chứng ranh trước khi dùng thiết kế.')
            self._paper_worker(lambda:contours_to_dem(path,destination,target,resolution,field,crs,layer),done)
        except Exception as exc:messagebox.showerror('Tạo DEM',str(exc))

    def _paper_worker(self,work,done):
        if self.paper_busy:return
        self.paper_busy=True
        def run():
            try:self.paper_queue.put((done,work(),None))
            except Exception as exc:self.paper_queue.put((done,None,exc))
        threading.Thread(target=run,daemon=True).start()

    def _paper_poll(self):
        try:
            while True:
                done,result,error=self.paper_queue.get_nowait();self.paper_busy=False
                if error:messagebox.showerror('Xử lý bản đồ giấy',str(error));self.lbl_status.configure(text=str(error))
                else:self._paper_guard(lambda:done(result))
        except queue.Empty:pass
        self.after(100,self._paper_poll)

    def _paper_text(self,title,text):
        dialog=ctk.CTkToplevel(self);dialog.title(title);dialog.geometry('900x690')
        box=ctk.CTkTextbox(dialog,wrap='word');box.pack(fill='both',expand=True,padx=10,pady=10);box.insert('1.0',text);box.configure(state='disabled')

    def paper_help(self):
        self._paper_text('Bản đồ giấy + DEM — quy trình & giới hạn',
            'CÁCH 1 — CHỈ CÓ BẢN ĐỒ GIẤY\n'
            'Nạp từng mảnh ảnh → khai báo đúng CRS nguồn → nắn affine bằng ≥3 giao lưới (nên 6–12 phân bố quanh mảnh) '
            'và thêm điểm kiểm tra độc lập. Hoặc nạp World File đủ 6 hệ số + CRS. Không tự đoán múi/kinh tuyến trục VN-2000.\n'
            'Chọn Bản đồ giấy — vẽ ranh → Lưu vực từ ảnh → Vẽ ranh mới, đi theo đường phân thủy qua sống núi/yên ngựa. '
            'Enter/chuột phải kết thúc, Backspace lùi, Esc hủy. Gán cửa xả cho từng lưu vực. '
            'Có thể vẽ sông chính từ nguồn đến cửa xả và nhập cao độ đọc từ bản đồ. '
            'Không tự suy cao độ/hướng chảy từ màu nét hoặc nền xanh/nâu. Không có cao độ/DEM thì độ dốc giữ trống.\n\n'
            'CÁCH 2 — DEM KẾT HỢP BẢN ĐỒ GIẤY\n'
            'Nạp DEM → nạp/nắn mảnh giấy. Các lớp được chuyển về cùng CRS mét để chồng khớp. Chấm cửa xả rồi tính DEM như trước. '
            'Trong Lưu vực từ ảnh, Nhận ranh DEM để kiểm tra và kéo sửa trên giấy. Sửa đỉnh: kéo, Shift+bấm chèn, Delete xóa; '
            'Ctrl+Z hoàn tác. Ranh đã sửa được ghi nguồn DEM_CHINH, không giả là ranh DEM tự động. '
            'Các phần rời và lỗ của đa giác DEM được giữ nguyên; ranh nhiều phần không tự bỏ các phần nhỏ để kéo sửa.\n'
            'Nếu đường sông/phân thủy DEM khác thực tế, dùng Tuyến sông / phân thủy để vẽ, kiểm tra và xác nhận. '
            'Bật Hiệu chỉnh hướng chảy để hạ tuyến sông/nâng tuyến phân thủy trên bản DEM định tuyến riêng. '
            'DEM gốc vẫn dùng đo cao độ/độ dốc. Chọn mức nhỏ có cơ sở; thay đổi này có thể tạo hố/đập giả và làm sai ranh. '
            'Không tự ép hướng dòng ở đồng bằng, vùng triều, đê/cống khi chưa đủ thông tin.\n\n'
            'CÁCH 3 — TẠO DEM TỪ ĐƯỜNG ĐỒNG MỨC\n'
            'Dùng DXF 3D/SHP/GeoJSON có cao độ đã kiểm tra (có thể xuất từ TopoContourDigitizer). '
            'Tạo DEM từ đồng mức Z → chọn CRS, cỡ ô, trường cao độ và layer cần dùng. Nội suy TIN tuyến tính, '
            'không ngoại suy ra ngoài bao lồi; các vùng thiếu dữ liệu giữ NoData. Ô nhỏ không tăng độ chính xác nguồn. '
            'Mọi đường cùng Z, cao độ thiếu hoặc cùng XY khác Z đều bị từ chối. Dữ liệu thưa/thiếu đường phân thủy '
            'có thể tạo bề mặt sai: cần bổ sung điểm cao độ và kiểm tra với giấy. Đây không phải DEM khảo sát.\n\n'
            'KIỂM TRA VÀ LƯU\n'
            'Xác nhận ranh và cửa xả sau khi đối chiếu. Lưu vực giấy chưa xác nhận không được xuất vector. '
            'Thông số trống là chưa đủ dữ liệu, không thay bằng 0. Diện tích từ đa giác tính chính xác theo CRS mét; '
            'độ dốc DEM của ranh vẽ chỉ tính khi DEM phủ gần đủ ranh. Hồ từ nét giấy chỉ tính sau khi đã kiểm tra. '
            'Các cửa xả DEM tạo lưu vực toàn phần độc lập, có thể lồng nhau; không cộng diện tích lồng nhau. '
            'BiênDEM đánh dấu lưu vực chạm biên/NoData: kiểm tra khả năng thiếu diện tích thượng lưu.\n'
            'Lưu/mở dự án giữ ảnh tham chiếu, điểm nắn, ranh, tuyến và cửa xả. Chuyển máy cần mang cả các ảnh/DEM nguồn. '
            'Xuất SHP/GeoJSON theo chức năng cũ, có nguồn ranh và cờ kiểm tra.\n\n'
            'Ảnh ghép các mảnh không cùng lưới (như bố cục ảnh mẫu) cần tách mảnh và nắn riêng. '
            'Một phép affine không sửa được ảnh chụp phối cảnh hoặc giấy co giãn cục bộ; phải nắn chuyên dụng/chia mảnh trước. '
            'Sai số điểm khống chế tối thiểu bằng 0 không chứng minh độ chính xác toàn bản đồ.')

    def save_paper_project(self):
        if self.paper_busy:return
        path=filedialog.asksaveasfilename(defaultextension='.lvgiay.json',filetypes=[('Dự án lưu vực','*.json')])
        if not path:return
        try:
            directory=os.path.dirname(os.path.abspath(path));maps=[]
            for paper in self.paper_maps:
                record=dict(path=os.path.relpath(paper.path,directory),width=paper.width,height=paper.height,
                    matrix=paper.matrix.tolist() if paper.matrix is not None else None,crs=paper.crs,gcps=paper.gcps,
                    signature=paper.calibrated_signature)
                with open(paper.path,'rb') as original:record['sha256']=hashlib.file_digest(original,'sha256').hexdigest()
                maps.append(record)
            dem_path=self.txt_dem.get().strip()
            data=dict(version=1,crs=self.map_crs.to_wkt() if self.map_crs else '',maps=maps,basins=self.paper_basins,
                features=self.paper_features,points=self.app_state['points'],workflow=self.workflow.get(),
                dem=os.path.relpath(dem_path,directory) if dem_path else '',
                use_constraints=self.use_paper_constraints.get(),burn=self.paper_burn.get(),raise_by=self.paper_raise.get())
            if self.lake_gdf is not None and not self.lake_gdf.empty:
                data['lakes']=[g.__geo_interface__ for g in self.lake_gdf.to_crs(self.map_crs).geometry]
            fd,temp=tempfile.mkstemp(dir=directory,suffix='.tmp');os.close(fd)
            try:
                with open(temp,'w',encoding='utf-8') as output:json.dump(data,output,ensure_ascii=False,allow_nan=False)
                os.replace(temp,path)
            finally:
                if os.path.exists(temp):os.unlink(temp)
            self.project_dirty=False;self.update_status('Đã lưu dự án. Giữ ảnh/DEM nguồn cùng bộ dự án khi chuyển máy.')
        except Exception as exc:messagebox.showerror('Lưu dự án',str(exc))

    def load_paper_project(self):
        if self.paper_busy:return
        path=filedialog.askopenfilename(filetypes=[('Dự án lưu vực','*.json')])
        if not path:return
        if self.project_dirty and not messagebox.askyesno('Mở dự án','Bỏ các chỉnh sửa bản đồ giấy chưa lưu?'):return
        try:
            if os.path.getsize(path)>100_000_000:raise ValueError('Dự án JSON vượt 100 MB.')
            with open(path,encoding='utf-8') as handle:data=json.load(handle)
            if data.get('version')!=1:raise ValueError('Phiên bản dự án không hỗ trợ.')
            directory=os.path.dirname(path);maps=[]
            for r in data['maps']:
                source=os.path.normpath(os.path.join(directory,r['path']))
                if not os.path.isfile(source):
                    source=filedialog.askopenfilename(title='Chọn lại đúng ảnh '+os.path.basename(r['path']))
                    if not source:return
                with open(source,'rb') as original:
                    if hashlib.file_digest(original,'sha256').hexdigest()!=r['sha256']:raise ValueError('Ảnh không đúng nội dung SHA-256 của dự án.')
                paper=PaperMap(source,r['matrix'],r['crs'],r['gcps']);paper.calibrated_signature=r.get('signature');maps.append(paper)
            crs=require_metric_crs(data['crs']) if data['crs'] else None
            for r in data['basins']:
                if not self.basin_geometry(r).is_valid:raise ValueError('Dự án có ranh không hợp lệ; không nạp chồng lên dữ liệu đang có.')
            ids=[r['id'] for r in data['basins']]
            if len(ids)!=len(set(ids)):raise ValueError('Mã lưu vực bị trùng trong dự án.')
            for feature in data['features']:
                if feature['kind'] not in ('river','ridge','main','lake'):raise ValueError('Loại tuyến/vùng không hợp lệ.')
                points=np.array(feature['points'],dtype=float)
                minimum=3 if feature['kind']=='lake' else 2
                if points.ndim!=2 or points.shape[1]!=2 or len(points)<minimum or not np.isfinite(points).all():
                    raise ValueError('Tuyến/vùng trong dự án có tọa độ không hợp lệ.')
                geometry=Polygon(points) if feature['kind']=='lake' else LineString(points)
                if not geometry.is_valid or not geometry.is_simple:raise ValueError('Tuyến/vùng dự án tự giao.')
            for point in data['points']:
                if len(point)!=2 or not np.isfinite(np.asarray(point,dtype=float)).all():raise ValueError('Cửa xả không hợp lệ.')
            for paper in self.paper_maps:
                if paper.artist is not None:
                    try:paper.artist.remove()
                    except ValueError:pass
            self.clear_all();self.ax.clear();self.map_crs=crs;self.paper_maps=maps;self.paper_basins=data['basins'];self.paper_features=data['features']
            self.paper_active_id=None;self.paper_mode=None;self.paper_temp=[];self.paper_cache={};self.paper_history=[]
            self.grid_obj=self.dem=self.fdir=self.acc=self.flooded_dem=self.dep_depth=None
            self.use_paper_constraints.set(data['use_constraints']);self.paper_burn.set(data['burn']);self.paper_raise.set(data['raise_by'])
            dem_path=os.path.normpath(os.path.join(directory,data['dem'])) if data['dem'] else ''
            self.txt_dem.delete(0,'end')
            if dem_path and os.path.isfile(dem_path):self.txt_dem.insert(0,dem_path)
            elif dem_path:messagebox.showinfo('DEM chưa tìm thấy','Dự án vẫn mở được ở chế độ ảnh. Chọn lại DEM để tính tự động.')
            self.workflow.set(data['workflow']);self.app_state['points']=[tuple(p) for p in data['points']]
            self.lake_gdf=gpd.GeoDataFrame(geometry=[shape(g) for g in data.get('lakes',[])],crs=crs) if crs and data.get('lakes') else None
            self._render_paper_maps()
            self._render_paper_vectors();self.draw_points()
            if maps:self._show_paper_layer(maps[0],fit_view=True)
            self.btn_calc.configure(state='normal' if crs else 'disabled');self.btn_save.configure(state='disabled')
            self.project_dirty=False;self.update_status('Đã mở dự án. Có thể chỉnh ranh trên ảnh; bấm Nạp DEM nếu cần tính tự động.')
        except Exception as exc:messagebox.showerror('Mở dự án',str(exc))

    def paper_close(self):
        if self.paper_busy:messagebox.showinfo('Đang xử lý','Chờ tác vụ hoàn tất trước khi đóng.');return
        if self.project_dirty and not messagebox.askyesno('Đóng','Các chỉnh sửa bản đồ giấy chưa lưu. Đóng và bỏ thay đổi?'):return
        self.dem_workspace.cleanup();self.destroy()

    def destroy(self):
        # Tk deletes callback commands on destruction but can leave scheduled timers.
        # This application owns the root/interpreter and its descendant dialogs.
        try:
            for identifier in self.tk.call('after','info'):
                self.tk.call('after','cancel',identifier)
        except tk.TclError:pass
        super().destroy()

if __name__ == "__main__":
    app = GeoCatchmentApp()
    app.mainloop()
