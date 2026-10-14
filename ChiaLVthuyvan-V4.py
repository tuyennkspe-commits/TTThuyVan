"""Chia lưu vực DEM — V7: Kết hợp OSM + Tự động dò mặt nước phẳng (Hydro-Flat) + Vẽ bổ sung Ao hồ trực tiếp trên bản đồ.
Cài thư viện: python -m pip install numpy pysheds numba rasterio pyproj geopandas shapely matplotlib customtkinter pandas openpyxl scipy
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
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from pysheds.grid import Grid
import tempfile
from shapely.geometry import shape, LineString, Polygon, MultiPolygon, Point
from shapely.ops import unary_union, polygonize
from rasterio.features import shapes
from pyproj import CRS, Transformer
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

D8 = {64:(-1,0), 128:(-1,1), 1:(0,1), 2:(1,1), 4:(1,0), 8:(1,-1), 16:(0,-1), 32:(-1,-1)}

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

class GeoCatchmentApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("GeoCatchment Pro V7 - Phân Tích Lưu Vực, Dò Mặt Hồ Phẳng & Vẽ Bổ Sung Ao Hồ Thực Tế")
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

        self.setup_ui()

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(self, width=360, corner_radius=0)
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
            "Giữ nguyên như DEM gốc",
            "EPSG:4326 (WGS 84 - Cầu)",
            "EPSG:32648 (UTM Zone 48N)",
            "EPSG:3405 (VN-2000 Toàn quốc)"
        ]
        self.cmb_crs = ctk.CTkComboBox(self.frame_export, values=self.crs_options, width=290, height=26, fg_color="white", text_color="black")
        self.cmb_crs.pack(padx=10, pady=3)

        self.btn_save = ctk.CTkButton(self.frame_export, text="💾 LƯU SHAPEFILE KẾT QUẢ", fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(weight="bold"), height=34, state="disabled", command=self.luu_ket_qua)
        self.btn_save.pack(padx=10, pady=(2, 8), fill="x")

        self.lbl_status = ctk.CTkLabel(self.left_panel, text="💡 Sẵn sàng. Hãy chọn file DEM rồi nhấn Nạp bản đồ.", text_color="gray", wraplength=310, justify="left")
        self.lbl_status.grid(row=10, column=0, padx=16, pady=6, sticky="sw")

        self.right_panel = ctk.CTkFrame(self, corner_radius=0, fg_color="white")
        self.right_panel.grid(row=0, column=1, sticky="nsew")

        self.fig, self.ax = plt.subplots(figsize=(8, 6))
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

    def load_data(self):
        dem_path = self.txt_dem.get()
        if not dem_path:
            messagebox.showwarning("Cảnh báo", "Bạn chưa chọn file DEM!")
            return

        try:
            self.update_status("⏳ Đang đọc và xử lý DEM... Xin chờ!")

            self.btn_calc.configure(state="disabled")
            self.btn_save.configure(state="disabled")
            dem_path = metric_dem(dem_path, os.path.join(self.dem_workspace.name, "dem_metric.tif"))
            self.grid_obj = Grid.from_raster(dem_path)
            self.dem = self.grid_obj.read_raster(dem_path)
            xmin, ymin, xmax, ymax = self.grid_obj.bbox
            self.cols, self.rows = self.grid_obj.shape[1], self.grid_obj.shape[0]
            self.cell_w, self.cell_h = (xmax - xmin) / self.cols, (ymax - ymin) / self.rows
            self.extent = [xmin, xmax, ymin, ymax]

            self.xmin, self.xmax, self.ymin, self.ymax = xmin, xmax, ymin, ymax

            self.update_status("Đang xử lý hố trũng bằng Priority-Flood...")
            flooded = condition_depressions(self.dem)
            self.flooded_dem = flooded
            raw_elev, valid_mask = valid_dem(self.dem)
            self.dep_depth = np.where(valid_mask, np.maximum(0.0, np.asarray(flooded, dtype=float) - raw_elev), 0.0)

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
            else:
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

    def on_click(self, event):
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

    def chay_chia_luu_vuc(self):
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
                records.append(dict(ID_LuuVuc=basin_id, **metrics))
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
        self.hien_thi_bang_thong_ke()

    def hien_thi_bang_thong_ke(self):
        if self.app_state['gdf_out'] is None: return

        df = self.app_state['gdf_out'].drop(columns='geometry')

        top = ctk.CTkToplevel(self)
        top.title("Kết quả Thống kê Lưu vực & Ao hồ")
        top.geometry("1180x440")
        top.attributes("-topmost", True)

        if self.lake_gdf is not None and not self.lake_gdf.empty:
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
            "Sông nhánh (km)"
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
                (f"{row['Dai_SNhanh']:.3f}" if np.isfinite(row['Dai_SNhanh']) else '—')
            ))

        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame_tb, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

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
                col_order = ['ID_LuuVuc', 'DienTich', 'DT_AoHo', 'TyLe_AoHo', 'Doc_LV_pm', 'Z_Nguon', 'Z_CuaXa', 'Dai_SC', 'Doc_SC_pm', 'Dai_SNhanh']
                df_export = df[col_order].copy()
                numeric_columns = df_export.columns.drop("ID_LuuVuc")
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

    def luu_ket_qua(self):
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
                kwargs = {'encoding': 'utf-8'} if driver is None else {'driver': driver, 'encoding': 'utf-8'}

                gdf_luuvuc_save.to_file(file_luuvuc, **kwargs)
                msg = f"- Lưu vực: {os.path.basename(file_luuvuc)}"

                if gdf_song_save is not None:
                    gdf_song_save.to_file(file_song, **kwargs)
                    msg += f"\n- Sông suối: {os.path.basename(file_song)}"

                if gdf_aoho_save is not None and not gdf_aoho_save.empty:
                    gdf_aoho_save.to_file(file_aoho, **kwargs)
                    msg += f"\n- Ao hồ trong lưu vực: {os.path.basename(file_aoho)}"

                messagebox.showinfo("Thành công", f"Đã xuất dữ liệu thành công!\n\n{msg}")
                self.update_status("💾 Đã lưu thành công bộ Shapefile kết quả!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi lưu file:\n{e}")

if __name__ == "__main__":
    app = GeoCatchmentApp()
    app.mainloop()