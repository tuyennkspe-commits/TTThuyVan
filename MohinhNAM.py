"""
PHẦN MỀM THỦY VĂN NAM DESKTOP - CHẠY TRỰC TIẾP TRÊN MÁY TÍNH
NAM 9 thông số: không tuyết/tưới; dòng tràn có điều tiết biến đổi theo lưu lượng.
Đối chiếu: Agrawal & Desmukh (2016), IJISET 3(6), tr.664–665;
Razad et al. (2018), JEST 13(12), tr.4211–4214.
Bài tổng quan có lỗi ký hiệu; áp dụng phương trình phù hợp thứ nguyên.
Không khẳng định tương đương bộ giải MIKE NAM của DHI.
Cài đặt: python -m pip install numpy pandas scipy matplotlib openpyxl
Tăng tốc tùy chọn: python -m pip install numba
Đọc MIKE DFS0: python -m pip install mikeio
Bản đồ lưu vực/Thiessen: python -m pip install geopandas shapely pyproj
P/PET tổng mm mỗi bước; Q trung bình hoặc tức thời cuối bước m³/s, chọn theo quan trắc.
Hiệu chỉnh cần kiểm định độc lập.
SHP giữ riêng từng lưu vực; Thiessen mưa/PET tính riêng; dự án .namproj lưu toàn bộ mạng trạm và mô hình.
"""

import os
import json
import tempfile
import re
from datetime import datetime, date
from pathlib import Path
import threading
import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure
from matplotlib import dates as mdates
from matplotlib.ticker import AutoLocator, ScalarFormatter
import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution, least_squares
from scipy.stats import qmc
try:
    from numba import njit
    NUMBA_AVAILABLE=True
except ImportError:
    NUMBA_AVAILABLE=False

# ==============================================================================
# 1. THUẬT TOÁN MÔ HÌNH BỂ CHỨA NAM VÀ ĐÁNH GIÁ CHỈ SỐ NASH
# ==============================================================================

PARAM_KEYS = [
    "U_max",
    "L_max",
    "CQOF",
    "CK_12",
    "TOF",
    "TIF",
    "TG",
    "CK_IF",
    "CK_BF",
]

PARAM_BOUNDS = [
    (5.0, 35.0),  # U_max (mm): Dung tích trữ tầng mặt
    (40.0, 350.0),  # L_max (mm): Dung tích trữ tầng rễ
    (0.05, 1.0),  # CQOF (-): Hệ số dòng tràn bề mặt
    (1.0, 50.0),  # CK_12 (h): Thời gian điều tiết dòng tràn
    (0.0, 0.99),  # TOF (-): Ngưỡng ẩm sinh dòng tràn
    (0.0, 0.99),  # TIF (-): Ngưỡng ẩm sinh dòng sát mặt
    (0.0, 0.99),  # TG (-): Ngưỡng ẩm thấm xuống ngầm
    (10.0, 2000.0),  # CK_IF (h): Hằng số sinh dòng sát mặt; có thể sửa giới hạn
    (200.0, 10000.0),  # CK_BF (h): Thời gian điều tiết ngầm; có thể sửa giới hạn
]


def finite_number(value, name, positive=False):
    try:
        value=float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name}: cần nhập số.') from None
    if not np.isfinite(value) or (positive and value<=0):
        raise ValueError(f'{name}: cần số hữu hạn'+(' lớn hơn 0.' if positive else '.'))
    return value


def validate_data(df, dt_hours):
    """P và PET là tổng mm trong mỗi bước, không phải mm/giờ."""
    df=df.copy()
    if len(df)<2:
        raise ValueError('Chuỗi cần ít nhất 2 bước thời gian.')
    for col in ['Mua_mm', 'BocHoi_mm']:
        if col not in df:
            raise ValueError(f'Thiếu cột {col}.')
        df[col]=pd.to_numeric(df[col],errors='raise')
        if not np.all(np.isfinite(df[col])) or np.any(df[col]<0):
            raise ValueError(f'{col}: không được âm, thiếu hoặc vô hạn; không tự điền mưa thiếu bằng 0.')
    if 'Q_ThucDo_m3s' not in df:
        df['Q_ThucDo_m3s']=np.nan
    df['Q_ThucDo_m3s']=pd.to_numeric(df['Q_ThucDo_m3s'],errors='raise')
    q=df['Q_ThucDo_m3s'].to_numpy()
    if np.any(np.isinf(q)) or np.any(q[np.isfinite(q)]<0):
        raise ValueError('Lưu lượng thực đo không được âm hoặc vô hạn; có thể để trống.')
    if 'ThoiGian' in df:
        times=pd.to_datetime(df['ThoiGian'],errors='raise')
        if times.isna().any() or not np.allclose(times.diff().dropna().dt.total_seconds().to_numpy()/3600,dt_hours,rtol=0,atol=1e-6):
            raise ValueError('ThoiGian phải tăng đều đúng bước tính; không chấp nhận ngày thiếu/trùng.')
    return df


SERIES_NAMES={'Mua_mm':'Mưa (mm/bước)','BocHoi_mm':'Bốc hơi tiềm năng (mm/bước)','Q_ThucDo_m3s':'Lưu lượng thực đo (m³/s)'}


class ImportCancelled(Exception):
    pass


def read_dfs0(path,key,item_selector=None):
    try:import mikeio
    except ImportError:raise ValueError('Đọc DFS0 cần thư viện MIKE IO. Cài bằng: python -m pip install mikeio') from None
    source=mikeio.open(path);items=source.items
    if not items:raise ValueError('DFS0 không có mục dữ liệu.')
    index=0
    if len(items)>1:
        if item_selector is None:raise ValueError('DFS0 có nhiều mục; cần chọn chuỗi muốn nhập.')
        index=item_selector(items)
        if index is None:raise ImportCancelled()
        if not isinstance(index,int) or not 0<=index<len(items):raise ValueError('Mục DFS0 không hợp lệ.')
    data=source.read(items=[index]);item=items[index]
    times=pd.DatetimeIndex(data.time)
    values=np.asarray(data[0].to_numpy(),dtype=float)
    if values.ndim!=1:raise ValueError('DFS0 phải là chuỗi thời gian một chiều.')
    unit=item.unit.name;kind=item.data_value_type.name
    if kind in ['Accumulated','MeanStepForward']:
        raise ValueError(f'{item.name}: kiểu {kind} chưa phù hợp dữ liệu mỗi bước; chuyển sang StepAccumulated hoặc MeanStepBackward trong MIKE trước khi nhập.')
    notes=[f'DFS0: {item.name}; đơn vị {item.unit}; kiểu {kind}.']
    if key=='Q_ThucDo_m3s':
        factors={'meter_pow_3_per_sec':1.,'meter_pow_3_per_min':1/60,'meter_pow_3_per_hour':1/3600,'meter_pow_3_per_day':1/86400,'liter_per_sec':.001,'liter_per_minute':.001/60,'feet_pow_3_per_sec':.028316846592}
        if unit not in factors:raise ValueError(f'Đơn vị {item.unit} không phù hợp lưu lượng. Chọn mục lưu lượng (m³/s).')
        if kind=='StepAccumulated':raise ValueError('Lưu lượng phải là tốc độ m³/s hoặc trung bình bước, không phải tổng tích lũy.')
        values=values*factors[unit]
    else:
        depth={'millimeter':1.,'centimeter':10.,'meter':1000.,'inch':25.4,'feet':304.8}
        rate={'mm_per_sec':3600.,'mm_per_hour':1.,'mm_per_day':1/24,'millimeter_per_day':1/24,'cm_per_hour':10.,'meter_per_sec':3600000.,'meter_per_day':1000/24,'inch_per_hour':25.4,'inch_per_day':25.4/24}
        if unit in depth:values=values*depth[unit]
        elif unit in rate:
            if len(times)<2:raise ValueError('DFS0 tốc độ mưa/bốc hơi cần ít nhất 2 thời điểm để xác định bước.')
            hours=times.to_series().diff().dropna().dt.total_seconds().to_numpy()/3600
            if np.any(hours<=0) or not np.allclose(hours,hours[0],rtol=0,atol=1e-6):raise ValueError('DFS0 tốc độ mưa/bốc hơi cần bước thời gian đều.')
            if kind=='StepAccumulated':raise ValueError('Kiểu StepAccumulated phải dùng đơn vị lớp nước, không phải tốc độ.')
            values=values*rate[unit]*hours[0]
            notes.append(f'Đổi tốc độ sang tổng mm mỗi bước {hours[0]:g} giờ; giá trị đại diện cho bước kết thúc tại thời điểm ghi.')
        else:raise ValueError(f'Đơn vị {item.unit} không phù hợp mưa/bốc hơi; chọn lớp nước mm hoặc tốc độ mưa.')
    result=pd.DataFrame({'ThoiGian':times,key:values})
    result.attrs['dfs_notes']=notes
    return result


def read_series_file(path,key,item_selector=None):
    if path.lower().endswith(".dfs0"):return read_dfs0(path,key,item_selector)
    if path.lower().endswith('.xlsx'):
        raw=pd.read_excel(path,header=None)
    else:
        first=Path(path).read_text(encoding='utf-8-sig').splitlines()[0]
        sep=';' if ';' in first else '\t' if '\t' in first else ','
        raw=pd.read_csv(path,sep=sep,header=None,encoding='utf-8-sig')
    if raw.empty:raise ValueError('Tệp không có dữ liệu.')
    # Chuỗi một cột có thể có tiêu đề hoặc chỉ có các giá trị.
    if raw.shape[1]==1:
        try:float(raw.iloc[0,0]);start=0
        except (ValueError,TypeError):start=1
        return pd.DataFrame({key:raw.iloc[start:,0].to_numpy()})
    if raw.shape[1]==2:
        first_time=raw.iloc[0,0]
        is_date=isinstance(first_time,(datetime,date,pd.Timestamp)) or isinstance(first_time,str) and bool(re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T].*)?$',first_time.strip()))
        if is_date:
            # Hai cột ngày giờ / giá trị, không tiêu đề: giữ cả dòng đầu.
            return pd.DataFrame({'ThoiGian':raw.iloc[:,0].to_numpy(),key:raw.iloc[:,1].to_numpy()})
    raw.columns=[str(v).strip() for v in raw.iloc[0]]
    return raw.iloc[1:].reset_index(drop=True)


def prepare_series(df,key):
    """Có ThoiGian: ghép theo ngày giờ; không có: ghép theo bước 1..n."""
    df=df.copy();df.columns=[str(c).strip() for c in df.columns]
    value_col=key if key in df else 'GiaTri' if 'GiaTri' in df else df.columns[0] if len(df.columns)==1 else None
    if value_col is None:raise ValueError(f'Cần cột {key}, GiaTri, hoặc tệp một cột giá trị. ThoiGian là tùy chọn.')
    values=pd.to_numeric(df[value_col],errors='raise')
    if np.isinf(values).any() or (values.dropna()<0).any():raise ValueError('Giá trị phải không âm và không vô hạn.')
    if len(df)<1:raise ValueError('Tệp không có số liệu.')
    import_notes=list(df.attrs.get('dfs_notes',[]))
    if 'ThoiGian' in df:
        axis='ThoiGian';coordinates=pd.to_datetime(df[axis],errors='raise')
        missing=coordinates.isna()
        if missing.any():
            if key!='Q_ThucDo_m3s':raise ValueError('Mưa/bốc hơi có dòng thiếu ngày giờ; kiểm tra tệp nguồn.')
            records=[f'dòng dữ liệu {i+1}: Q={values.iloc[i]}' for i in np.flatnonzero(missing.to_numpy())]
            import_notes.append('Không dùng Q thiếu ngày giờ: '+ '; '.join(records))
            coordinates=coordinates[~missing];values=values[~missing]
            if not len(coordinates):raise ValueError('Không có lưu lượng nào đủ ngày giờ để nhập.')
        if coordinates.duplicated().any():raise ValueError('Trùng ngày giờ trong tệp; cần kiểm tra và sửa số liệu.')
        if coordinates.dt.tz is not None:raise ValueError('Dùng giờ địa phương thống nhất, không kèm múi giờ.')
        coordinates=coordinates.astype('datetime64[ns]')
    else:
        axis='Buoc'
        coordinates=pd.to_numeric(df[axis],errors='raise') if axis in df else pd.Series(np.arange(1,len(df)+1),index=df.index)
        if not np.all(np.isfinite(coordinates)) or np.any(coordinates<1) or np.any(coordinates!=np.floor(coordinates)) or coordinates.duplicated().any():
            raise ValueError('Buoc phải là số nguyên dương, không trùng.')
    result=pd.DataFrame({axis:coordinates,key:values}).sort_values(axis).reset_index(drop=True)
    missing_values=result[key].isna()
    if key!='Q_ThucDo_m3s' and missing_values.any():
        coordinates=result.loc[missing_values,axis]
        fmt=lambda v:v.strftime('%d/%m/%Y %H:%M:%S') if axis=='ThoiGian' else str(int(v))
        rule='Ô mưa trống được giữ nguyên trong tệp nhập và tính là 0 mm trong khoảng mô phỏng người dùng chọn.' if key=='Mua_mm' else 'Giữ ô bốc hơi trống; khoảng mô phỏng phải có đủ bốc hơi.'
        import_notes.append(f'{SERIES_NAMES[key]}: có {int(missing_values.sum())}/{len(result)} ô trống, từ {fmt(coordinates.iloc[0])} đến {fmt(coordinates.iloc[-1])}. '+rule)
    result.attrs['import_notes']=import_notes
    return result


def series_axis(data):
    return 'ThoiGian' if 'ThoiGian' in data else 'Buoc'


def select_period(data,start='',end=''):
    axis=series_axis(data);result=data
    if axis=='ThoiGian':
        def bound(text,is_end):
            if not str(text).strip():return None
            text=str(text).strip()
            if '/' in text:
                try:value=pd.Timestamp(datetime.strptime(text,'%d/%m/%Y %H:%M:%S' if len(text)>10 else '%d/%m/%Y'))
                except ValueError:raise ValueError('Nhập ngày theo dd/mm/yyyy hh:mm:ss, ví dụ 01/10/1996 01:00:00.') from None
            else:value=pd.Timestamp(text)
            if pd.isna(value) or value.tzinfo is not None:raise ValueError('Ngày giới hạn không hợp lệ hoặc có múi giờ.')
            if is_end and len(str(text).strip())==10:value+=pd.Timedelta(days=1)-pd.Timedelta(nanoseconds=1)
            return value
        lower=bound(start,False);upper=bound(end,True)
    else:
        lower=finite_number(start,'Bước bắt đầu') if str(start).strip() else None
        upper=finite_number(end,'Bước kết thúc') if str(end).strip() else None
        if any(v is not None and (v<1 or v!=int(v)) for v in [lower,upper]):raise ValueError('Giới hạn bước phải là số nguyên dương.')
    if lower is not None and upper is not None and lower>upper:raise ValueError('Bắt đầu phải trước hoặc bằng kết thúc.')
    if lower is not None:result=result[result[axis]>=lower]
    if upper is not None:result=result[result[axis]<=upper]
    return result.copy()


def distribute_evaporation(source,rain,dt):
    """Phân bổ đều tổng PET theo phần thời gian giao nhau, giữ tổng mm."""
    if series_axis(source)!='ThoiGian' or series_axis(rain)!='ThoiGian':return source
    mode=source.attrs.get('pet_mode','step_total')
    times=pd.DatetimeIndex(source['ThoiGian']).as_unit('ns')
    target=pd.DatetimeIndex(rain['ThoiGian']).as_unit('ns')
    if not len(times):return source
    if mode in ['month_total','month_daily_mean']:
        periods=times.to_period('M')
        if periods.duplicated().any():raise ValueError('Bốc hơi tháng có nhiều giá trị trong cùng tháng.')
        left=periods.start_time;right=(periods+1).start_time
    elif mode=='day_total':
        periods=times.to_period('D')
        if periods.duplicated().any():raise ValueError('Bốc hơi ngày có nhiều giá trị trong cùng ngày.')
        left=periods.start_time;right=(periods+1).start_time
    else:
        if len(times)==1:
            if not times.equals(target):raise ValueError('Bốc hơi tổng mỗi bước cần ít nhất 2 thời điểm để biết độ dài bước.')
            hours=dt
        else:
            gaps=np.diff(times.asi8)/3.6e12
            unique,counts=np.unique(gaps,return_counts=True);hours=float(unique[np.argmax(counts)])
            if hours<=0:raise ValueError('Bước bốc hơi phải dương.')
        right=times;left=times-pd.to_timedelta(hours,unit='h')
    bounds_left=left.as_unit('ns').asi8;bounds_right=right.as_unit('ns').asi8
    ends=target.asi8;step=pd.to_timedelta(dt,unit='h').value;starts=ends-step
    amount=np.zeros(len(target));covered=np.zeros(len(target))
    values=source['BocHoi_mm'].to_numpy(dtype=float)
    for lo,hi,value in zip(bounds_left,bounds_right,values):
        if not np.isfinite(value):continue
        first=np.searchsorted(ends,lo,side='right');last=np.searchsorted(starts,hi,side='left')
        overlap=np.maximum(0,np.minimum(ends[first:last],hi)-np.maximum(starts[first:last],lo)).astype(float)
        total=value*((hi-lo)/86400e9) if mode=='month_daily_mean' else value
        amount[first:last]+=total*overlap/(hi-lo);covered[first:last]+=overlap
    amount[~np.isclose(covered,step,rtol=0,atol=1e3)]=np.nan
    result=pd.DataFrame({'ThoiGian':target,'BocHoi_mm':amount})
    result.attrs=dict(source.attrs)
    result.attrs['import_notes']=list(source.attrs.get('import_notes',[]))+[f'Bốc hơi phân bổ đều theo giao khoảng thời gian về bước {dt:g} giờ; không ngoại suy hoặc điền số liệu thiếu.']
    return result


def infer_time_step(stations,inputs):
    frames=[v['data'] for v in stations.values() if v['weight']>0]
    if not frames and 'BocHoi_mm' in inputs:frames.append(inputs['BocHoi_mm'])
    intervals=[]
    for frame in frames:
        if series_axis(frame)!='ThoiGian' or len(frame)<2:continue
        times=pd.to_datetime(frame['ThoiGian']).sort_values()
        gaps=times.diff().dropna().dt.total_seconds().to_numpy()
        gaps=gaps[gaps>0]
        if not len(gaps):continue
        # Khoảng phổ biến; khi bằng số lần xuất hiện chọn khoảng nhỏ hơn.
        unique,counts=np.unique(np.round(gaps,6),return_counts=True)
        intervals.append(float(unique[np.argmax(counts)])/3600)
    if not intervals:return None
    if not np.allclose(intervals,intervals[0],rtol=0,atol=1e-6):raise ValueError('Bước số liệu giữa các trạm mưa/bốc hơi khác nhau; cần thống nhất trước khi mô phỏng.')
    return intervals[0]


def detect_common_period(stations,inputs,dt):
    """Giao mưa/PET và Q nếu có; chọn đoạn liên tục dài nhất, không bắc qua lỗ hổng."""
    if 'BocHoi_mm' not in inputs:return None
    active=[v for v in stations.values() if v['weight']>0]
    if not active:return None
    weights=[finite_number(v['weight'],'Trọng số') for v in stations.values()]
    if any(not 0<=w<=1 for w in weights) or not np.isclose(sum(weights),1,rtol=0,atol=1e-8):raise ValueError('Tổng trọng số trạm mưa phải bằng 1 trước khi nhận diện khoảng chung.')
    pet=distribute_evaporation(inputs['BocHoi_mm'],active[0]['data'],dt)
    data=[(v['data'],'Mua_mm') for v in active]+[(pet,'BocHoi_mm')]
    if 'Q_ThucDo_m3s' in inputs:data.append((inputs['Q_ThucDo_m3s'],'Q_ThucDo_m3s'))
    axis=series_axis(data[0][0]);common=None
    for frame,key in data:
        if series_axis(frame)!=axis:raise ValueError('Các chuỗi phải cùng kiểu ngày giờ hoặc thứ tự bước.')
        index=pd.Index(frame[axis] if key=='Mua_mm' else frame.loc[frame[key].notna(),axis])
        common=index if common is None else common.intersection(index)
    common=common.sort_values()
    if len(common)<2:raise ValueError('Không có ít nhất 2 bước chung đủ mưa, bốc hơi và Q thực đo.')
    gaps=common.to_series().diff().dropna().dt.total_seconds().to_numpy()/3600 if axis=='ThoiGian' else np.diff(common.to_numpy(dtype=float))
    expected=finite_number(dt,'Bước tính',True) if axis=='ThoiGian' else 1.
    cuts=np.r_[0,np.flatnonzero(~np.isclose(gaps,expected,rtol=0,atol=1e-6))+1,len(common)]
    lengths=np.diff(cuts);chosen=int(np.argmax(lengths));lo,hi=cuts[chosen],cuts[chosen+1]
    if hi-lo<2:raise ValueError('Các thời điểm chung không liên tục theo bước tính đã nhập.')
    fmt=lambda x:x.strftime('%d/%m/%Y %H:%M:%S') if axis=='ThoiGian' else str(int(x))
    return fmt(common[lo]),fmt(common[hi-1]),len(lengths),int(hi-lo)


def weighted_rainfall(stations,start='',end=''):
    if not stations:raise ValueError('Chưa nhập trạm mưa.')
    weights=[finite_number(v['weight'],'Trọng số') for v in stations.values()]
    if any(w<0 or w>1 for w in weights) or not np.isclose(sum(weights),1,rtol=0,atol=1e-8):
        raise ValueError(f'Tổng trọng số trạm mưa phải bằng 1 (hiện tại {sum(weights):.6f}); mỗi trọng số thuộc [0;1].')
    result=None;axis=None
    for item in stations.values():
        if item['weight']==0:continue
        data=select_period(item['data'],start,end)
        if data.empty:raise ValueError('Trạm mưa không có số liệu trong khoảng mô phỏng.')
        current_axis=series_axis(data);series=data.set_index(current_axis)['Mua_mm'].fillna(0.0)
        if result is None:result=series*item['weight'];axis=current_axis
        else:
            if current_axis!=axis or not series.index.equals(result.index):raise ValueError('Các trạm có trọng số >0 phải khớp ngày giờ hoặc cùng số bước; không trộn hai kiểu nhập.')
            result=result+series*item['weight']
    return result.rename('Mua_mm').reset_index()


def weighted_evaporation(stations,rain,dt):
    """Phân bổ từng trạm PET về bước tính trước khi lấy bình quân Thiessen."""
    active=[item for item in stations.values() if item['weight']>0]
    if not active or not np.isclose(sum(item['weight'] for item in active),1,atol=1e-8,rtol=0):
        raise ValueError('Trọng số các trạm bốc hơi phải có tổng bằng 1.')
    axis=series_axis(rain);target=pd.Index(rain[axis]);total=np.zeros(len(rain))
    notes=[]
    for item in active:
        source=item['data']
        if series_axis(source)!=axis:raise ValueError('Các trạm bốc hơi và mưa phải cùng kiểu thời gian/bước.')
        distributed=distribute_evaporation(source,rain,dt)
        values=distributed.set_index(axis)['BocHoi_mm'].reindex(target).to_numpy(dtype=float)
        total+=item['weight']*values
        notes.extend(source.attrs.get('import_notes',[]))
    result=pd.DataFrame({axis:rain[axis].to_numpy(),'BocHoi_mm':total})
    result.attrs={'pet_mode':'step_total','import_notes':notes+['Bốc hơi bình quân theo Thiessen; không điền hoặc phân phối lại trọng số khi thiếu số liệu.']}
    return result


def merge_series(series,dt,start='',end=''):
    dt=finite_number(dt,'Bước giờ',True)
    if not all(k in series for k in ['Mua_mm','BocHoi_mm']):raise ValueError('Nhập đủ mưa và bốc hơi trước khi mô phỏng.')
    axis=series_axis(series['Mua_mm'])
    if any(series_axis(data)!=axis for data in series.values()):raise ValueError('Dùng cùng kiểu cho các chuỗi: tất cả có ThoiGian hoặc tất cả theo thứ tự bước. Không tự ghép hai kiểu.')
    selected_rain=select_period(series['Mua_mm'],start,end)
    selected_rain=selected_rain.copy();selected_rain['Mua_mm']=selected_rain['Mua_mm'].fillna(0.0)
    rain=selected_rain.set_index(axis);pet=distribute_evaporation(series['BocHoi_mm'],selected_rain,dt).set_index(axis)
    if rain.empty:raise ValueError('Không có mưa trong khoảng mô phỏng đã chọn.')
    if not rain.index.equals(pet.index):raise ValueError('Mưa/bốc hơi phải khớp ngày giờ hoặc số bước; không tự cắt chuỗi hay điền 0.')
    if axis=='Buoc' and not np.array_equal(rain.index.to_numpy(),np.arange(rain.index[0],rain.index[0]+len(rain))):
        raise ValueError('Chuỗi mưa/bốc hơi cần đủ các bước liên tiếp trong khoảng mô phỏng.')
    df=rain.join(pet);outside=0
    if 'Q_ThucDo_m3s' in series:
        q=series['Q_ThucDo_m3s'].set_index(axis)
        outside=int(((q.index<df.index.min())|(q.index>df.index.max())).sum())
        q=q[(q.index>=df.index.min())&(q.index<=df.index.max())]
        if not q.index.isin(df.index).all():raise ValueError('Q thực đo trong khoảng mô phỏng bị lệch ngày giờ/bước so với mưa; cần kiểm tra nguồn.')
        df=df.join(q)
    result=validate_data(df.reset_index(),dt)
    result.attrs['outside_Q_count']=outside
    return result


def route_linear(storage, inflow, dt, k):
    """Bể tuyến tính: trữ lượng mm, inflow mm/giờ, out tổng mm trong dt."""
    e=np.exp(-dt/k)
    new=storage*e+inflow*k*(-np.expm1(-dt/k))
    out=storage+inflow*dt-new
    return max(new,0.), max(out,0.)


def route_cascade(storage, inflow, dt, k):
    """Nghiệm chính xác hai bể tuyến tính nối tiếp, đầu vào đều trong dt."""
    s1,s2=storage
    e=np.exp(-dt/k);one=-np.expm1(-dt/k)
    a=s1*e+inflow*k*one
    b=s2*e+s1*(dt/k)*e+inflow*(k*one-dt*e)
    out=s1+s2+inflow*dt-a-b
    return (max(a,0.),max(b,0.)),max(out,0.)


MODEL_VERSION='NAM9-mean-endpoint-2026-10'


def overland_time_constant(flow_mm_hour,ck12):
    """IJISET tr.665: CK=CK12 khi OF≤0.4; nếu lớn hơn, CK12(OF/0.4)^−0.4."""
    return ck12 if flow_mm_hour<=.4 else ck12*(flow_mm_hour/.4)**(-.4)


def overland_discharge(storage_mm,ck12):
    """Giải q=S/CK(q); bảo đảm q mm/h và trữ lượng S mm."""
    if storage_mm<=.4*ck12:return max(storage_mm,0.)/ck12
    return (storage_mm/(ck12*.4**.4))**(1/.6)


def route_overland(storage,inflow,dt,ck12,max_step=.25,cancel_event=None):
    """Hai bể nối tiếp, CK chung lấy từ dòng tràn ở bể thứ hai.

    Tích phân chia bước, giữ CK trong từng bước nhỏ; nghiệm tuyến tính chính
    xác tại mỗi bước. Đây là lựa chọn bộ giải của bản Python, không tuyên bố
    trùng bộ giải nội bộ DHI. Lượng ra tính từ cân bằng trữ lượng.
    """
    remaining=dt;total=0.;minimum_k=ck12;iterations=0
    while remaining>max(1e-12,dt*1e-12):
        if cancel_event is not None and cancel_event.is_set():raise CalibrationStopped()
        flow=overland_discharge(storage[1],ck12);k=overland_time_constant(flow,ck12)
        h=min(remaining,max_step,k/8)
        storage,out=route_cascade(storage,inflow,h,k)
        total+=out;remaining-=h;minimum_k=min(minimum_k,k);iterations+=1
        if iterations>100000:raise ValueError('Điều tiết cần quá nhiều bước nhỏ; kiểm tra CK12 và lượng mưa.')
    return storage,total,minimum_k


class CalibrationStopped(Exception):
    pass




def _kernel_route_linear(storage, inflow, dt, k):
    """Bể tuyến tính: trữ lượng mm, inflow mm/giờ, out tổng mm trong dt."""
    e=np.exp(-dt/k)
    new=storage*e+inflow*k*(-np.expm1(-dt/k))
    out=storage+inflow*dt-new
    return max(new,0.), max(out,0.)

def _kernel_route_cascade(storage, inflow, dt, k):
    """Nghiệm chính xác hai bể tuyến tính nối tiếp, đầu vào đều trong dt."""
    s1,s2=storage
    e=np.exp(-dt/k);one=-np.expm1(-dt/k)
    a=s1*e+inflow*k*one
    b=s2*e+s1*(dt/k)*e+inflow*(k*one-dt*e)
    out=s1+s2+inflow*dt-a-b
    return (max(a,0.),max(b,0.)),max(out,0.)

def _kernel_overland_time_constant(flow_mm_hour,ck12):
    """IJISET tr.665: CK=CK12 khi OF≤0.4; nếu lớn hơn, CK12(OF/0.4)^−0.4."""
    return ck12 if flow_mm_hour<=.4 else ck12*(flow_mm_hour/.4)**(-.4)

def _kernel_overland_discharge(storage_mm,ck12):
    """Giải q=S/CK(q); bảo đảm q mm/h và trữ lượng S mm."""
    if storage_mm<=.4*ck12:return max(storage_mm,0.)/ck12
    return (storage_mm/(ck12*.4**.4))**(1/.6)

def _kernel_route_overland(storage,inflow,dt,ck12,max_step=.25):
    """Hai bể nối tiếp, CK chung lấy từ dòng tràn ở bể thứ hai.

    Tích phân chia bước, giữ CK trong từng bước nhỏ; nghiệm tuyến tính chính
    xác tại mỗi bước. Đây là lựa chọn bộ giải của bản Python, không tuyên bố
    trùng bộ giải nội bộ DHI. Lượng ra tính từ cân bằng trữ lượng.
    """
    remaining=dt;total=0.;minimum_k=ck12;iterations=0
    while remaining>max(1e-12,dt*1e-12):
        flow=_kernel_overland_discharge(storage[1],ck12);k=_kernel_overland_time_constant(flow,ck12)
        h=min(remaining,max_step,k/8)
        storage,out=_kernel_route_cascade(storage,inflow,h,k)
        total+=out;remaining-=h;minimum_k=min(minimum_k,k);iterations+=1
        if iterations>100000:raise ValueError('Điều tiết cần quá nhiều bước nhỏ; kiểm tra CK12 và lượng mưa.')
    return storage,total,minimum_k

def _nam_kernel(p,rain,pet,dt,sub,U,L,surf,inter,base):
    n=len(rain);components=np.zeros((n,3));endpoints=np.zeros((n,3));evap=np.zeros(n);stores=np.zeros(n);residual=np.zeros(n);ck_of=np.full(n,p[3])
    steps=int(np.ceil(dt/sub));h=dt/steps
    for t in range(n):
        before=U+L+sum(surf)+sum(inter)+base
        for _ in range(steps):
            U+=rain[t]/steps
            eu=min(U,pet[t]/steps);U-=eu
            el=min(L,(pet[t]/steps-eu)*L/p[1]);L-=el
            evap[t]+=eu+el
            moisture=L/p[1]
            threshold=lambda x:max((moisture-x)/(1-x),0.)
            # IF rút nước bể mặt trước khi xác định Pn, theo cân bằng Pn
            # có trừ IF tại IJISET tr.664. U dùng để sinh IF không vượt Umax.
            surface_available=min(U,p[0])
            inf_flow=surface_available*(-np.expm1(-threshold(p[5])*h/p[7]));U-=inf_flow
            excess=max(U-p[0],0.);U-=excess
            of=p[2]*threshold(p[4])*excess
            infiltration=excess-of;recharge=infiltration*threshold(p[6])
            L+=infiltration-recharge
            # Bể rễ đầy: phần thấm vượt sức chứa bổ cập ngầm, không mất nước.
            spill=max(L-p[1],0.);L-=spill;recharge+=spill
            surf,qo,kmin=_kernel_route_overland(surf,of/h,h,p[3])
            ck_of[t]=min(ck_of[t],kmin)
            inter,qi=_kernel_route_cascade(inter,inf_flow/h,h,p[3])
            base,qb=_kernel_route_linear(base,recharge/h,h,p[8])
            components[t]+=np.array([qo,qi,qb])
        endpoints[t]=np.array([_kernel_overland_discharge(surf[1],p[3]),inter[1]/p[3],base/p[8]])
        stores[t]=U+L+sum(surf)+sum(inter)+base
        residual[t]=before+rain[t]-evap[t]-components[t].sum()-stores[t]
    return components,evap,stores,residual,ck_of,U,L,surf,inter,base,endpoints

if NUMBA_AVAILABLE:
    def _compile_nam(function):
        # Reuse compiled code across sessions; packaged apps may lack a cache locator.
        try:return njit(nogil=True,cache=True)(function)
        except RuntimeError:return njit(nogil=True)(function)
    _kernel_route_linear=_compile_nam(_kernel_route_linear)
    _kernel_route_cascade=_compile_nam(_kernel_route_cascade)
    _kernel_overland_time_constant=_compile_nam(_kernel_overland_time_constant)
    _kernel_overland_discharge=_compile_nam(_kernel_overland_discharge)
    _kernel_route_overland=_compile_nam(_kernel_route_overland)
    _nam_kernel=_compile_nam(_nam_kernel)


def calibration_discharge(params,area,rain,pet,dt,initial,cancel_event,mode):
    """Same NAM kernel as the full report, without constructing report arrays."""
    if not NUMBA_AVAILABLE:
        return run_nam(params,area,rain,pet,dt,initial,cancel_event=cancel_event,use_acceleration=False,discharge_mode=mode)['Q_sim']
    area=float(area);dt=float(dt)
    p=np.array([params[k] for k in PARAM_KEYS],dtype=float)
    U=initial['U_fraction']*p[0];L=initial['L_fraction']*p[1]
    qs=initial['Q_surf_m3s']*3.6/area;qi=initial['Q_inter_m3s']*3.6/area
    surf=(qs*overland_time_constant(qs,p[3]),)*2;inter=(qi*p[3],)*2
    base=initial['Q_base_m3s']*3.6/area*p[8]
    flow=np.empty(len(rain))
    for start in range(0,len(rain),256):
        if cancel_event.is_set():raise CalibrationStopped()
        stop=min(start+256,len(rain))
        result=_nam_kernel(p,rain[start:stop],pet[start:stop],dt,1.,U,L,surf,inter,base)
        flow[start:stop]=result[-1].sum(axis=1)*area/3.6 if mode=='endpoint' else result[0].sum(axis=1)*area/(3.6*dt)
        U,L,surf,inter,base=result[5:10]
    return flow


def run_nam(params, area_km2, rain, pet, dt_hours, initial=None, max_substep_hours=1., cancel_event=None, use_acceleration=True, discharge_mode='mean'):
    """NAM 9 thông số: dòng tràn có CK biến đổi; sát mặt CK12 tuyến tính.

    Không tuyên bố tương đương bộ giải MIKE NAM. P/PET là mm mỗi bước;
    Q là lưu lượng TRUNG BÌNH bước. Điều tiết bảo toàn thể tích với hai bể
    nối tiếp cho dòng tràn/sát mặt và một bể dòng ngầm. Chia bước nội bộ
    ≤1 giờ; không nội suy trận mưa chưa quan trắc trong bước lớn.
    """
    if discharge_mode not in ['mean','endpoint']:raise ValueError('Loại lưu lượng phải là mean hoặc endpoint.')
    p={k:finite_number(params[k],k) for k in PARAM_KEYS}
    for k in ['U_max','L_max','CK_12','CK_IF','CK_BF']:
        if p[k]<=0:raise ValueError(f'{k} phải lớn hơn 0.')
    if not 0<=p['CQOF']<=1 or any(not 0<=p[k]<1 for k in ['TOF','TIF','TG']):
        raise ValueError('CQOF thuộc [0;1]; TOF, TIF, TG thuộc [0;1).')
    area=finite_number(area_km2,'Diện tích',True);dt=finite_number(dt_hours,'Bước tính',True)
    sub=finite_number(max_substep_hours,'Bước nội bộ',True)
    rain=np.asarray(rain,dtype=float);pet=np.asarray(pet,dtype=float)
    if rain.ndim!=1 or pet.shape!=rain.shape or not len(rain) or not np.all(np.isfinite(rain)) or not np.all(np.isfinite(pet)) or np.any(rain<0) or np.any(pet<0):
        raise ValueError('Mưa/PET phải là hai chuỗi một chiều cùng độ dài, hữu hạn và không âm.')
    init={'U_fraction':.2,'L_fraction':.5,'Q_base_m3s':0.,'Q_surf_m3s':0.,'Q_inter_m3s':0.}
    if initial:init.update(initial)
    init={k:finite_number(v,k) for k,v in init.items()}
    if any(not 0<=init[k]<=1 for k in ['U_fraction','L_fraction']) or any(init[k]<0 for k in ['Q_base_m3s','Q_surf_m3s','Q_inter_m3s']):
        raise ValueError('Độ đầy ban đầu thuộc [0;1]; dòng ngầm ban đầu không âm.')
    U=init['U_fraction']*p['U_max'];L=init['L_fraction']*p['L_max']
    qs=init['Q_surf_m3s']*3.6/area;qi=init['Q_inter_m3s']*3.6/area
    surf=(qs*overland_time_constant(qs,p['CK_12']),)*2
    inter=(qi*p['CK_12'],)*2
    base=init['Q_base_m3s']*3.6/area*p['CK_BF']
    initial_storage=U+L+sum(surf)+sum(inter)+base
    if use_acceleration and NUMBA_AVAILABLE:
        vector=np.array([p[k] for k in PARAM_KEYS],dtype=np.float64)
        blocks=[];endpoint_blocks=[]
        for start in range(0,len(rain),64):
            if cancel_event is not None and cancel_event.is_set():raise CalibrationStopped()
            result=_nam_kernel(vector,np.ascontiguousarray(rain[start:start+64]),np.ascontiguousarray(pet[start:start+64]),dt,sub,U,L,surf,inter,base)
            blocks.append(result[:5]);endpoint_blocks.append(result[-1]);U,L,surf,inter,base=result[5:10]
        components,evap,stores,residual,ck_of=[np.concatenate([block[j] for block in blocks],axis=0) for j in range(5)]
        conv=area/(3.6*dt)
        return select_discharge(dict(Q_sim=components.sum(axis=1)*conv,Q_surf=components[:,0]*conv,Q_inter=components[:,1]*conv,Q_base=components[:,2]*conv,
                    Evap_actual_mm=evap,Storage_mm=stores,Balance_error_mm=residual,CK_overland_min_hours=ck_of,Model_version=MODEL_VERSION,
                    Initial_storage_mm=initial_storage,Initial_state=init,
                    Final_state=dict(U_mm=U,L_mm=L,surface_mm=surf,interflow_mm=inter,base_mm=base),Engine='Numba'),np.concatenate(endpoint_blocks)*area/3.6,discharge_mode)
    n=len(rain);components=np.zeros((n,3));endpoints=np.zeros((n,3));evap=np.zeros(n);stores=np.zeros(n);residual=np.zeros(n);ck_of=np.full(n,p["CK_12"])
    steps=int(np.ceil(dt/sub));h=dt/steps
    for t in range(n):
        if cancel_event is not None and cancel_event.is_set():raise CalibrationStopped()
        before=U+L+sum(surf)+sum(inter)+base
        for _ in range(steps):
            U+=rain[t]/steps
            eu=min(U,pet[t]/steps);U-=eu
            el=min(L,(pet[t]/steps-eu)*L/p['L_max']);L-=el
            evap[t]+=eu+el
            moisture=L/p['L_max']
            threshold=lambda x:max((moisture-x)/(1-x),0.)
            # IF rút nước bể mặt trước khi xác định Pn, theo cân bằng Pn
            # có trừ IF tại IJISET tr.664. U dùng để sinh IF không vượt Umax.
            surface_available=min(U,p['U_max'])
            inf_flow=surface_available*(-np.expm1(-threshold(p['TIF'])*h/p['CK_IF']));U-=inf_flow
            excess=max(U-p['U_max'],0.);U-=excess
            of=p['CQOF']*threshold(p['TOF'])*excess
            infiltration=excess-of;recharge=infiltration*threshold(p['TG'])
            L+=infiltration-recharge
            # Bể rễ đầy: phần thấm vượt sức chứa bổ cập ngầm, không mất nước.
            spill=max(L-p['L_max'],0.);L-=spill;recharge+=spill
            surf,qo,kmin=route_overland(surf,of/h,h,p['CK_12'],cancel_event=cancel_event)
            ck_of[t]=min(ck_of[t],kmin)
            inter,qi=route_cascade(inter,inf_flow/h,h,p['CK_12'])
            base,qb=route_linear(base,recharge/h,h,p['CK_BF'])
            components[t]+=np.array([qo,qi,qb])
        endpoints[t]=np.array([overland_discharge(surf[1],p['CK_12']),inter[1]/p['CK_12'],base/p['CK_BF']])
        stores[t]=U+L+sum(surf)+sum(inter)+base
        residual[t]=before+rain[t]-evap[t]-components[t].sum()-stores[t]
    conv=area/(3.6*dt)
    return select_discharge(dict(Q_sim=components.sum(axis=1)*conv,Q_surf=components[:,0]*conv,
                Q_inter=components[:,1]*conv,Q_base=components[:,2]*conv,
                Evap_actual_mm=evap,Storage_mm=stores,Balance_error_mm=residual,CK_overland_min_hours=ck_of,Model_version=MODEL_VERSION,
                Initial_storage_mm=initial_storage,Initial_state=init,Engine='Python',
                Final_state=dict(U_mm=U,L_mm=L,surface_mm=surf,interflow_mm=inter,base_mm=base)),endpoints*area/3.6,discharge_mode)


def select_discharge(result,endpoints,mode):
    """Trung bình bước bảo toàn thể tích; cuối bước lấy lưu lượng từ trạng thái bể."""
    for index,key in enumerate(['Q_surf','Q_inter','Q_base']):
        result[key+'_mean']=result[key].copy()
        result[key+'_endpoint']=endpoints[:,index]
        if mode=='endpoint':result[key]=result[key+'_endpoint']
    result['Q_sim_mean']=result['Q_sim'].copy()
    result['Q_sim_endpoint']=endpoints.sum(axis=1)
    result['Q_sim']=result['Q_sim_'+mode]
    result['Discharge_mode']=mode
    return result


def compute_nse(obs,sim):
    obs=np.asarray(obs,dtype=float);sim=np.asarray(sim,dtype=float)
    if obs.shape!=sim.shape:raise ValueError('Hai chuỗi đánh giá phải cùng kích thước.')
    # Thiếu quan trắc được bỏ; mô phỏng không hữu hạn tại điểm đo là lỗi.
    valid=np.isfinite(obs)
    if np.any(~np.isfinite(sim[valid])):return np.nan
    o,s=obs[valid],sim[valid]
    denominator=np.sum((o-o.mean())**2) if len(o)>=2 else 0.
    return float(1-np.sum((o-s)**2)/denominator) if denominator>0 else np.nan


def compute_metrics(obs,sim):
    obs=np.asarray(obs,dtype=float);sim=np.asarray(sim,dtype=float)
    valid=np.isfinite(obs)&np.isfinite(sim);o=obs[valid];s=sim[valid]
    # PBIAS theo quy ước tổng (đo - mô phỏng)/tổng đo: dương = thiếu nước.
    return dict(nse=compute_nse(obs,sim),pbias=100*np.sum(o-s)/np.sum(o) if len(o) and np.sum(o)>0 else np.nan,
                observed_peak=float(o.max()) if len(o) else np.nan,
                simulated_peak=float(s.max()) if len(s) else np.nan,n=int(len(o)))


# ==============================================================================
# 2. GIAO DIỆN PHẦN MỀM MÁY TÍNH (TKINTER DESKTOP APP)
# ==============================================================================


def _geo_modules():
    try:
        import geopandas as gpd
        from shapely.geometry import shape, mapping, Polygon
        from shapely.ops import transform, unary_union
        from pyproj import CRS, Transformer
    except ImportError as exc:
        raise ValueError('Cần cài thư viện bản đồ: python -m pip install geopandas shapely pyproj') from exc
    return gpd,shape,mapping,Polygon,transform,unary_union,CRS,Transformer


def resolve_horizontal_crs(value):
    """EPSG/ESRI, WKT, PROJ hoặc nội dung tệp PRJ; không suy đoán datum/múi chiếu."""
    _,_,_,_,_,_,CRS,_=_geo_modules()
    text=str(value).strip()
    if not text:raise ValueError('Cần khai báo hệ tọa độ nguồn.')
    if text.isdigit():text='EPSG:'+text
    if len(text)<250 and Path(text).suffix.lower() in ('.prj','.wkt') and Path(text).is_file():
        text=Path(text).read_text(encoding='utf-8-sig')
    try:crs=CRS.from_user_input(text)
    except Exception as exc:raise ValueError('Không nhận diện được hệ tọa độ. Dùng mã EPSG/ESRI, WKT, PROJ hoặc đọc tệp .prj đúng của dữ liệu.') from exc
    if not (crs.is_geographic or crs.is_projected or crs.is_geocentric):
        raise ValueError('Cần hệ tọa độ ngang hoặc địa tâm, không dùng hệ cao độ riêng.')
    return crs


def vn2000_projected_crs(meridian,scale=.9999,false_east=500000.,false_north=0.,latitude_origin=0.):
    """TM tùy chỉnh, giữ datum VN-2000 từ EPSG:3405, không giả định datum WGS84."""
    _,_,_,_,_,_,CRS,_=_geo_modules()
    meridian=finite_number(meridian,'Kinh tuyến trục');scale=finite_number(scale,'Hệ số tỷ lệ',True)
    latitude_origin=finite_number(latitude_origin,'Vĩ độ gốc')
    if not -180<=meridian<=180 or not -90<latitude_origin<90:raise ValueError('Kinh tuyến trục/vĩ độ gốc không hợp lệ.')
    definition=CRS.from_epsg(3405).to_json_dict()
    for key in ('id','scope','area','bbox'):definition.pop(key,None)
    definition['name']=f'VN-2000 / TM {meridian} k={scale}'
    conversion=definition['conversion'];conversion.pop('id',None);conversion['name']='Transverse Mercator tùy chỉnh'
    values={'Latitude of natural origin':latitude_origin,'Longitude of natural origin':meridian,
            'Scale factor at natural origin':scale,'False easting':finite_number(false_east,'Easting gốc'),
            'False northing':finite_number(false_north,'Northing gốc')}
    for parameter in conversion['parameters']:parameter['value']=values[parameter['name']]
    return CRS.from_json_dict(definition)


def horizontal_transformer(source,target):
    _,_,_,_,_,_,_,Transformer=_geo_modules()
    try:return Transformer.from_crs(source,target,always_xy=True,allow_ballpark=False)
    except Exception as exc:
        raise ValueError('Chưa có phép chuyển datum phù hợp giữa hai hệ tọa độ. Kiểm tra hệ nguồn hoặc dữ liệu chuyển đổi PROJ; không tự dịch điểm.') from exc


def frame_to_wgs84(frame):
    """SHP luôn đọc x/y theo Easting/Northing, kể cả khi tên trục EPSG đảo thứ tự."""
    _,_,_,_,transform,_,_,_=_geo_modules()
    if frame.crs is None:raise ValueError('Dữ liệu chưa có hệ tọa độ nguồn.')
    source=frame.crs if frame.crs.is_geocentric else frame.crs.to_2d()
    operation=horizontal_transformer(source,4326)
    def convert(x,y,z=None):
        values=operation.transform(x,y,z,errcheck=True) if source.is_geocentric and z is not None else operation.transform(x,y,errcheck=True)
        return values[:2]
    result=frame.copy();result.geometry=result.geometry.map(lambda geom:transform(convert,geom))
    return result.set_crs(4326,allow_override=True)


def basin_metric_geometry(geojson,target_crs=None):
    _,shape,_,_,transform,_,CRS,Transformer=_geo_modules()
    basin=shape(geojson)
    if basin.geom_type not in ('Polygon','MultiPolygon') or basin.is_empty or not basin.is_valid:
        raise ValueError('Ranh giới phải là Polygon/MultiPolygon hợp lệ, không rỗng.')
    west,south,east,north=basin.bounds
    if not (-180<=west<=east<=180 and -90<south<=north<90):raise ValueError('Tọa độ lưu vực WGS84 không hợp lệ.')
    center=basin.centroid
    crs=resolve_horizontal_crs(target_crs) if target_crs is not None else CRS.from_proj4(f'+proj=laea +lat_0={center.y} +lon_0={center.x} +datum=WGS84 +units=m +no_defs')
    if not crs.is_projected or any(not np.isclose(axis.unit_conversion_factor,1.) for axis in crs.axis_info[:2]):
        raise ValueError('Hệ hiển thị/tính diện tích phải là hệ phẳng đơn vị mét.')
    forward=horizontal_transformer(4326,crs)
    def horizontal(x,y,z=None):return forward.transform(x,y,errcheck=True)
    metric=transform(horizontal,basin)
    if not metric.is_valid or not np.isfinite(metric.area) or metric.area<=0:
        raise ValueError('Không tính được diện tích lưu vực.')
    return metric,crs,forward


def thiessen_basin_weights(geojson,positions):
    """Giao các nửa mặt phẳng gần nhất với lưu vực; hỗ trợ 1, 2 trạm và trạm thẳng hàng."""
    _,_,_,Polygon,_,_,_,_= _geo_modules()
    basin,crs,forward=basin_metric_geometry(geojson)
    names=list(positions)
    if not names:raise ValueError('Chưa có vị trí trạm mưa.')
    points=np.array([forward.transform(*positions[name]) for name in names],dtype=float)
    if not np.isfinite(points).all():raise ValueError('Tọa độ trạm mưa không hợp lệ.')
    origin=np.array(basin.centroid.coords[0]);points-=origin
    xmin,ymin,xmax,ymax=basin.bounds;pad=max(xmax-xmin,ymax-ymin,1.)*.01+1.
    box=[np.array([xmin-pad,ymin-pad])-origin,np.array([xmax+pad,ymin-pad])-origin,
         np.array([xmax+pad,ymax+pad])-origin,np.array([xmin-pad,ymax+pad])-origin]
    areas=[];cells=[]
    for i,point in enumerate(points):
        vertices=list(box)
        for j,other in enumerate(points):
            if i==j:continue
            normal=other-point;distance=np.linalg.norm(normal)
            if distance<.001:raise ValueError('Hai trạm có vị trí trùng nhau; không xác định được trọng số riêng.')
            normal/=distance;boundary=float(np.dot(normal,(other+point)*.5))
            clipped=[]
            for a,b in zip(vertices,vertices[1:]+vertices[:1]):
                da=float(np.dot(normal,a)-boundary);db=float(np.dot(normal,b)-boundary)
                inside_a=da<=0;inside_b=db<=0
                if inside_a:clipped.append(a)
                if inside_a!=inside_b:clipped.append(a+(b-a)*da/(da-db))
            vertices=clipped
            if not vertices:break
        cell=basin.intersection(Polygon(np.array(vertices)+origin)) if len(vertices)>=3 else Polygon()
        cells.append(cell);areas.append(cell.area)
    total=float(sum(areas))
    if not np.isclose(total,basin.area,rtol=1e-8,atol=.01):raise ValueError('Diện tích các vùng Thiessen chưa khớp lưu vực.')
    return dict(weights=dict(zip(names,np.array(areas)/total)),areas_km2=dict(zip(names,np.array(areas)/1e6)),
                cells=dict(zip(names,cells)),basin=basin,crs=crs,forward=forward,area_km2=basin.area/1e6)


def cumulative_water_volume(observed,simulated_mean,dt_hours,discharge_mode='mean'):
    """Tổng lượng nước m³; chỉ cộng các khoảng có đủ quan trắc.

    Q trung bình: W=Q*Δt. Q tức thời: quan trắc tích phân hình thang
    giữa hai điểm liền kề; không nối qua khoảng thiếu, không suy đoán
    Q đầu chuỗi. Mô phỏng luôn dùng Q trung bình bước để giữ cân bằng nước.
    """
    obs=np.asarray(observed,dtype=float);sim=np.asarray(simulated_mean,dtype=float)
    if obs.ndim!=1 or obs.shape!=sim.shape:raise ValueError('Hai chuỗi tổng lượng phải cùng kích thước.')
    dt=finite_number(dt_hours,'Bước tính tổng lượng',True)*3600.
    if discharge_mode not in ('mean','endpoint'):raise ValueError('Loại lưu lượng không hợp lệ.')
    observed_mean=obs.copy()
    if discharge_mode=='endpoint':
        observed_mean[:]=np.nan
        observed_mean[1:]=(obs[:-1]+obs[1:])*.5
    valid=np.isfinite(observed_mean)&np.isfinite(sim)
    observed_total=np.cumsum(np.where(valid,observed_mean*dt,0.))
    simulated_total=np.cumsum(np.where(valid,sim*dt,0.))
    return dict(observed_m3=np.where(valid,observed_total,np.nan),
                simulated_m3=np.where(valid,simulated_total,np.nan),valid=valid,
                observed_total_m3=float(observed_total[-1]) if len(obs) else 0.,
                simulated_total_m3=float(simulated_total[-1]) if len(obs) else 0.)


class NAMDesktopApp:

    def __init__(self, root: tk.Tk, validation_params=None):
        self.validation_mode=validation_params is not None
        self._calibrated_params=None
        self.root = root
        self.root.title(
            "Phần mềm Thủy văn NAM - Tự động Hiệu chỉnh Thông số (Nash-Sutcliffe)"
        )
        self.root.geometry("1280x900")
        self.root.minsize(1050, 850)

        # Dữ liệu nội bộ
        self.df_data = None
        self.input_series={}
        self.rain_stations={}
        self._basin_geojson=None;self._basin_source='';self._station_positions={}
        self._basin_input_crs=None;self._map_crs_wkt=None
        self._thiessen_result=None;self._map_pick=False
        self.show_thiessen=tk.BooleanVar(value=False)
        self._shape_basins=[];self._basins={};self._active_basin_id=None
        self._evap_stations={};self._evap_positions={};self._evap_thiessen=None
        self._spatial_signature=None;self._parameter_source=None;self._independent_metrics=None
        self._is_demo=False
        self.auto_period=tk.BooleanVar(value=True)
        self.auto_dt=tk.BooleanVar(value=True)
        self.best_params = {
            "U_max": 15.0,
            "L_max": 100.0,
            "CQOF": 0.50,
            "CK_12": 15.0,
            "TOF": 0.20,
            "TIF": 0.20,
            "TG": 0.30,
            "CK_IF": 50.0,
            "CK_BF": 1000.0,
        }
        self.param_bounds=list(PARAM_BOUNDS)
        self.current_sim = None

        self._setup_style()
        self._build_ui()
        self._busy=False;self._worker_queue=queue.Queue();self._result_signature=None;self._stop_event=threading.Event()
        if self.validation_mode:
            self.best_params=validation_params.copy()
            self.root.title('NAM — Kiểm định độc lập với bộ thông số cố định')
            self.ent_split.delete(0,'end');self.ent_split.insert(0,'100');self.ent_split.config(state='readonly')
            self.btn_edit.config(state=tk.DISABLED)
        self._update_parameter_display()
        self._project_path=None
        self._project_defaults=self._project_payload()
        self._saved_project=self._project_text()
        self._update_project_title()
        self.root.protocol('WM_DELETE_WINDOW',self._close_project)
        self.root.after(300,self._watch)

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        self.root.configure(background='#eef2f7')
        style.configure('.',background='#eef2f7',foreground='#20334d',font=('Segoe UI',10))
        style.configure('TFrame',background='#eef2f7')
        style.configure('TButton',font=('Segoe UI',10),padding=(10,7),background='white',bordercolor='#c5d2e0')
        style.map('TButton',background=[('active','#dfebf7'),('disabled','#e5eaf0')])
        style.configure('Treeview',background='white',fieldbackground='white',rowheight=28)
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),padding=7)
        style.map('Treeview',background=[('selected','#2367a0')],foreground=[('selected','white')])
        style.configure('TNotebook.Tab',padding=(14,8),background='#e2eaf4')
        style.map('TNotebook.Tab',background=[('selected','white')],foreground=[('selected','#174d7d')])
        style.configure('TEntry',padding=4)
        style.configure('TProgressbar',background='#2367a0')
        style.configure('Accent.TButton',font=('Segoe UI',10,'bold'),background='#2367a0',foreground='white',padding=(12,9))
        style.map('Accent.TButton',background=[('active','#174d7d'),('disabled','#ccd6e1')],foreground=[('disabled','#64748b')])
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"),foreground="#174d7d",padding=(0,7))

    def _build_ui(self):
        heading=ttk.Frame(self.root,padding=(16,10));heading.pack(fill='x')
        ttk.Label(heading,text='NAM · Mưa và dòng chảy lưu vực',font=('Segoe UI',16,'bold'),foreground='#174d7d').pack(anchor='w')
        ttk.Label(heading,text='Quản lý lưu vực và trạm · Hiệu chỉnh thông số · Kiểm định độc lập · Trích kết quả',foreground='#52657c').pack(anchor='w',pady=(3,0))
        project_bar=ttk.Frame(self.root,padding=(8,5))
        project_bar.pack(fill='x')
        for label,command in [('Tạo dự án mới',self._new_project),('Mở dự án',self._open_project),('Lưu dự án',self._save_project),('Lưu dự án thành…',lambda:self._save_project(save_as=True))]:
            ttk.Button(project_bar,text=label,command=command).pack(side='left',padx=3)
        self.lbl_project=ttk.Label(project_bar,text='Dự án mới')
        self.lbl_project.pack(side='right',padx=8)
        self.root.bind('<Control-s>',lambda event:self._save_project())
        self.root.bind('<Control-o>',lambda event:self._open_project())
        self.root.bind('<Control-n>',lambda event:self._new_project())
        # Khung chính chia 2 cột: Trái (Điều khiển & Tham số), Phải (Đồ thị)
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- KHUNG BÊN TRÁI: ĐIỀU KHIỂN ---
        left_outer=ttk.Frame(main_paned,width=420)
        main_paned.add(left_outer,weight=0)
        controls=tk.Canvas(left_outer,width=420,background="#eef2f7",highlightthickness=0)
        scroll=ttk.Scrollbar(left_outer,orient='vertical',command=controls.yview)
        controls.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');controls.pack(side='left',fill='both',expand=True)
        left_frame=ttk.Frame(controls,padding=10)
        item=controls.create_window((0,0),window=left_frame,anchor='nw')
        left_frame.bind('<Configure>',lambda event:controls.configure(scrollregion=controls.bbox('all')))
        controls.bind('<Configure>',lambda event:controls.itemconfigure(item,width=event.width))
        def scroll_controls(event):
            widget=event.widget
            while widget is not None and widget is not controls:widget=getattr(widget,'master',None)
            if widget is not controls:return
            units=-1 if getattr(event,'num',None)==4 else 1 if getattr(event,'num',None)==5 else -int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1)
            controls.yview_scroll(units,'units');return 'break'
        for sequence in ['<MouseWheel>','<Button-4>','<Button-5>']:self.root.bind(sequence,scroll_controls,add='+')

        ttk.Label(left_frame,text='Lưu vực mô phỏng NAM',style='Header.TLabel').pack(anchor='w')
        self.basin_choice=ttk.Combobox(left_frame,state='readonly',width=43)
        self.basin_choice.pack(fill='x',pady=4)
        self.basin_choice.bind('<<ComboboxSelected>>',lambda event:self._select_basin_from_combo())
        ttk.Button(left_frame,text='Áp dụng bộ thông số cho các lưu vực…',command=self._parameter_transfer_dialog).pack(fill='x',pady=3)
        self.lbl_basin_model=ttk.Label(left_frame,text='Chưa chuyển lưu vực từ bản đồ.',wraplength=350)
        self.lbl_basin_model.pack(anchor='w',pady=3)
        # 1. Thông tin lưu vực
        lbl_sec1 = ttk.Label(
            left_frame, text="1. Thông số Lưu vực", style="Header.TLabel"
        )
        lbl_sec1.pack(anchor="w", pady=(0, 5))

        f_basin = ttk.Frame(left_frame)
        f_basin.pack(fill=tk.X, pady=2)

        ttk.Label(f_basin, text="Diện tích F (km²):").grid(
            row=0, column=0, sticky="w", padx=3, pady=3
        )
        self.ent_area = ttk.Entry(f_basin, width=16)
        self.ent_area.insert(0, "150.0")
        self.ent_area.grid(row=0, column=1, sticky="w", padx=3, pady=3)

        ttk.Label(f_basin, text="Bước tính Δt (giờ):").grid(
            row=1, column=0, sticky="w", padx=3, pady=3
        )
        self.ent_dt = ttk.Entry(f_basin, width=10)
        self.ent_dt.insert(0, "1.0")
        self.ent_dt.grid(row=1, column=1, sticky="w", padx=3, pady=3)

        ttk.Checkbutton(left_frame,text='Tự nhận bước thời gian từ số liệu',variable=self.auto_dt,command=self._refresh_inputs).pack(anchor='w')
        ttk.Label(left_frame,text='Loại lưu lượng dùng đánh giá:').pack(anchor='w')
        self.discharge_choice=ttk.Combobox(left_frame,state='readonly',values=['Trung bình bước (m³/s)','Cuối bước – tức thời (m³/s)'],width=35)
        self.discharge_choice.current(0);self.discharge_choice.pack(anchor='w',pady=3)
        self.discharge_choice.bind('<<ComboboxSelected>>',lambda event:self._refresh_inputs())
        ttk.Label(left_frame,text='Chọn cùng loại với Q thực đo. Khi đối chiếu MIKE, kiểm tra loại đầu ra trước khi chọn.',wraplength=350).pack(anchor='w')
        self.setting_entries=[self.ent_area,self.ent_dt]
        for row,(attr,label,default) in enumerate([
            ('ent_warm','Khởi động (giờ):','0'),('ent_split','Hiệu chỉnh (% chuỗi sau khởi động):','70'),
            ('ent_u','Độ đầy bể mặt đầu (0–1):','0.2'),('ent_l','Độ đầy bể rễ đầu (0–1):','0.5'),
            ('ent_base','Dòng ngầm ban đầu (m³/s):','0'),('ent_surf','Dòng tràn ban đầu (m³/s):','0'),('ent_inter','Dòng sát mặt ban đầu (m³/s):','0')],2):
            if self.validation_mode and attr=='ent_split':label='Kiểm định (% sau khởi động):'
            ttk.Label(f_basin,text=label).grid(row=row,column=0,sticky='w',padx=3,pady=2)
            entry=ttk.Entry(f_basin,width=10);entry.insert(0,default);entry.grid(row=row,column=1,padx=3)
            setattr(self,attr,entry);self.setting_entries.append(entry)
        for attr,label in [('ent_period_start','Bắt đầu mô phỏng:'),('ent_period_end','Kết thúc mô phỏng:')]:
            row=ttk.Frame(left_frame);row.pack(fill='x',pady=2)
            ttk.Label(row,text=label).pack(side='left')
            entry=ttk.Entry(row,width=24);entry.pack(side='right');setattr(self,attr,entry);self.setting_entries.append(entry)
            entry.bind('<KeyRelease>',lambda event:self.auto_period.set(False))
        ttk.Checkbutton(left_frame,text='Gợi ý khoảng mô phỏng từ dữ liệu',variable=self.auto_period,command=self._request_period_suggestion).pack(anchor='w')
        ttk.Label(left_frame,text='Có ngày giờ: dd/mm/yyyy hh:mm:ss.\nChuỗi một cột: nhập số bước đầu/cuối.\nThời gian gợi ý để tham khảo; có thể sửa trực tiếp.\nÔ mưa trống trong khoảng đã chọn được tính là 0 mm.',wraplength=350).pack(anchor='w')
        ttk.Label(left_frame,text='NAM 9 thông số: CK dòng tràn biến đổi; không tuyết/tưới.\nNhập 3 chuỗi riêng bằng CSV, Excel hoặc MIKE DFS0.\nMột cột giá trị: mỗi dòng = một bước Δt.\nHoặc ThoiGian + giá trị (giờ cuối bước).\nMưa: tổng mm/bước; Q: m³/s, tùy chọn.\nBốc hơi: tổng tháng/ngày/bước hoặc mm/ngày của tháng; tự phân bổ đều.',wraplength=350).pack(anchor='w',pady=4)
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # 2. Nạp dữ liệu
        lbl_sec2 = ttk.Label(
            left_frame, text="2. Mưa, bốc hơi và lưu lượng", style="Header.TLabel"
        )
        lbl_sec2.pack(anchor="w", pady=(0, 5))

        self.series_labels={}
        for key,name in SERIES_NAMES.items():
            row=ttk.Frame(left_frame);row.pack(fill=tk.X,pady=2)
            ttk.Button(row,text='Thêm trạm mưa' if key=='Mua_mm' else 'Nhập '+name,command=lambda k=key:self._import_series(k)).pack(side='left',fill='x',expand=True)
            ttk.Button(row,text='Trạm & trọng số' if key=='Mua_mm' else 'Xem bảng',command=self._manage_rain if key=='Mua_mm' else lambda k=key:self._view_series(k)).pack(side='right',padx=2)
            label=ttk.Label(left_frame,text='Chưa nhập',wraplength=350,foreground='gray');label.pack(anchor='w')
            self.series_labels[key]=label
        row=ttk.Frame(left_frame);row.pack(fill='x',pady=4)
        ttk.Button(row,text='Bỏ Q thực đo',command=self._clear_observed).pack(side='left')
        ttk.Button(row,text='Dữ liệu giả lập',command=self._load_synthetic_data).pack(side='right')
        self.lbl_data_status=ttk.Label(left_frame,text='Nhập mưa và bốc hơi để mô phỏng.',wraplength=350)
        self.lbl_data_status.pack(anchor='w',pady=4)

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        calib_frame=ttk.Frame(left_frame)
        if not self.validation_mode:calib_frame.pack(fill='x')
        # 3. Tự động dò thông số (Auto-Calibrate)
        lbl_sec3 = ttk.Label(
            calib_frame,
            text="3. Hiệu chỉnh thông số",
            style="Header.TLabel",
        )
        lbl_sec3.pack(anchor="w", pady=(0, 5))

        f_iter = ttk.Frame(calib_frame)
        f_iter.pack(fill=tk.X, pady=2)
        ttk.Label(f_iter, text="Số thế hệ tối ưu:").pack(side=tk.LEFT)
        self.ent_maxiter = ttk.Entry(f_iter, width=6)
        self.ent_maxiter.insert(0, "20")
        self.ent_maxiter.pack(side=tk.LEFT, padx=6)
        runs_row=ttk.Frame(calib_frame);runs_row.pack(fill=tk.X,pady=2)
        ttk.Label(runs_row,text='Số lần chạy hiệu chỉnh:').pack(side=tk.LEFT)
        self.ent_runs=ttk.Entry(runs_row,width=6);self.ent_runs.insert(0,'3');self.ent_runs.pack(side=tk.LEFT,padx=6)
        ttk.Label(calib_frame,text='Tìm kiếm toàn cục, sau đó tinh chỉnh cục bộ; giữ NSE tốt nhất.\nThông số được chuẩn hóa; mỗi lần chạy khảo sát thêm vùng mới. Kiểm định độc lập để đánh giá khả năng áp dụng.',wraplength=350).pack(anchor='w')


        self.btn_calibrate = ttk.Button(
            calib_frame,
            text="Bắt đầu hiệu chỉnh thông số",
            style="Accent.TButton",
            command=self._start_calibration_thread,
        )
        self.btn_calibrate.pack(fill=tk.X, pady=6)
        self.btn_stop=ttk.Button(calib_frame,text="Dừng hiệu chỉnh",command=self._stop_calibration,state=tk.DISABLED)
        self.btn_stop.pack(fill=tk.X,pady=2)

        self.progress_bar = ttk.Progressbar(calib_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=2)

        self.lbl_calib_status = ttk.Label(
            calib_frame, text="Sẵn sàng", foreground="#007ACC", wraplength=350
        )
        self.lbl_calib_status.pack(anchor="w", pady=2)

        ttk.Separator(calib_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # 4. Hiển thị thông số mô hình
        lbl_sec4 = ttk.Label(
            left_frame, text="4. Tham số NAM hiện tại", style="Header.TLabel"
        )
        lbl_sec4.pack(anchor="w", pady=(0, 5))

        self.param_labels = {}
        f_params = ttk.Frame(left_frame)
        f_params.pack(fill=tk.X)

        for i, key in enumerate(PARAM_KEYS):
            row = i // 2
            col = (i % 2) * 2
            ttk.Label(f_params, text=f"{key}:", font=("Segoe UI", 8)).grid(
                row=row, column=col, sticky="w", padx=2, pady=1
            )
            lbl_v = ttk.Label(
                f_params,
                text="--",
                font=("Segoe UI", 8, "bold"),
                foreground="#333",
            )
            lbl_v.grid(row=row, column=col + 1, sticky="w", padx=2, pady=1)
            self.param_labels[key] = lbl_v

        self.btn_edit=ttk.Button(left_frame,text='Chỉnh thông số mô hình',command=self._edit_parameters)
        self.btn_edit.pack(fill=tk.X,pady=2)
        ttk.Button(left_frame,text='Chạy kiểm định' if self.validation_mode else 'Chạy mô phỏng',command=self._run_manual).pack(fill=tk.X,pady=2)

        if not self.validation_mode:
            ttk.Button(left_frame,text='KIỂM ĐỊNH VỚI DỮ LIỆU MỚI',command=self._open_validation).pack(fill='x',pady=5)
        else:
            ttk.Label(left_frame,text='Nhập bộ số liệu mới để kiểm định.\nThông số được giữ nguyên, không dò lại.\nTrạng thái đầu và thời gian khởi động đặt riêng.\nNSE tính trên toàn bộ giai đoạn sau khởi động.',wraplength=350).pack(anchor='w',pady=5)

        # 5. Xuất kết quả
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )
        btn_export = ttk.Button(
            left_frame,
            text="💾 Xuất kết quả ra file CSV",
            command=self._export_csv,
        )
        btn_export.pack(fill=tk.X, pady=4)
        ttk.Button(left_frame,text='Trích lưu lượng các lưu vực (Excel)',command=self._export_basins_dialog).pack(fill=tk.X,pady=4)

        # --- KHUNG BÊN PHẢI: ĐỒ THỊ MATPLOTLIB ---
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)

        self.results_tabs=ttk.Notebook(right_frame);self.results_tabs.pack(fill='both',expand=True)
        plot_frame=ttk.Frame(self.results_tabs);map_frame=ttk.Frame(self.results_tabs);basins_frame=ttk.Frame(self.results_tabs)
        self.results_tabs.add(plot_frame,text='Mô phỏng và kết quả')
        self.results_tabs.add(map_frame,text='Bản đồ lưu vực')
        self._build_basin_map(map_frame)
        self.results_tabs.add(basins_frame,text='Danh sách lưu vực NAM')
        self._build_basins_tab(basins_frame)
        right_frame=plot_frame
        # Thanh hiển thị chỉ số thống kê (NSE, Qmax, PBIAS)
        metrics_bar = ttk.Frame(right_frame, padding=5)
        metrics_bar.pack(fill=tk.X)

        self.lbl_metric_nse = ttk.Label(
            metrics_bar,
            text="Hệ số NASH (NSE): --",
            font=("Segoe UI", 9, "bold"),
            foreground="#D9534F",
        )
        self.lbl_metric_nse.pack(anchor="w", padx=5)

        self.lbl_metric_peak = ttk.Label(
            metrics_bar,
            text="Đỉnh Qmax (Đo / Mô phỏng): --",
            font=("Segoe UI", 10),
        )
        self.lbl_metric_peak.pack(anchor="w", padx=5)

        self.lbl_metric_pbias = ttk.Label(
            metrics_bar, text="Sai số thể tích (PBIAS): --", font=("Segoe UI", 10)
        )
        self.lbl_metric_pbias.pack(anchor="w", padx=5)

        # Nhúng Matplotlib Canvas
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax_rain = self.fig.add_subplot(3, 1, 1)
        self.ax_flow = self.fig.add_subplot(3, 1, 2, sharex=self.ax_rain)
        self.ax_volume=self.fig.add_subplot(3,1,3,sharex=self.ax_rain)
        self.fig.subplots_adjust(hspace=0.15)

        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, right_frame)
        toolbar.update()
        toolbar.pack(fill=tk.X)

    # ==========================================================================
    # CÁC HÀM XỬ LÝ SỰ KIỆN VÀ DỮ LIỆU
    # ==========================================================================

    def _build_basins_tab(self,parent):
        bar=ttk.Frame(parent,padding=6);bar.pack(fill='x')
        for i,(label,command) in enumerate([('Chuyển tất cả từ bản đồ',self._transfer_shape_basins),('Chọn lưu vực mô phỏng / hiệu chỉnh',self._select_basin_from_table),('Kiểm định lưu vực được chọn',self._validate_selected_basin),('Áp dụng bộ thông số…',self._parameter_transfer_dialog),('Đổi tên lưu vực',self._rename_basin)]):
            ttk.Button(bar,text=label,command=command).grid(row=i//2,column=i%2,sticky='ew',padx=3,pady=3)
        bar.columnconfigure(0,weight=1);bar.columnconfigure(1,weight=1)
        self.basins_tree=ttk.Treeview(parent,columns=('name','area','rain','evap','q','source','validation'),show='headings',selectmode='browse')
        for key,label in [('name','Lưu vực'),('area','Diện tích (km²)'),('rain','Trọng số mưa'),('evap','Trọng số bốc hơi'),('q','Q thực đo'),('source','Nguồn thông số'),('validation','NSE kiểm định')]:
            self.basins_tree.heading(key,text=label);self.basins_tree.column(key,width=140,stretch=True)
        scrollbar=ttk.Scrollbar(parent,orient='vertical',command=self.basins_tree.yview);self.basins_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y')
        horizontal=ttk.Scrollbar(parent,orient='horizontal',command=self.basins_tree.xview)
        self.basins_tree.configure(xscrollcommand=horizontal.set);horizontal.pack(side='bottom',fill='x')
        self.basins_detail=ttk.Label(parent,wraplength=850);self.basins_detail.pack(side='bottom',fill='x',padx=8,pady=4)
        self.basins_tree.pack(fill='both',expand=True,padx=6,pady=6)
        self.basins_tree.bind('<<TreeviewSelect>>',lambda event:self._show_basin_detail())
        self.basins_tree.bind('<Double-1>',lambda event:self._select_basin_from_table())
        ttk.Label(parent,text='SHP giữ nguyên từng đối tượng, kể cả lưu vực lồng nhau. Chọn lưu vực trước khi nhập Q thực đo, hiệu chỉnh hoặc kiểm định. Thông số chuyển sang lưu vực khác cần được kiểm tra tại lưu vực nhận.',wraplength=900).pack(fill='x',padx=8,pady=6)

    def _rename_basin(self):
        if not self._project_idle():return
        selected=self.basins_tree.selection()
        basin_id=selected[0] if selected else self._active_basin_id
        feature=next((item for item in self._shape_basins if item['id']==basin_id),None)
        if feature is None:
            messagebox.showinfo('Đổi tên lưu vực','Chọn lưu vực trong danh sách trước khi đổi tên.',parent=self.root);return
        name=simpledialog.askstring('Đổi tên lưu vực','Tên lưu vực:',initialvalue=feature['name'],parent=self.root)
        if name is None:return
        name=name.strip()
        if not name:
            messagebox.showerror('Đổi tên lưu vực','Tên lưu vực không được để trống.',parent=self.root);return
        feature['name']=name
        if basin_id in self._basins:self._basins[basin_id]['name']=name
        if basin_id==self._active_basin_id:
            label='Q riêng: ' if 'Q_ThucDo_m3s' in self.input_series else 'Chưa nhập Q cho '
            self.series_labels['Q_ThucDo_m3s'].config(text=label+name)
        self._update_basins_table()
        self.basins_tree.selection_set(basin_id);self.basins_tree.see(basin_id)
        self._show_basin_detail();self._draw_basin_map()

    def _show_basin_detail(self):
        selected=self.basins_tree.selection()
        if not selected:self.basins_detail.config(text='');return
        record=self._basins.get(selected[0],{})
        show=lambda values:'; '.join(f'{name}: {weight:.6f}' for name,weight in values.items()) or 'Chưa đủ vị trí / số liệu trạm'
        self.basins_detail.config(text='Trọng số mưa: '+show(record.get('rain_weights',{}))+'\nTrọng số bốc hơi: '+show(record.get('evap_weights',{})))

    def _capture_active_basin(self):
        if self._active_basin_id not in self._basins:return
        record=self._basins[self._active_basin_id]
        record['settings']={name:getattr(self,name).get() for name in self._PROJECT_ENTRIES}
        record['auto_period']=self.auto_period.get();record['auto_dt']=self.auto_dt.get()
        record['discharge_mode']=self._discharge_mode();record['params']=self.best_params.copy()
        record['bounds']=[list(pair) for pair in self.param_bounds]
        record['observed']=self._pack_series(self.input_series['Q_ThucDo_m3s']) if 'Q_ThucDo_m3s' in self.input_series else None
        record['calibrated']=None if self._calibrated_params is None else dict(params=self._calibrated_params.copy(),area=self._calibrated_area,discharge_mode=self._calibrated_discharge_mode)
        record['parameter_source']=self._parameter_source;record['independent_metrics']=self._independent_metrics
        record['rain_weights']={} if self._thiessen_result is None else dict(self._thiessen_result['weights'])
        record['evap_weights']={} if self._evap_thiessen is None else dict(self._evap_thiessen['weights'])
        record['calibration_period']=getattr(self,'_calibration_period',None)

    def _basin_display(self,basin_id):
        return f'{basin_id} — {self._basins[basin_id]["name"]}'

    def _update_basins_table(self):
        self.basin_choice.config(values=[self._basin_display(bid) for bid in self._basins])
        if self._active_basin_id in self._basins:self.basin_choice.set(self._basin_display(self._active_basin_id))
        else:self.basin_choice.set('')
        self.basins_tree.delete(*self.basins_tree.get_children())
        for feature in self._shape_basins:
            bid=feature['id'];record=self._basins.get(bid,{})
            metrics=self._source_validation(record) or record.get('independent_metrics') or {};nse=metrics.get('nse')
            source=record.get('parameter_source')
            source_label=self._basins.get(source,{}).get('name',source) if source else 'Chưa hiệu chỉnh'
            if source is None and record.get('validation_source'):source_label='KĐ từ '+self._basins.get(record['validation_source'],{}).get('name',record['validation_source'])
            text=lambda weights:'; '.join(f'{name}: {weight:.3f}' for name,weight in weights.items())
            self.basins_tree.insert('','end',iid=bid,values=(f'{bid} — {feature["name"]}',f'{feature["area_km2"]:.3f}',text(record.get('rain_weights',{})),text(record.get('evap_weights',{})),
                'Đã nhập' if record.get('observed') else 'Chưa nhập',source_label,(f'{nse:.3f}'+(' tại '+str(self._basins.get(metrics.get('basin_id'),{}).get('name',metrics.get('basin_id'))) if metrics.get('basin_id') not in (None,bid) else '')) if nse is not None else 'Chưa kiểm định'))
        if self._active_basin_id in self._basins:
            record=self._basins[self._active_basin_id];source=record.get('parameter_source')
            self.lbl_basin_model.config(text=f'Đang làm: {self._basin_display(self._active_basin_id)}. '+('Thông số từ '+str(self._basins.get(source,{}).get('name',source))+'.' if source else 'Chưa hiệu chỉnh.'))
            self.basins_tree.selection_set(self._active_basin_id)
        else:self.lbl_basin_model.config(text='Chưa chuyển lưu vực từ bản đồ.')

    def _transfer_shape_basins(self):
        if not self._project_idle():return
        if not self._shape_basins:
            messagebox.showinfo('Lưu vực','Nhập SHP lưu vực trước.',parent=self.root);return
        self._capture_active_basin()
        for feature in self._shape_basins:
            if feature['id'] in self._basins:continue
            settings={name:getattr(self,name).get() for name in self._PROJECT_ENTRIES}
            settings['ent_area']=f'{feature["area_km2"]:.12g}'
            record=dict(feature,settings=settings,auto_period=True,auto_dt=self.auto_dt.get(),discharge_mode=self._discharge_mode(),params=self.best_params.copy(),
                bounds=[list(pair) for pair in self.param_bounds],observed=None,calibrated=None,parameter_source=None,independent_metrics=None,rain_weights={},evap_weights={},calibration_period=None)
            self._basins[feature['id']]=record
        selected=self._active_basin_id or next(iter(self._basins))
        self._activate_basin(selected)
        self.results_tabs.select(2)

    def _activate_basin(self,basin_id,capture=True):
        if not self._project_idle():
            if self._active_basin_id in self._basins:self.basin_choice.set(self._basin_display(self._active_basin_id))
            return False
        if basin_id not in self._basins:return False
        if capture:self._capture_active_basin()
        record=self._basins[basin_id];self._active_basin_id=basin_id
        self._basin_geojson=record['geometry'];self._thiessen_result=None;self._evap_thiessen=None;self._spatial_signature=None
        self.best_params=record['params'].copy();self.param_bounds=[tuple(pair) for pair in record['bounds']]
        calibrated=record.get('calibrated');self._calibrated_params=None if calibrated is None else calibrated['params'].copy()
        if calibrated is not None:
            self._calibrated_area=record['area_km2'];self._calibrated_discharge_mode=calibrated['discharge_mode']
        self._parameter_source=record.get('parameter_source');self._independent_metrics=record.get('independent_metrics');self._calibration_period=record.get('calibration_period')
        for name,value in record['settings'].items():
            entry=getattr(self,name);entry.config(state='normal');entry.delete(0,'end');entry.insert(0,value)
        self.ent_area.delete(0,'end');self.ent_area.insert(0,f'{record["area_km2"]:.12g}');self.ent_area.config(state='readonly')
        if self.validation_mode:self.ent_split.delete(0,'end');self.ent_split.insert(0,'100');self.ent_split.config(state='readonly')
        self.auto_period.set(record['auto_period']);self.auto_dt.set(record['auto_dt'])
        self.discharge_choice.current(1 if record['discharge_mode']=='endpoint' else 0)
        if record.get('observed') is None:self.input_series.pop('Q_ThucDo_m3s',None)
        else:self.input_series['Q_ThucDo_m3s']=self._unpack_series(record['observed'],'Q_ThucDo_m3s')
        self.series_labels['Q_ThucDo_m3s'].config(text='Q riêng: '+record['name'] if record.get('observed') else 'Chưa nhập Q cho '+record['name'],foreground='blue')
        self._suggested_period=self._period();self._update_parameter_display();self._refresh_inputs()
        self._capture_active_basin();self._update_basins_table();self._draw_basin_map()
        return True

    def _select_basin_from_combo(self):
        selected=self.basin_choice.get()
        bid=next((key for key in self._basins if self._basin_display(key)==selected),None)
        if bid is not None:self._activate_basin(bid)

    def _select_basin_from_table(self):
        selected=self.basins_tree.selection()
        if selected:
            if not self._basins:self._transfer_shape_basins()
            self._activate_basin(selected[0]);self.results_tabs.select(0)

    def _validate_selected_basin(self):
        selected=self.basins_tree.selection()
        if selected and self._activate_basin(selected[0]):self._validation_source_dialog()

    @staticmethod
    def _source_validation(record):
        calibrated=record.get('calibrated')
        if calibrated is None:return None
        own=record.get('independent_metrics')
        if own is not None and own.get('nse') is not None and np.isfinite(own['nse']) and (record.get('validation_params') is None or record['validation_params']==calibrated['params']):
            return dict(own,basin_id=record['id'])
        for bid,result in record.get('validation_results',{}).items():
            if result.get('nse') is not None and np.isfinite(result['nse']) and result.get('params')==calibrated['params']:
                return dict(result,basin_id=bid)
        return None

    def _validation_source_dialog(self):
        if not self._project_idle():return
        self._capture_active_basin()
        sources=[bid for bid,record in self._basins.items() if record.get('calibrated') is not None]
        if not sources:
            messagebox.showinfo('Kiểm định','Hiệu chỉnh ít nhất một lưu vực để có bộ thông số.',parent=self.root);return
        window=tk.Toplevel(self.root);window.title('Chọn bộ thông số dùng kiểm định');window.transient(self.root);window.grab_set()
        ttk.Label(window,text='Lưu vực kiểm định: '+self._basin_display(self._active_basin_id)).pack(padx=10,pady=6)
        ttk.Label(window,text='Chọn lưu vực cung cấp bộ thông số đã hiệu chỉnh:').pack(padx=10,pady=4)
        choice=ttk.Combobox(window,values=[self._basin_display(bid) for bid in sources],state='readonly',width=60);choice.current(0);choice.pack(padx=10,pady=6)
        def run():
            source_id=sources[choice.current()];window.destroy();self._open_basin_validation(source_id)
        ttk.Button(window,text='Mở kiểm định với bộ thông số cố định',command=run).pack(padx=10,pady=8)

    def _transfer_parameters(self,source_id,target_ids):
        self._capture_active_basin()
        source=self._basins[source_id]
        if source.get('calibrated') is None:raise ValueError('Lưu vực nguồn chưa có bộ thông số hiệu chỉnh.')
        if self._source_validation(source) is None:
            raise ValueError('Chạy kiểm định độc lập có NSE xác định cho lưu vực nguồn trước khi áp dụng bộ thông số.')
        if any(target_id not in self._basins for target_id in target_ids):raise ValueError('Lưu vực nhận không có trong danh sách.')
        params=source['calibrated']['params'];mode=source['calibrated']['discharge_mode']
        for target_id in target_ids:
            if target_id==source_id:continue
            target=self._basins[target_id]
            target['params']=params.copy();target['discharge_mode']=mode
            target['calibrated']=dict(params=params.copy(),area=target['area_km2'],discharge_mode=mode)
            tested=target.get('independent_metrics') if target.get('validation_source')==source_id and target.get('validation_params')==params else None
            target['parameter_source']=source_id;target['independent_metrics']=tested;target['calibration_metrics']=None;target['calibration_period']=None
            target['validation_results']={}
        if self._active_basin_id in target_ids and self._active_basin_id!=source_id:self._activate_basin(self._active_basin_id,capture=False)
        self._update_basins_table()

    def _parameter_transfer_dialog(self):
        if not self._project_idle():return
        self._capture_active_basin()
        sources=[bid for bid,record in self._basins.items() if record.get('calibrated') is not None]
        if not sources:
            messagebox.showinfo('Thông số','Chọn một lưu vực và hiệu chỉnh trước.',parent=self.root);return
        window=tk.Toplevel(self.root);window.title('Áp dụng bộ thông số NAM cho các lưu vực');window.geometry('900x430');window.transient(self.root);window.grab_set()
        ttk.Label(window,text='Lưu vực nguồn (đã hiệu chỉnh và kiểm định):').pack(anchor='w',padx=8,pady=4)
        choice=ttk.Combobox(window,values=[self._basin_display(bid) for bid in sources],state='readonly',width=65);choice.current(0);choice.pack(fill='x',padx=8)
        status=ttk.Label(window,wraplength=850);status.pack(fill='x',padx=8,pady=4)
        def show_source(event=None):
            record=self._basins[sources[choice.current()]];metric=self._source_validation(record) or {}
            status.config(text='NSE kiểm định tại '+str(self._basins.get(metric.get('basin_id'),{}).get('name','chưa chọn'))+': '+(str(round(metric['nse'],3)) if metric.get('nse') is not None else 'chưa có')+'. Chỉ chuyển thông số và loại Q đánh giá; giữ diện tích, đầu vào và thời gian riêng của từng lưu vực nhận.')
        choice.bind('<<ComboboxSelected>>',show_source);show_source()
        tree=ttk.Treeview(window,columns=('name','area'),show='headings',selectmode='extended');tree.heading('name',text='Lưu vực nhận');tree.heading('area',text='Diện tích (km²)')
        for bid,record in self._basins.items():tree.insert('','end',iid=bid,values=(self._basin_display(bid),f'{record["area_km2"]:.3f}'))
        tree.pack(fill='both',expand=True,padx=8,pady=4)
        row=ttk.Frame(window);row.pack(fill='x',padx=8,pady=8)
        ttk.Button(row,text='Chọn tất cả',command=lambda:tree.selection_set(tree.get_children())).pack(side='left')
        def apply():
            try:
                if not tree.selection():raise ValueError('Chọn các lưu vực nhận bộ thông số.')
                self._transfer_parameters(sources[choice.current()],tree.selection());window.destroy()
            except Exception as exc:messagebox.showerror('Áp dụng thông số',str(exc),parent=window)
        ttk.Button(row,text='Áp dụng cho các lưu vực đã chọn',command=apply).pack(side='right')

    def _import_evap_station(self,name):
        if not self._project_idle():return
        path=filedialog.askopenfilename(parent=self.root,title='Chọn bốc hơi trạm '+name,filetypes=[('CSV / Excel / MIKE DFS0','*.csv *.xlsx *.dfs0')])
        if not path:return
        try:
            prepared=prepare_series(read_series_file(path,'BocHoi_mm',self._choose_dfs_item),'BocHoi_mm')
            if 'ThoiGian' in prepared:
                mode=simpledialog.askinteger('Bốc hơi trạm '+name,'1. Tổng mm/bước (thời gian cuối bước).\n2. Tổng mm/tháng.\n3. Trung bình mm/ngày của tháng.\n4. Tổng mm/ngày theo lịch.',initialvalue=1,minvalue=1,maxvalue=4,parent=self.root)
                if mode is None:return
                prepared.attrs['pet_mode']={1:'step_total',2:'month_total',3:'month_daily_mean',4:'day_total'}[mode]
            if name in self._evap_stations and not messagebox.askyesno('Bốc hơi','Thay dữ liệu bốc hơi trạm '+name+'?',parent=self.root):return
            self._evap_stations[name]=dict(data=prepared,source=Path(path).name,weight=1. if not self._evap_stations else self._evap_stations.get(name,{}).get('weight',0.))
            self._spatial_signature=None;self._evap_thiessen=None
            if self._basin_geojson is not None and self.rain_stations:self._calculate_thiessen()
            else:self._refresh_inputs();self._draw_basin_map()
        except ImportCancelled:return
        except Exception as exc:messagebox.showerror('Trạm bốc hơi',str(exc),parent=self.root)

    def _manage_evap_stations(self):
        window=tk.Toplevel(self.root);window.title('Mạng trạm bốc hơi');window.geometry('750x350')
        tree=ttk.Treeview(window,columns=('name','weight','source'),show='headings')
        for key,label in [('name','Trạm'),('weight','Trọng số lưu vực đang chọn'),('source','Dữ liệu')]:tree.heading(key,text=label)
        tree.pack(fill='both',expand=True,padx=6,pady=6)
        def refresh():
            tree.delete(*tree.get_children())
            for name in dict.fromkeys([*self._evap_stations,*self._evap_positions]):
                item=self._evap_stations.get(name,{})
                tree.insert('','end',iid=name,values=(name,f'{item.get("weight",0):.6f}',item.get('source','Chưa chọn dữ liệu')))
        def replace():
            if tree.selection():self._import_evap_station(tree.selection()[0]);refresh()
        def remove():
            if tree.selection():
                name=tree.selection()[0];self._evap_stations.pop(name,None);self._evap_positions.pop(name,None)
                self._spatial_signature=None;self._evap_thiessen=None;self.input_series.pop('BocHoi_mm',None)
                self._refresh_inputs();self._draw_basin_map();refresh()
        row=ttk.Frame(window);row.pack(fill='x',padx=6,pady=6)
        for label,command in [('Thêm trạm / vị trí',lambda:self._station_coordinate_dialog('evap')),('Chọn lại dữ liệu',replace),('Xóa trạm',remove)]:ttk.Button(row,text=label,command=command).pack(side='left',padx=3)
        window.bind('<FocusIn>',lambda event:refresh() if event.widget==window else None);refresh()

    def _open_basin_validation(self,source_id=None):
        if not self._project_idle():return
        self._capture_active_basin();bid=self._active_basin_id;record=self._basins[bid]
        if source_id is None:
            if record.get('calibrated') is None:self._validation_source_dialog();return
            source_id=bid
        source=self._basins[source_id];fitted=source['calibrated']
        import copy
        window=tk.Toplevel(self.root);app=NAMDesktopApp(window,validation_params=fitted['params'])
        app._shape_basins=[copy.deepcopy(feature) for feature in self._shape_basins if feature['id']==bid]
        app._basins={bid:copy.deepcopy(record)};app._basin_source=self._basin_source
        app._basins[bid]['params']=fitted['params'].copy()
        app._basins[bid]['calibrated']=dict(params=fitted['params'].copy(),area=record['area_km2'],discharge_mode=fitted['discharge_mode'])
        app._basins[bid]['parameter_source']=source_id
        app._basins[bid]['discharge_mode']=fitted['discharge_mode']
        app._basins[bid]['calibration_period']=record.get('calibration_period') if source_id==bid else None
        app.show_thiessen.set(self.show_thiessen.get())
        app._map_crs_wkt=self._map_crs_wkt;app._basin_input_crs=self._basin_input_crs
        app._station_positions=copy.deepcopy(self._station_positions);app._evap_positions=copy.deepcopy(self._evap_positions)
        app.rain_stations={name:dict(item,data=item['data'].copy()) for name,item in self.rain_stations.items()}
        app._evap_stations={name:dict(item,data=item['data'].copy()) for name,item in self._evap_stations.items()}
        app.input_series={key:frame.copy() for key,frame in self.input_series.items() if key!='Mua_mm'}
        app._activate_basin(bid,capture=False);app.basin_choice.config(state='disabled');app.discharge_choice.config(state='disabled')
        app._validation_forbidden_period=record.get('calibration_period') if source_id==bid else None
        def store(metrics,params,period):
            current=self._basins.get(bid)
            donor=self._basins.get(source_id)
            if current is None or donor is None or donor.get('calibrated') is None:return
            if any(donor['calibrated']['params'][key]!=params[key] for key in PARAM_KEYS):return
            result={key:float(value) if np.isfinite(value) else None for key,value in metrics.items()}
            result['requested_period']=list(period);current['independent_metrics']=result
            current['validation_source']=source_id;current['validation_params']=params.copy()
            donor.setdefault('validation_results',{})[bid]=dict(result,params=params.copy())
            if self._active_basin_id==bid:self._independent_metrics=result
            self._update_basins_table()
        app._validation_callback=store
        app.lbl_calib_status.config(text='Kiểm định '+record['name']+' với thông số từ '+source['name']+'. Chọn thời đoạn / số liệu kiểm định; thông số giữ cố định.')
        app._project_defaults=app._project_payload();app._saved_project=app._project_text();window._nam_app=app

    def _common_map_crs(self):
        if self._map_crs_wkt is None and self._basin_geojson is not None:
            if self._basin_input_crs:
                source=resolve_horizontal_crs(self._basin_input_crs)
                if source.is_projected and all(np.isclose(axis.unit_conversion_factor,1.) for axis in source.axis_info[:2]):
                    self._map_crs_wkt=source.to_2d().to_wkt();return self._map_crs_wkt
            _,shape,mapping,_,_,union,_,_=_geo_modules()
            extent=mapping(union([shape(feature['geometry']) for feature in self._shape_basins])) if self._shape_basins else self._basin_geojson
            self._map_crs_wkt=basin_metric_geometry(extent)[1].to_wkt()
        return self._map_crs_wkt

    def _build_basin_map(self,parent):
        toolbar=ttk.Frame(parent,padding=(8,6));toolbar.pack(fill='x')
        menu_buttons=[]
        def menu_button(label,items):
            button=ttk.Menubutton(toolbar,text=label+' ▾')
            menu=tk.Menu(button,tearoff=False,font=('Segoe UI',10))
            for title,command in items:
                if title is None:menu.add_separator()
                else:menu.add_command(label=title,command=command)
            button.configure(menu=menu);button.grid(row=0,column=len(menu_buttons),sticky='w',padx=(0,8));menu_buttons.append(button)
            return menu
        self.map_basin_menu=menu_button('Lưu vực',[
            ('Nhập bản đồ lưu vực (.shp)…',self._import_basin),
            ('Chuyển tất cả lưu vực sang NAM',self._transfer_shape_basins)])
        self.map_rain_menu=menu_button('Trạm mưa',[
            ('Thêm / sửa vị trí trạm…',self._station_coordinate_dialog),
            ('Quản lý trạm và dữ liệu mưa…',self._manage_rain)])
        self.map_evap_menu=menu_button('Trạm bốc hơi',[
            ('Thêm / sửa vị trí trạm…',lambda:self._station_coordinate_dialog('evap')),
            ('Quản lý trạm và dữ liệu bốc hơi…',self._manage_evap_stations)])
        calculate=ttk.Button(toolbar,text='Tính trọng số Thiessen',command=self._calculate_thiessen,style='Accent.TButton')
        display=ttk.Checkbutton(toolbar,text='Hiện đa giác',variable=self.show_thiessen,command=self._draw_basin_map)
        def arrange_toolbar(event=None):
            narrow=toolbar.winfo_width()<730
            calculate.grid(row=1 if narrow else 0,column=0 if narrow else 3,columnspan=2 if narrow else 1,sticky='w',padx=(0,10),pady=(5,0) if narrow else 0)
            display.grid(row=1 if narrow else 0,column=2 if narrow else 4,sticky='w',pady=(5,0) if narrow else 0)
        toolbar.bind('<Configure>',arrange_toolbar)
        arrange_toolbar()
        row=ttk.Frame(parent,padding=(8,2));row.pack(fill='x')
        ttk.Label(row,text='Trạm mưa đang chọn:').pack(side='left')
        self.map_station_choice=ttk.Combobox(row,state='readonly',width=25);self.map_station_choice.pack(side='left',padx=(8,10))
        action=ttk.Menubutton(row,text='Thao tác với trạm ▾');action.pack(side='left')
        self.map_station_menu=tk.Menu(action,tearoff=False,font=('Segoe UI',10))
        self.map_station_menu.add_command(label='Đặt vị trí bằng chuột',command=self._enable_map_pick)
        self.map_station_menu.add_command(label='Chọn / thay dữ liệu mưa…',command=self._choose_map_rain_data)
        self.map_station_menu.add_separator()
        self.map_station_menu.add_command(label='Xóa vị trí trên bản đồ',command=self._remove_station_position)
        action.configure(menu=self.map_station_menu)
        self.lbl_map_status=ttk.Label(parent,text='Nhập SHP cùng các tệp .shx, .dbf, .prj. Trạm mưa có thể nằm ngoài lưu vực.',wraplength=850)
        self.lbl_map_status.pack(fill='x',padx=8,pady=4)
        self.map_fig=Figure(figsize=(8,5),dpi=100);self.map_ax=self.map_fig.add_subplot(111)
        self.map_canvas=FigureCanvasTkAgg(self.map_fig,master=parent);self.map_canvas.get_tk_widget().pack(fill='both',expand=True)
        self.map_canvas.mpl_connect('button_press_event',self._map_clicked)
        NavigationToolbar2Tk(self.map_canvas,parent).pack(fill='x')
        self.map_tree=ttk.Treeview(parent,columns=('name','lon','lat','area','weight','data'),show='headings',height=5)
        for key,label in [('name','Trạm mưa'),('lon','Kinh độ'),('lat','Vĩ độ'),('area','Vùng Thiessen (km²)'),('weight','Trọng số'),('data','Dữ liệu mưa')]:
            self.map_tree.heading(key,text=label);self.map_tree.column(key,width=145,stretch=True)
        self.map_tree.pack(fill='x',padx=5,pady=5)
        self._draw_basin_map()

    def _choose_map_rain_data(self):
        name=self.map_station_choice.get()
        if not name:
            messagebox.showinfo('Dữ liệu trạm mưa','Chọn trạm mưa hoặc thêm vị trí trạm trước khi chọn dữ liệu.',parent=self.root);return
        self._import_rain_station(name)

    def _sync_map_stations(self):
        names=list(dict.fromkeys([*self.rain_stations,*self._station_positions]))
        self.map_station_choice.config(values=names)
        if self.map_station_choice.get() not in names:self.map_station_choice.set(names[0] if names else '')

    def _import_basin(self):
        if not self._project_idle():return
        if self.validation_mode:
            messagebox.showinfo('Kiểm định','Nhập danh sách lưu vực tại cửa sổ chính.',parent=self.root);return
        path=filedialog.askopenfilename(parent=self.root,title='Nhập các lưu vực — giữ nguyên từng đối tượng',filetypes=[('Shapefile','*.shp')])
        if not path:return
        try:
            gpd,_,mapping,_,_,union,_,_=_geo_modules();frame=gpd.read_file(path)
            if frame.crs is None:
                code=simpledialog.askstring('Hệ tọa độ SHP','SHP thiếu .prj. Nhập hệ tọa độ đúng (EPSG hoặc CRS):',parent=self.root)
                if not code:return
                frame=frame.set_crs(resolve_horizontal_crs(code))
            if frame.empty or frame.geometry.isna().any() or frame.geometry.is_empty.any():raise ValueError('SHP rỗng hoặc có hình học trống.')
            if not frame.geom_type.isin(['Polygon','MultiPolygon']).all() or not frame.geometry.is_valid.all():raise ValueError('Mỗi đối tượng phải là Polygon/MultiPolygon hợp lệ.')
            if self._basins and not messagebox.askyesno('Thay bản đồ','Thay danh sách lưu vực đang làm? Hãy lưu dự án hiện tại nếu cần giữ.',parent=self.root):return
            fields=[column for column in frame.columns if column!=frame.geometry.name]
            preferred=next((c for c in fields if str(c).casefold() in ('name','ten','ten_lv','ten_luuvuc','basin_name','id')),None)
            converted=frame_to_wgs84(frame);features=[]
            for i,(_,row) in enumerate(converted.iterrows(),1):
                geometry=mapping(row.geometry);metric,_,_=basin_metric_geometry(geometry)
                value=row[preferred] if preferred else None
                name=str(value) if value is not None and pd.notna(value) else f'Lưu vực {i}'
                properties={str(c):str(row[c]) if pd.notna(row[c]) else None for c in fields}
                features.append(dict(id=f'LV_{i}',name=name,geometry=geometry,area_km2=metric.area/1e6,properties=properties))
            self._shape_basins=features;self._basins={};self._active_basin_id=None
            self._parameter_source=None;self._independent_metrics=None;self._calibration_period=None;self._calibrated_params=None
            self._basin_geojson=mapping(union(converted.geometry.tolist())) # Chỉ làm khung hiển thị, không gộp các lưu vực NAM.
            self._basin_input_crs=frame.crs.to_wkt();self._map_crs_wkt=None
            self._common_map_crs()
            self._basin_source=Path(path).name;self._thiessen_result=None;self._evap_thiessen=None;self._spatial_signature=None
            self.ent_area.config(state='normal')
            self._refresh_inputs();self._update_basins_table();self._draw_basin_map()
            self.lbl_map_status.config(text=f'Đã giữ nguyên {len(features)} đối tượng lưu vực. Bấm Chuyển tất cả lưu vực sang NAM để tạo mô hình riêng.')
        except Exception as exc:messagebox.showerror('Nhập lưu vực',str(exc),parent=self.root)

    @staticmethod
    def _station_lonlat(first,second,crs_code,confirm_swap=None,order='north_east',third=None):
        crs=resolve_horizontal_crs(crs_code)
        def number(value):return finite_number(str(value).strip().replace(',','.'),'Tọa độ')
        first=number(first);second=number(second)
        if order not in ('north_east','east_north'):raise ValueError('Thứ tự tọa độ không hợp lệ.')
        if crs.is_geocentric:
            if third is None or not str(third).strip():raise ValueError('Hệ địa tâm cần đủ X, Y và Z.')
            lon,lat,*_=horizontal_transformer(crs,4326).transform(first,second,number(third),errcheck=True)
        else:
            north,east=(first,second) if order=='north_east' else (second,first)
            if crs.is_geographic:
                factor=crs.axis_info[0].unit_conversion_factor
                lat_limit=np.pi/2/factor;lon_limit=np.pi/factor
                if abs(north)>lat_limit and abs(east)<=lat_limit:
                    if confirm_swap is None or not confirm_swap():raise ValueError('Hai giá trị có vẻ nhập ngược. Chọn đúng thứ tự vĩ độ/kinh độ.')
                    north,east=east,north
                if not (-lat_limit<=north<=lat_limit and -lon_limit<=east<=lon_limit):raise ValueError('Tọa độ vượt phạm vi vĩ độ/kinh độ của hệ nguồn; kiểm tra thứ tự và đơn vị.')
            lon,lat,*_=horizontal_transformer(crs,4326).transform(east,north,errcheck=True)
        if not (np.isfinite(lon) and np.isfinite(lat) and -180<=lon<=180 and -90<lat<90):
            raise ValueError('Tọa độ sau chuyển đổi không hợp lệ; kiểm tra hệ nguồn, đơn vị và thứ tự trục.')
        return [lon,lat]

    def _station_coordinate_dialog(self,kind='rain'):
        positions=self._station_positions if kind=='rain' else self._evap_positions
        network=self.rain_stations if kind=='rain' else self._evap_stations
        station_label='mưa' if kind=='rain' else 'bốc hơi'
        if not self._project_idle():return
        self._sync_map_stations()
        window=tk.Toplevel(self.root);window.title('Thêm trạm '+station_label+' — vị trí và dữ liệu');window.transient(self.root)
        fields={};labels={}
        names=list(dict.fromkeys([*network,*positions]))
        for r,(key,label,default) in enumerate([('name','Tên trạm (nhập mới hoặc chọn)',self.map_station_choice.get() if kind=='rain' else ''),('crs','Hệ tọa độ EPSG','EPSG:4326'),('x','Vĩ độ (độ)',''),('y','Kinh độ (độ)','')]):
            labels[key]=ttk.Label(window,text=label);labels[key].grid(row=r,column=0,padx=8,pady=5,sticky='w')
            entry=ttk.Combobox(window,values=names,state='normal',width=28) if key=='name' else ttk.Entry(window,width=30)
            entry.set(default) if key=='name' else entry.insert(0,default)
            entry.grid(row=r,column=1,padx=8,pady=5);fields[key]=entry
        presets={'WGS84 — vĩ độ/kinh độ':'EPSG:4326','WGS84 / UTM 48N':'EPSG:32648',
                 'WGS84 / UTM 49N':'EPSG:32649','VN-2000 / UTM 48N':'EPSG:3405',
                 'VN-2000 / UTM 49N':'EPSG:3406','Web Mercator':'EPSG:3857'}
        if self._basin_input_crs:presets['Giống SHP lưu vực']=self._basin_input_crs
        preset=ttk.Combobox(window,values=list(presets),state='readonly',width=27)
        preset.grid(row=1,column=2,padx=6,pady=5);preset.set('WGS84 — vĩ độ/kinh độ')
        ttk.Label(window,text='Thứ tự hai tọa độ:').grid(row=4,column=0,padx=8,pady=4,sticky='w')
        coordinate_order=ttk.Combobox(window,values=['Vĩ độ / X Bắc → Kinh độ / Y Đông','Kinh độ / Easting → Vĩ độ / Northing'],state='readonly',width=39)
        coordinate_order.current(0);coordinate_order.grid(row=4,column=1,columnspan=2,padx=8,pady=4)
        ttk.Label(window,text='Z (chỉ bắt buộc cho hệ địa tâm):').grid(row=5,column=0,padx=8,pady=4,sticky='w')
        fields['z']=ttk.Entry(window,width=30);fields['z'].grid(row=5,column=1,padx=8,pady=4)
        note=ttk.Label(window,wraplength=620);note.grid(row=6,column=0,columnspan=3,padx=8,pady=5)
        def update_labels(event=None):
            try:crs=resolve_horizontal_crs(fields['crs'].get())
            except Exception:return
            order=coordinate_order.current()
            if crs.is_geocentric:
                labels['x'].config(text='X địa tâm');labels['y'].config(text='Y địa tâm')
                note.config(text='Nhập đủ X, Y, Z theo đơn vị của hệ địa tâm nguồn. Phần mềm tự chuyển về WGS84 và hệ bản đồ chung.')
            else:
                unit=crs.axis_info[0].unit_name
                unit={'degree':'độ','metre':'m','meter':'m'}.get(unit,unit)
                north='Vĩ độ' if crs.is_geographic else 'Northing / X Bắc'
                east='Kinh độ' if crs.is_geographic else 'Easting / Y Đông'
                labels['x'].config(text=f'{north if order==0 else east} ({unit})')
                labels['y'].config(text=f'{east if order==0 else north} ({unit})')
                note.config(text='Tự chuyển hệ nguồn về WGS84, rồi về cùng hệ phẳng hiển thị với lưu vực. EPSG/ESRI, WKT, PROJ đều được hỗ trợ. VN-2000 phải đúng múi/kinh tuyến trục; không chọn múi khác để thử dịch điểm.')
        def select_preset(event=None):
            value=presets.get(preset.get())
            if value:
                fields['crs'].delete(0,'end');fields['crs'].insert(0,value)
                coordinate_order.current(1 if preset.get()=='Giống SHP lưu vực' or resolve_horizontal_crs(value).is_projected else 0)
                update_labels()
        preset.bind('<<ComboboxSelected>>',select_preset)
        coordinate_order.bind('<<ComboboxSelected>>',update_labels)
        def fill_existing(event=None):
            point=positions.get(fields['name'].get().strip())
            if point is not None:
                coordinate_order.current(0);preset.set('WGS84 — vĩ độ/kinh độ')
                for key,value in [('crs','EPSG:4326'),('x',f'{point[1]:.10f}'),('y',f'{point[0]:.10f}')]:
                    fields[key].delete(0,'end');fields[key].insert(0,value)
                update_labels()
        fields['crs'].bind('<KeyRelease>',update_labels);fields['name'].bind('<<ComboboxSelected>>',fill_existing)
        update_labels();fill_existing()
        def save():
            if not self._project_idle():return
            try:
                name=fields['name'].get().strip()
                if not name:raise ValueError('Tên trạm không được để trống.')
                point=self._station_lonlat(fields['x'].get(),fields['y'].get(),fields['crs'].get(),
                    lambda:messagebox.askyesno('Thứ tự tọa độ','Hai giá trị có vẻ bị nhập ngược so với thứ tự đã chọn. Đổi lại?',parent=window),
                    order='east_north' if coordinate_order.current()==1 else 'north_east',third=fields['z'].get())
                positions[name]=point;self._thiessen_result=None;self._evap_thiessen=None;self._spatial_signature=None
                self._draw_basin_map();self.map_station_choice.set(name);window.destroy()
                self._import_rain_station(name) if kind=='rain' else self._import_evap_station(name)
            except Exception as exc:messagebox.showerror('Tọa độ trạm',str(exc),parent=window)
        ttk.Button(window,text='Lưu vị trí và chọn dữ liệu '+station_label,command=save).grid(row=7,column=0,columnspan=2,pady=8)
        def read_prj():
            path=filedialog.askopenfilename(parent=window,title='Đọc định nghĩa hệ tọa độ nguồn',filetypes=[('Hệ tọa độ','*.prj *.wkt'),('Tất cả tệp','*.*')])
            if not path:return
            try:
                crs=resolve_horizontal_crs(path);fields['crs'].delete(0,'end');fields['crs'].insert(0,crs.to_wkt());preset.set('Đọc từ .prj / WKT');update_labels()
            except Exception as exc:messagebox.showerror('Hệ tọa độ',str(exc),parent=window)
        ttk.Button(window,text='Đọc hệ tọa độ từ .prj',command=read_prj).grid(row=7,column=2,padx=6,pady=8)
        def custom_vn2000():
            dialog=tk.Toplevel(window);dialog.title('VN-2000 theo kinh tuyến trục');dialog.transient(window)
            inputs={}
            for r,(key,label,default) in enumerate([('meridian','Kinh tuyến trục (độ)','105'),('scale','Hệ số tỷ lệ k₀','0.9999'),('false_east','Easting gốc (m)','500000'),('false_north','Northing gốc (m)','0'),('latitude_origin','Vĩ độ gốc (độ)','0')]):
                ttk.Label(dialog,text=label).grid(row=r,column=0,padx=8,pady=4,sticky='w')
                entry=ttk.Entry(dialog);entry.insert(0,default);entry.grid(row=r,column=1,padx=8,pady=4);inputs[key]=entry
            ttk.Label(dialog,text='Dùng đúng thông số ghi trong hồ sơ: TM3 thường k₀=0.9999; UTM/TM6 thường k₀=0.9996. Datum giữ VN-2000.',wraplength=420).grid(row=5,column=0,columnspan=2,padx=8,pady=5)
            def choose():
                try:
                    crs=vn2000_projected_crs(**{key:entry.get().replace(',','.') for key,entry in inputs.items()})
                    fields['crs'].delete(0,'end');fields['crs'].insert(0,crs.to_wkt());preset.set(crs.name);update_labels();dialog.destroy()
                except Exception as exc:messagebox.showerror('VN-2000',str(exc),parent=dialog)
            ttk.Button(dialog,text='Dùng hệ tọa độ này',command=choose).grid(row=6,column=0,columnspan=2,pady=8)
        ttk.Button(window,text='VN-2000 theo kinh tuyến trục…',command=custom_vn2000).grid(row=8,column=0,columnspan=3,padx=6,pady=5)


    def _enable_map_pick(self):
        self._sync_map_stations()
        if self._basin_geojson is None:
            messagebox.showinfo('Bản đồ','Nhập lưu vực trước khi đặt trạm bằng chuột.',parent=self.root);return
        if not self.map_station_choice.get():
            name=simpledialog.askstring('Trạm mưa','Tên trạm muốn đặt trên bản đồ:',parent=self.root)
            if not name or not name.strip():return
            self.map_station_choice.set(name.strip())
        self._map_pick=True
        self.lbl_map_status.config(text='Bấm trên bản đồ để đặt trạm '+self.map_station_choice.get()+'. Có thể đặt bên ngoài lưu vực.')

    def _map_clicked(self,event):
        if not self._map_pick or event.inaxes!=self.map_ax or event.xdata is None:return
        if self.map_canvas.toolbar.mode:return
        if not self._project_idle():return
        try:
            _,_,_,_,_,_,_,Transformer=_geo_modules()
            _,crs,_=basin_metric_geometry(self._basin_geojson,self._common_map_crs())
            lon,lat=Transformer.from_crs(crs,4326,always_xy=True).transform(event.xdata,event.ydata,errcheck=True)
            name=self.map_station_choice.get()
            self._station_positions[name]=[lon,lat]
            self._map_pick=False;self._thiessen_result=None;self._spatial_signature=None;self._draw_basin_map()
            if name not in self.rain_stations:self._import_rain_station(name)
        except Exception as exc:messagebox.showerror('Đặt trạm',str(exc),parent=self.root)

    def _remove_station_position(self):
        self._station_positions.pop(self.map_station_choice.get(),None)
        self._thiessen_result=None;self._spatial_signature=None;self._draw_basin_map()

    def _assign_spatial_weights(self):
        if self._basin_geojson is None:return
        signature=(self._active_basin_id,id(self._basin_geojson),
            tuple((name,tuple(self._station_positions.get(name,()))) for name in self.rain_stations),
            tuple((name,tuple(self._evap_positions.get(name,()))) for name in self._evap_stations))
        if signature==self._spatial_signature:return
        for network,positions,label,attr in [(self.rain_stations,self._station_positions,'mưa','_thiessen_result'),(self._evap_stations,self._evap_positions,'bốc hơi','_evap_thiessen')]:
            if not network:continue
            missing=[name for name in network if name not in positions]
            pending=[name for name in positions if name not in network]
            if missing:raise ValueError('Chưa có tọa độ trạm '+label+': '+', '.join(missing))
            if pending:raise ValueError('Chưa chọn dữ liệu cho trạm '+label+': '+', '.join(pending))
            result=thiessen_basin_weights(self._basin_geojson,{name:positions[name] for name in network})
            for name,item in network.items():item['weight']=float(result['weights'][name])
            setattr(self,attr,result)
        self._spatial_signature=signature
        token=repr((tuple((name,tuple(self._station_positions.get(name,()))) for name in self.rain_stations),
                    tuple((name,tuple(self._evap_positions.get(name,()))) for name in self._evap_stations)))
        for bid,record in self._basins.items():
            if record.get('spatial_token')==token:continue
            for network,positions,key in [(self.rain_stations,self._station_positions,'rain_weights'),(self._evap_stations,self._evap_positions,'evap_weights')]:
                record[key]={} if not network else dict(thiessen_basin_weights(record['geometry'],{name:positions[name] for name in network})['weights'])
            record['spatial_token']=token

    def _calculate_thiessen(self):
        if not self._project_idle():return
        try:
            if self._basin_geojson is None:raise ValueError('Chưa nhập lưu vực.')
            if self._shape_basins and self._active_basin_id is None:raise ValueError('Bấm Chuyển tất cả lưu vực sang NAM và chọn lưu vực trước.')
            if not self.rain_stations:raise ValueError('Chưa nhập trạm mưa.')
            self._spatial_signature=None;self._assign_spatial_weights()
            self.series_labels['Mua_mm'].config(text=f'{len(self.rain_stations)} trạm; trọng số Thiessen riêng cho lưu vực đang chọn.',foreground='blue')
            self._refresh_inputs();self._draw_basin_map();self._capture_active_basin();self._update_basins_table()
            networks='mưa và bốc hơi' if self._evap_stations else 'mưa (chưa có mạng trạm bốc hơi)'
            self.lbl_map_status.config(text='Đã tính Thiessen '+networks+' riêng cho lưu vực đang chọn. Tổng trọng số mỗi mạng đã nhập = 1.')
        except Exception as exc:messagebox.showerror('Thiessen',str(exc),parent=self.root)

    def _draw_basin_map(self):
        self._sync_map_stations();self.map_ax.clear();self.map_tree.delete(*self.map_tree.get_children())
        if self._basin_geojson is None:
            for name in dict.fromkeys([*self.rain_stations,*self._station_positions]):
                point=self._station_positions.get(name)
                self.map_tree.insert('','end',values=(name,f'{point[0]:.7f}' if point else 'Chưa đặt',f'{point[1]:.7f}' if point else '',
                    '','',self.rain_stations[name]['source'] if name in self.rain_stations else 'Chưa chọn dữ liệu'))
            self.map_ax.text(.5,.5,'Chưa nhập bản đồ lưu vực',transform=self.map_ax.transAxes,ha='center')
            self.map_canvas.draw();return
        try:
            _,_,_,_,_,_,_,_= _geo_modules()
            from matplotlib.path import Path as PlotPath
            from matplotlib.patches import PathPatch
            basin,crs,forward=basin_metric_geometry(self._basin_geojson,self._common_map_crs())
            def draw_polygon(geom,color,alpha):
                if geom.is_empty:return
                if geom.geom_type in ('MultiPolygon','GeometryCollection'):
                    for part in geom.geoms:draw_polygon(part,color,alpha)
                elif geom.geom_type=='Polygon':
                    from shapely.geometry.polygon import orient
                    geom=orient(geom,sign=1.)
                    vertices=[];codes=[]
                    for ring in [geom.exterior,*geom.interiors]:
                        coords=[(coordinate[0],coordinate[1]) for coordinate in ring.coords];vertices.extend(coords);codes.extend([PlotPath.MOVETO]+[PlotPath.LINETO]*(len(coords)-2)+[PlotPath.CLOSEPOLY])
                    self.map_ax.add_patch(PathPatch(PlotPath(vertices,codes),facecolor=color,edgecolor='#28536b',alpha=alpha,lw=1.1))
            draw_polygon(basin,'none',1.)
            if self._shape_basins:
                _,shape,_,_,transform,_,_,_=_geo_modules()
                for feature in self._shape_basins:
                    part=transform(lambda x,y,z=None:forward.transform(x,y,errcheck=True),shape(feature['geometry']))
                    draw_polygon(part,'none',1.)
                    center=part.representative_point();self.map_ax.annotate(feature['name'],(center.x,center.y),fontsize=8,color='#315779')
            result=self._thiessen_result
            if result is not None and self.show_thiessen.get():
                colors=['#79c7c5','#f2b880','#a6c48a','#b5a7d4','#ef9c9c']
                for i,cell in enumerate(result['cells'].values()):
                    _,_,_,_,transform,_,_,_=_geo_modules()
                    convert=horizontal_transformer(result['crs'],crs)
                    draw_polygon(transform(convert.transform,cell),colors[i%len(colors)],.65)
            for name in dict.fromkeys([*self.rain_stations,*self._station_positions]):
                point=self._station_positions.get(name)
                if point is None:
                    self.map_tree.insert('','end',values=(name,'Chưa đặt','','','','Đã nhập' if name in self.rain_stations else 'Chưa nhập'));continue
                x,y=forward.transform(*point);self.map_ax.plot(x,y,'+',color='#228b22',markersize=11,markeredgewidth=1.5)
                self.map_ax.annotate(name,(x,y),xytext=(5,5),textcoords='offset points',fontsize=9)
                area='' if result is None else f'{result["areas_km2"].get(name,0):.3f}'
                weight='' if result is None else f'{result["weights"].get(name,0):.6f}'
                self.map_tree.insert('','end',values=(name,f'{point[0]:.7f}',f'{point[1]:.7f}',area,weight,self.rain_stations[name]['source'] if name in self.rain_stations else 'Chưa chọn dữ liệu'))
            for name,point in self._evap_positions.items():
                x,y=forward.transform(*point);self.map_ax.plot(x,y,'s',color='#df8a16',markersize=7)
                self.map_ax.annotate('BH: '+name,(x,y),xytext=(5,-12),textcoords='offset points',fontsize=8)
                result_pet=self._evap_thiessen
                area='' if result_pet is None else f"{result_pet['areas_km2'].get(name,0):.3f}"
                weight='' if result_pet is None else f"{result_pet['weights'].get(name,0):.6f}"
                self.map_tree.insert('','end',values=('BH: '+name,f'{point[0]:.7f}',f'{point[1]:.7f}',area,weight,self._evap_stations[name]['source'] if name in self._evap_stations else 'Chưa chọn dữ liệu'))
            self.map_ax.autoscale_view();self.map_ax.margins(.1);self.map_ax.set_aspect('equal',adjustable='datalim')
            self.map_ax.set(xlabel='Easting (m)',ylabel='Northing (m)',title='Lưu vực và trạm — cùng hệ tọa độ phẳng hiển thị')
            self.map_ax.ticklabel_format(style='plain',useOffset=False);self.map_ax.grid(color='#5ca9df',linestyle='--',alpha=.65)
            authority=crs.to_authority();crs_label=':'.join(authority) if authority else crs.name
            self.lbl_map_status.config(text=f'{self._basin_source} — Diện tích NAM: {basin_metric_geometry(self._basin_geojson)[0].area/1e6:.3f} km². Hệ hiển thị: {crs_label}.')
            self.map_fig.tight_layout();self.map_canvas.draw()
        except Exception as exc:
            self.lbl_map_status.config(text=str(exc));self.map_ax.clear()
            self.map_ax.text(.5,.5,'Không hiển thị được bản đồ: '+str(exc),transform=self.map_ax.transAxes,ha='center',wrap=True)
            self.map_canvas.draw()

    # Dự án JSON tự chứa dữ liệu, không phụ thuộc đường dẫn tệp nguồn.
    _PROJECT_ENTRIES=('ent_area','ent_dt','ent_warm','ent_split','ent_u','ent_l',
                      'ent_base','ent_surf','ent_inter','ent_period_start',
                      'ent_period_end','ent_maxiter','ent_runs')

    @staticmethod
    def _pack_series(frame):
        data=json.loads(frame.to_json(orient='split',date_format='iso',date_unit='ns',double_precision=15))
        data.pop('index',None)
        data['attrs']=frame.attrs.copy()
        return data

    @staticmethod
    def _unpack_series(data,key):
        if not isinstance(data,dict):raise ValueError('Bảng dữ liệu dự án không hợp lệ.')
        frame=pd.DataFrame(data['data'],columns=data['columns'])
        result=prepare_series(frame,key)
        attrs=data.get('attrs',{})
        if not isinstance(attrs,dict):raise ValueError('Thông tin chuỗi không hợp lệ.')
        result.attrs=attrs.copy()
        if key=='BocHoi_mm' and attrs.get('pet_mode','step_total') not in ('step_total','month_total','month_daily_mean','day_total'):
            raise ValueError('Cách biểu diễn bốc hơi không hợp lệ.')
        return result

    def _project_payload(self):
        self._capture_active_basin()
        calibrated=None
        if self._calibrated_params is not None:
            calibrated=dict(params=self._calibrated_params,area=self._calibrated_area,
                            discharge_mode=self._calibrated_discharge_mode)
        return dict(format='NAM-project',version=1,model_version=MODEL_VERSION,
                    validation_mode=self.validation_mode,
                    settings={name:getattr(self,name).get() for name in self._PROJECT_ENTRIES},
                    auto_period=self.auto_period.get(),auto_dt=self.auto_dt.get(),
                    discharge_mode=self._discharge_mode(),params=self.best_params.copy(),
                    bounds=[list(pair) for pair in self.param_bounds],calibrated=calibrated,
                    multi_basins=dict(show_thiessen=self.show_thiessen.get(),map_crs=self._map_crs_wkt,basin_input_crs=self._basin_input_crs,features=self._shape_basins,basins=self._basins,active=self._active_basin_id,
                        evap_positions=self._evap_positions,evap_stations={name:dict(weight=item['weight'],source=item['source'],data=self._pack_series(item['data'])) for name,item in self._evap_stations.items()}),
                    demo=self._is_demo,basin_map=dict(geometry=self._basin_geojson,source=self._basin_source,stations=self._station_positions,thiessen_computed=self._thiessen_result is not None),
                    rain_stations=[dict(name=name,weight=item['weight'],source=item['source'],
                        data=self._pack_series(item['data'])) for name,item in self.rain_stations.items()],
                    input_series={key:self._pack_series(frame) for key,frame in self.input_series.items() if key!='Mua_mm'})

    def _project_text(self):
        return json.dumps(self._project_payload(),ensure_ascii=False,sort_keys=True,allow_nan=False)

    def _update_project_title(self):
        name=Path(self._project_path).name if self._project_path else 'Dự án mới'
        self.lbl_project.config(text=name)
        self.root.title(('NAM — Kiểm định độc lập' if self.validation_mode else 'Phần mềm Thủy văn NAM')+' — '+name)

    def _project_idle(self):
        if self._busy:
            messagebox.showinfo('Dự án','Hãy dừng hoặc hoàn tất hiệu chỉnh trước khi thao tác dự án.',parent=self.root)
            return False
        return True

    def _confirm_project_change(self):
        if not self._project_idle():return False
        if self._project_text()==self._saved_project:return True
        answer=messagebox.askyesnocancel('Lưu dự án','Dự án có thay đổi chưa lưu. Bạn muốn lưu trước khi tiếp tục?',parent=self.root)
        return False if answer is None else self._save_project() if answer else True

    def _save_project(self,save_as=False):
        if not self._project_idle():return False
        path=self._project_path
        if save_as or not path:
            path=filedialog.asksaveasfilename(parent=self.root,title='Lưu dự án NAM',
                defaultextension='.namproj',filetypes=[('Dự án NAM','*.namproj')],
                initialfile=Path(path).name if path else 'DuAnNAM.namproj')
        if not path:return False
        temporary=None
        try:
            content=self._project_text()
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=Path(path).parent,
                    prefix='.nam-',suffix='.tmp',delete=False) as stream:
                temporary=stream.name;stream.write(content);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
            self._project_path=str(path);self._saved_project=content;self._update_project_title()
            self.lbl_calib_status.config(text='Đã lưu dự án: '+Path(path).name)
            return True
        except Exception as exc:
            messagebox.showerror('Lưu dự án',str(exc),parent=self.root);return False
        finally:
            if temporary and os.path.exists(temporary):os.unlink(temporary)

    def _decode_project(self,payload):
        if payload.get('format')!='NAM-project' or payload.get('version')!=1:
            raise ValueError('Tệp không phải dự án NAM được hỗ trợ.')
        if payload.get('validation_mode')!=self.validation_mode:
            raise ValueError('Mở dự án kiểm định trong cửa sổ kiểm định; mở dự án hiệu chỉnh trong cửa sổ chính.')
        settings=payload['settings']
        if set(settings)!=set(self._PROJECT_ENTRIES) or not all(isinstance(v,str) for v in settings.values()):
            raise ValueError('Thiếu hoặc sai thông tin thiết lập dự án.')
        def parameters(values):
            if set(values)!=set(PARAM_KEYS):raise ValueError('Dự án không đủ 9 thông số NAM.')
            result={key:float(values[key]) for key in PARAM_KEYS}
            if not all(np.isfinite(v) for v in result.values()):raise ValueError('Thông số phải hữu hạn.')
            for key,value in result.items():
                if key in ('CQOF','TOF','TIF','TG'):
                    if not 0<=value<=1 or (key!='CQOF' and value==1):raise ValueError('Thông số tỷ lệ/ngưỡng ngoài khoảng.')
                elif value<=0:raise ValueError('Dung tích và thời gian điều tiết phải dương.')
            return result
        params=parameters(payload['params'])
        bounds=[tuple(float(v) for v in pair) for pair in payload['bounds']]
        if len(bounds)!=len(PARAM_KEYS) or any(len(pair)!=2 or not all(np.isfinite(v) for v in pair) or pair[0]>=pair[1] for pair in bounds):
            raise ValueError('Giới hạn dò thông số không hợp lệ.')
        if payload.get('discharge_mode') not in ('mean','endpoint'):raise ValueError('Loại lưu lượng không hợp lệ.')
        for key in ('auto_period','auto_dt','demo'):
            if not isinstance(payload.get(key),bool):raise ValueError('Thiết lập dự án không hợp lệ.')
        stations={}
        for item in payload['rain_stations']:
            name=item['name'];weight=float(item['weight'])
            if not isinstance(name,str) or not name.strip() or name in stations or not np.isfinite(weight) or not 0<=weight<=1:
                raise ValueError('Tên hoặc trọng số trạm mưa không hợp lệ.')
            stations[name]=dict(data=self._unpack_series(item['data'],'Mua_mm'),weight=weight,source=str(item['source']))
        inputs={}
        for key,data in payload['input_series'].items():
            if key not in ('BocHoi_mm','Q_ThucDo_m3s'):raise ValueError('Loại dữ liệu dự án không hợp lệ.')
            inputs[key]=self._unpack_series(data,key)
        calibrated=payload.get('calibrated')
        if calibrated is not None:
            calibrated=dict(params=parameters(calibrated['params']),area=finite_number(calibrated['area'],'Diện tích hiệu chỉnh',True),discharge_mode=calibrated['discharge_mode'])
            if calibrated['discharge_mode'] not in ('mean','endpoint'):raise ValueError('Loại lưu lượng hiệu chỉnh không hợp lệ.')
        basin_map=payload.get('basin_map',{})
        if basin_map.get('geometry') is not None:basin_metric_geometry(basin_map['geometry'])
        for name,point in basin_map.get('stations',{}).items():
            if not isinstance(name,str) or len(point)!=2 or not all(np.isfinite(v) for v in point) or not (-180<=point[0]<=180 and -90<point[1]<90):
                raise ValueError('Vị trí trạm trong dự án không hợp lệ.')
        if basin_map.get('thiessen_computed'):
            if basin_map.get('geometry') is None or not stations or any(name not in basin_map.get('stations',{}) for name in stations):
                raise ValueError('Dự án thiếu lưu vực hoặc tọa độ dùng tính Thiessen.')
            thiessen_basin_weights(basin_map['geometry'],{name:basin_map['stations'][name] for name in stations})
        multi=payload.get('multi_basins',{})
        if multi.get('map_crs') is not None:
            crs=resolve_horizontal_crs(multi['map_crs'])
            if not crs.is_projected or any(not np.isclose(axis.unit_conversion_factor,1.) for axis in crs.axis_info[:2]):raise ValueError('Hệ bản đồ chung phải là hệ phẳng đơn vị mét.')
        if multi.get('basin_input_crs') is not None:resolve_horizontal_crs(multi['basin_input_crs'])
        features=multi.get('features',[]);basins=multi.get('basins',{})
        ids=set()
        for feature in features:
            if feature['id'] in ids:raise ValueError('Trùng mã lưu vực trong dự án.')
            ids.add(feature['id']);geometry,_,_=basin_metric_geometry(feature['geometry'])
            if not np.isclose(finite_number(feature['area_km2'],'Diện tích lưu vực',True),geometry.area/1e6,rtol=1e-8):raise ValueError('Diện tích không khớp hình học lưu vực.')
        if multi.get('active') is not None and multi['active'] not in basins:raise ValueError('Lưu vực đang chọn không có trong dự án.')
        for basin_id,record in basins.items():
            if basin_id!=record['id'] or basin_id not in ids:raise ValueError('Mã lưu vực không hợp lệ.')
            parameters(record['params'])
            geometry,_,_=basin_metric_geometry(record['geometry'])
            if not np.isclose(finite_number(record['area_km2'],'Diện tích lưu vực',True),geometry.area/1e6,rtol=1e-8):raise ValueError('Diện tích mô hình không khớp lưu vực.')
            if set(record['settings'])!=set(self._PROJECT_ENTRIES) or not all(isinstance(v,str) for v in record['settings'].values()):raise ValueError('Thiếu thiết lập lưu vực.')
            if record['discharge_mode'] not in ('mean','endpoint') or not isinstance(record['auto_period'],bool) or not isinstance(record['auto_dt'],bool):raise ValueError('Thiết lập mô hình lưu vực không hợp lệ.')
            limits=record['bounds']
            if len(limits)!=len(PARAM_KEYS) or any(len(pair)!=2 or not all(np.isfinite(v) for v in pair) or pair[0]>=pair[1] for pair in limits):raise ValueError('Giới hạn thông số lưu vực không hợp lệ.')
            if record.get('observed') is not None:self._unpack_series(record['observed'],'Q_ThucDo_m3s')
            if record.get('calibrated') is not None:parameters(record['calibrated']['params'])
            if record.get('validation_params') is not None:parameters(record['validation_params'])
            for result in [record.get('independent_metrics'),*record.get('validation_results',{}).values()]:
                if result is None:continue
                value=result.get('nse')
                if value is not None and (not isinstance(value,(int,float)) or not np.isfinite(value)):raise ValueError('NSE kiểm định trong dự án không hợp lệ.')
                if result.get('params') is not None:parameters(result['params'])
        for name,item in multi.get('evap_stations',{}).items():
            self._unpack_series(item['data'],'BocHoi_mm')
            if not isinstance(name,str) or not 0<=finite_number(item['weight'],'Trọng số bốc hơi')<=1:raise ValueError('Trạm bốc hơi không hợp lệ.')
        for point in multi.get('evap_positions',{}).values():
            if len(point)!=2 or not all(np.isfinite(v) for v in point) or not (-180<=point[0]<=180 and -90<point[1]<90):raise ValueError('Tọa độ bốc hơi không hợp lệ.')
        return params,bounds,stations,inputs,calibrated

    def _apply_project(self,payload,decoded):
        params,bounds,stations,inputs,calibrated=decoded
        multi=payload.get('multi_basins',{})
        self.show_thiessen.set(multi.get('show_thiessen',False))
        self._map_crs_wkt=multi.get('map_crs');self._basin_input_crs=multi.get('basin_input_crs')
        self._shape_basins=multi.get('features',[]);self._basins=multi.get('basins',{});self._active_basin_id=multi.get('active')
        self._evap_positions=multi.get('evap_positions',{})
        self._evap_stations={name:dict(weight=item['weight'],source=item['source'],data=self._unpack_series(item['data'],'BocHoi_mm')) for name,item in multi.get('evap_stations',{}).items()}
        self._evap_thiessen=None;self._spatial_signature=None
        self._parameter_source=None;self._independent_metrics=None;self._calibration_period=None
        if self.validation_mode:self._validation_forbidden_period=None
        if self._active_basin_id:
            record=self._basins[self._active_basin_id];self._parameter_source=record.get('parameter_source');self._independent_metrics=record.get('independent_metrics');self._calibration_period=record.get('calibration_period')
            if self.validation_mode:self._validation_forbidden_period=self._calibration_period
        for name,value in payload['settings'].items():
            entry=getattr(self,name);state=entry.cget('state');entry.config(state='normal')
            entry.delete(0,'end');entry.insert(0,value);entry.config(state=state)
        self.auto_dt.set(payload['auto_dt']);self.auto_period.set(payload['auto_period'])
        self.discharge_choice.current(1 if payload['discharge_mode']=='endpoint' else 0)
        self.best_params=params;self.param_bounds=bounds
        self.rain_stations=stations;self.input_series=inputs;self._is_demo=payload['demo']
        self._calibrated_params=None if calibrated is None else calibrated['params']
        if calibrated is not None:
            self._calibrated_area=calibrated['area'];self._calibrated_discharge_mode=calibrated['discharge_mode']
        basin_map=payload.get('basin_map',{})
        self._basin_geojson=basin_map.get('geometry');self._basin_source=basin_map.get('source','')
        self._station_positions=basin_map.get('stations',{});self._thiessen_result=None
        self._suggested_period=self._period();self.current_sim=None;self._result_signature=None
        for key,label in self.series_labels.items():
            frame=inputs.get(key)
            label.config(text='Chưa nhập' if frame is None else f'Dữ liệu trong dự án — {len(frame)} dòng',foreground='gray' if frame is None else 'blue')
        self._update_rain_label();self._update_parameter_display();self._refresh_inputs()
        if basin_map.get('thiessen_computed') and self._basin_geojson is not None:
            positions={name:self._station_positions[name] for name in self.rain_stations}
            result=thiessen_basin_weights(self._basin_geojson,positions)
            if all(np.isclose(item['weight'],result['weights'][name],atol=1e-10) for name,item in self.rain_stations.items()):
                self._thiessen_result=result
        if not self.validation_mode:self.ent_area.config(state='readonly' if self._active_basin_id else 'normal')
        self._draw_basin_map();self._update_basins_table()
        self.lbl_calib_status.config(text='Đã mở dự án. Bấm chạy mô phỏng để tính lại kết quả.' if stations else 'Sẵn sàng')

    def _open_project(self):
        if not self._project_idle():return
        path=filedialog.askopenfilename(parent=self.root,title='Mở dự án NAM',filetypes=[('Dự án NAM','*.namproj')])
        if not path:return
        try:
            payload=json.loads(Path(path).read_text(encoding='utf-8-sig'))
            decoded=self._decode_project(payload)
        except Exception as exc:
            messagebox.showerror('Mở dự án','Không mở được dự án: '+str(exc),parent=self.root);return
        if not self._confirm_project_change():return
        self._apply_project(payload,decoded);self._project_path=str(path)
        self._saved_project=self._project_text();self._update_project_title()

    def _new_project(self):
        if not self._confirm_project_change():return
        payload=json.loads(json.dumps(self._project_defaults))
        self._apply_project(payload,self._decode_project(payload))
        self._project_path=None;self._saved_project=self._project_text();self._update_project_title()

    def _close_project(self):
        if self._confirm_project_change():self.root.destroy()

    def _load_synthetic_data(self):
        if self._shape_basins:
            messagebox.showinfo('Dữ liệu giả lập','Tạo dự án mới trước khi thử số liệu giả lập, để giữ dữ liệu các lưu vực đang làm.',parent=self.root);return
        if self.validation_mode:
            messagebox.showinfo("Kiểm định","Nhập số liệu độc lập của bạn bằng các nút nhập mưa, bốc hơi và Q thực đo.");return
        """Sinh chuỗi mưa rào mẫu và lưu lượng thực đo giả lập 72 giờ."""
        n_hours = 72
        rain = np.zeros(n_hours)
        # Vũ biểu mưa rào cường độ lớn từ giờ thứ 8 đến 23
        rain[8:24] = [
            4,
            12,
            25,
            46,
            58,
            38,
            22,
            14,
            8,
            4,
            2,
            1,
            0.5,
            0.5,
            0.2,
            0.1,
        ]
        pet = np.full(n_hours, 0.2)

        # Tạo chuỗi lưu lượng giả định có nhiễu thực tế
        target_p = {
            "U_max": 18.0,
            "L_max": 120.0,
            "CQOF": 0.65,
            "CK_12": 10.0,
            "TOF": 0.2,
            "TIF": 0.15,
            "TG": 0.25,
            "CK_IF": 40.0,
            "CK_BF": 800.0,
        }
        res_true = run_nam(target_p, 150.0, rain, pet, 1.0,use_acceleration=NUMBA_AVAILABLE and bool(_nam_kernel.signatures))["Q_sim"]
        rng=np.random.default_rng(42)
        q_obs=np.maximum(0,res_true+rng.normal(0,res_true*.08,n_hours))
        self.ent_area.delete(0,'end');self.ent_area.insert(0,'150')
        self.ent_dt.delete(0,'end');self.ent_dt.insert(0,'1')

        self.df_data = pd.DataFrame(
            {"Mua_mm": rain, "BocHoi_mm": pet, "Q_ThucDo_m3s": q_obs}
        )
        times=pd.date_range('2000-01-01 01:00',periods=n_hours,freq='h')
        self.df_data.insert(0,'ThoiGian',times)
        self.input_series={k:self.df_data[['ThoiGian',k]].copy() for k in SERIES_NAMES}
        self.rain_stations={'Trạm giả lập':dict(data=self.input_series['Mua_mm'].copy(),weight=1.,source='Dữ liệu giả lập')}
        self._is_demo=True
        for key,label in self.series_labels.items():label.config(text='Giả lập: 72 bước giờ',foreground='green')
        self.lbl_data_status.config(text='DỮ LIỆU GIẢ LẬP, không phải quan trắc',foreground='green')
        self._update_parameter_display();self._update_rain_label()
        self._recompute_and_plot()

    def _update_parameter_display(self):
        for k, v in self.best_params.items():
            if k in self.param_labels:
                self.param_labels[k].config(text=f"{v:.2f}")

    def _settings(self):
        area=finite_number(self.ent_area.get(),'Diện tích',True)
        dt=finite_number(self.ent_dt.get(),'Bước tính',True)
        warm=finite_number(self.ent_warm.get(),'Khởi động')
        split=finite_number(self.ent_split.get(),'Tỷ lệ hiệu chỉnh')
        initial=dict(U_fraction=finite_number(self.ent_u.get(),'Độ đầy bể mặt'),L_fraction=finite_number(self.ent_l.get(),'Độ đầy bể rễ'),Q_base_m3s=finite_number(self.ent_base.get(),'Dòng ngầm đầu'),Q_surf_m3s=finite_number(self.ent_surf.get(),'Dòng tràn đầu'),Q_inter_m3s=finite_number(self.ent_inter.get(),'Dòng sát mặt đầu'))
        if warm<0 or not 0<split<=100 or any(not 0<=initial[k]<=1 for k in ['U_fraction','L_fraction']) or any(initial[k]<0 for k in ['Q_base_m3s','Q_surf_m3s','Q_inter_m3s']):
            raise ValueError('Khởi động ≥0 giờ; hiệu chỉnh trong (0;100]%; độ đầy trong [0;1]; dòng ngầm ≥0.')
        return area,dt,int(np.ceil(warm/dt)),split/100,initial

    def _discharge_mode(self):
        return 'endpoint' if self.discharge_choice.current()==1 else 'mean'

    def _signature(self):
        return (self._active_basin_id,)+tuple(e.get() for e in self.setting_entries)+(self.ent_maxiter.get(),self.ent_runs.get(),self.auto_period.get(),self.auto_dt.get(),self._discharge_mode())+tuple(self.best_params.items())+(id(self.df_data),)+tuple(self.param_bounds)+tuple((name,v['weight'],id(v['data'])) for name,v in self.rain_stations.items())+tuple((name,v['weight'],id(v['data'])) for name,v in self._evap_stations.items())+tuple((name,tuple(point)) for name,point in self._station_positions.items())+tuple((name,tuple(point)) for name,point in self._evap_positions.items())

    def _watch(self):
        if self.current_sim is not None and self._result_signature!=self._signature():
            self.current_sim=None
            self.lbl_calib_status.config(text='Đầu vào đã đổi: chạy mô phỏng lại trước khi xuất.')
            self.ax_flow.clear();self.ax_volume.clear();self.canvas.draw()
            for label in [self.lbl_metric_nse,self.lbl_metric_peak,self.lbl_metric_pbias]:label.config(text='Cần tính lại')
        self.root.after(300,self._watch)

    def _run_manual(self):
        self._refresh_inputs()
        if self.df_data is None:
            messagebox.showwarning('Dữ liệu',self.lbl_data_status.cget('text'));return
        self._recompute_and_plot()

    def _open_validation(self):
        if self._active_basin_id and not self._busy:
            self._open_basin_validation();return
        if self._busy:
            messagebox.showinfo("Kiểm định","Dừng hoặc hoàn tất hiệu chỉnh trước khi mở kiểm định.");return
        if self._calibrated_params is None:
            messagebox.showwarning("Kiểm định","Hãy hiệu chỉnh để có bộ thông số trước khi kiểm định dữ liệu mới.");return
        window=tk.Toplevel(self.root)
        app=NAMDesktopApp(window,validation_params=self._calibrated_params)
        app.discharge_choice.current(1 if getattr(self,'_calibrated_discharge_mode','mean')=='endpoint' else 0)
        app.discharge_choice.config(state='disabled')
        app.ent_area.delete(0,"end");app.ent_area.insert(0,str(self._calibrated_area));app.ent_area.config(state="readonly")
        app._project_defaults=app._project_payload();app._saved_project=app._project_text()
        app._update_project_title()
        app._basin_geojson=self._basin_geojson;app._basin_source=self._basin_source
        app._station_positions={name:list(point) for name,point in self._station_positions.items()}
        app._project_defaults=app._project_payload();app._saved_project=app._project_text();app._draw_basin_map()
        window._nam_app=app

    def _edit_parameters(self):
        if self.validation_mode:return
        window=tk.Toplevel(self.root);window.title('Thông số mô hình và đơn vị')
        entries={};bound_entries={}
        for col,title in enumerate(["Thông số / đơn vị","Giá trị","Cận dưới dò","Cận trên dò"]):ttk.Label(window,text=title).grid(row=0,column=col,padx=8,pady=5)
        descriptions=['Dung tích mặt (mm)','Dung tích rễ (mm)','Hệ số dòng tràn (0–1)',
                      'Điều tiết tràn/sát mặt (giờ)','Ngưỡng dòng tràn (0–<1)',
                      'Ngưỡng sát mặt (0–<1)','Ngưỡng bổ cập ngầm (0–<1)',
                      'Sinh dòng sát mặt (giờ)','Điều tiết ngầm (giờ)']
        for i,(key,desc) in enumerate(zip(PARAM_KEYS,descriptions),1):
            ttk.Label(window,text=key+' — '+desc).grid(row=i,column=0,sticky='w',padx=8,pady=3)
            e=ttk.Entry(window);e.insert(0,str(self.best_params[key]));e.grid(row=i,column=1,padx=8);entries[key]=e
            bounds=[]
            for col,val in enumerate(self.param_bounds[i-1],2):
                e=ttk.Entry(window,width=12);e.insert(0,str(val));e.grid(row=i,column=col,padx=5);bounds.append(e)
            bound_entries[key]=bounds
        def save():
            try:
                params={k:finite_number(e.get(),k) for k,e in entries.items()}
                new_bounds=[tuple(finite_number(e.get(),k+' giới hạn') for e in bound_entries[k]) for k in PARAM_KEYS]
                if any(lo>=hi for lo,hi in new_bounds):raise ValueError('Cận dưới phải nhỏ hơn cận trên.')
                for edge in [0,1]:run_nam(dict(zip(PARAM_KEYS,[b[edge] for b in new_bounds])),1.,[0.],[0.],1.,use_acceleration=False)
                run_nam(params,1.,[0.],[0.],1.,use_acceleration=False)
                self.param_bounds=new_bounds
                self.best_params=params;self._update_parameter_display();window.destroy();self._recompute_and_plot()
            except Exception as exc:messagebox.showerror('Thông số',str(exc),parent=window)
        ttk.Button(window,text='Áp dụng và mô phỏng',command=save).grid(row=10,column=0,columnspan=4,pady=8)
        window.transient(self.root);window.grab_set()

    def _choose_dfs_item(self,items):
        choices='\n'.join(f'{i+1}. {item.name} — {item.unit} ({item.data_value_type.name})' for i,item in enumerate(items))
        number=simpledialog.askinteger('Chọn chuỗi trong DFS0',choices+'\nNhập số thứ tự mục muốn dùng:',minvalue=1,maxvalue=len(items),parent=self.root)
        return None if number is None else number-1

    def _import_rain_station(self,station_name=None):
        if not self._project_idle():return
        if station_name is not None and not station_name.strip():
            messagebox.showinfo("Trạm mưa","Chọn hoặc tạo vị trí trạm trước.",parent=self.root);return
        path=filedialog.askopenfilename(title='Nhập mưa một trạm: giá trị hoặc ThoiGian + Mua_mm',filetypes=[('CSV / Excel / MIKE DFS0','*.csv *.xlsx *.dfs0')])
        if not path:return
        try:
            df=read_series_file(path,'Mua_mm',self._choose_dfs_item)
            data=prepare_series(df,'Mua_mm')
            name=station_name if station_name is not None else simpledialog.askstring('Tên trạm mưa','Tên trạm:',initialvalue=os.path.splitext(os.path.basename(path))[0],parent=self.root)
            if name is None:return
            name=name.strip()
            if not name:raise ValueError('Tên trạm không được trống.')
            if name in self.rain_stations and not self._is_demo:
                if station_name is None:raise ValueError('Trạm đã có. Chọn trạm trong tab bản đồ để thay dữ liệu.')
                if not messagebox.askyesno('Thay dữ liệu mưa','Thay chuỗi mưa hiện có của trạm '+name+' bằng tệp vừa chọn?',parent=self.root):return
            if station_name is not None:
                weight=self.rain_stations[name]['weight'] if name in self.rain_stations and not self._is_demo else 1. if not self.rain_stations or self._is_demo else 0.
            else:weight=simpledialog.askfloat('Trọng số trạm','Trọng số từ 0 đến 1; tổng các trạm phải bằng 1:',initialvalue=1 if not self.rain_stations or self._is_demo else 0,minvalue=0,maxvalue=1,parent=self.root)
            if weight is None:return
            if not np.isfinite(weight):raise ValueError('Trọng số phải hữu hạn.')
            if self._is_demo:
                self.input_series={};self.rain_stations={};self._is_demo=False
                for label in self.series_labels.values():label.config(text='Chưa nhập',foreground='gray')
            self.rain_stations[name]=dict(data=data,weight=weight,source=os.path.basename(path))
            self._update_rain_label();self._refresh_inputs()
            if station_name is not None and self._basin_geojson is not None and set(self.rain_stations)==set(self._station_positions):
                self._calculate_thiessen()
            if data.attrs.get('import_notes'):messagebox.showinfo('Thông tin trạm mưa','\n'.join(data.attrs['import_notes']))
        except ImportCancelled:return
        except Exception as exc:messagebox.showerror('Nhập trạm mưa',str(exc))

    def _update_rain_label(self):
        self._thiessen_result=None;self._spatial_signature=None
        self._sync_map_stations()
        self.series_labels['Mua_mm'].config(text=f'{len(self.rain_stations)} trạm; tổng trọng số = {sum(v["weight"] for v in self.rain_stations.values()):.6f}',foreground='blue')
        self._draw_basin_map()

    def _manage_rain(self):
        window=tk.Toplevel(self.root);window.title('Trạm mưa và trọng số lưu vực');window.geometry('750x420')
        frame=ttk.Frame(window);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=('name','weight','count','source'),show='headings',selectmode='browse')
        for col,title in [('name','Tên trạm'),('weight','Trọng số'),('count','Số dòng'),('source','Tệp nguồn')]:tree.heading(col,text=title);tree.column(col,width=150)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');tree.pack(fill='both',expand=True)
        total=ttk.Label(window);total.pack(pady=4)
        def refresh():
            tree.delete(*tree.get_children())
            for i,(name,item) in enumerate(self.rain_stations.items()):tree.insert('', 'end',iid=str(i),values=(name,f'{item["weight"]:.8g}',len(item['data']),item['source']))
            total.config(text=f'Tổng trọng số = {sum(v["weight"] for v in self.rain_stations.values()):.8g} (bắt buộc bằng 1)')
        def selected():
            return tree.item(tree.selection()[0],'values')[0] if tree.selection() else None
        def edit(event=None):
            if self._basins:self._calculate_thiessen();refresh();return
            name=selected()
            if name is None:return
            weight=simpledialog.askfloat('Trọng số',name+':',initialvalue=self.rain_stations[name]['weight'],minvalue=0,maxvalue=1,parent=window)
            if weight is not None and np.isfinite(weight):
                self.rain_stations[name]['weight']=weight;refresh();self._update_rain_label();self._refresh_inputs()
        def delete():
            name=selected()
            if name is not None:
                del self.rain_stations[name];self._station_positions.pop(name,None)
                refresh();self._update_rain_label();self._refresh_inputs()
        def view():
            name=selected()
            if name is not None:self._view_series('Mua_mm',self.rain_stations[name]['data'])
        row=ttk.Frame(window);row.pack(fill='x',pady=5)
        for text,command in [('Thêm trạm',lambda:(self._import_rain_station(),refresh())),('Tính Thiessen' if self._basins else 'Sửa trọng số',edit),('Xóa trạm',delete),('Xem mưa trạm',view),('Xem mưa bình quân',lambda:self._view_series('Mua_mm'))]:ttk.Button(row,text=text,command=command).pack(side='left',padx=3)
        tree.bind('<Double-1>',edit);refresh()

    def _import_series(self,key):
        if key=='Mua_mm':self._import_rain_station();return
        if key=='BocHoi_mm' and self._basins:
            self._station_coordinate_dialog('evap');return
        path=filedialog.askopenfilename(title='Nhập riêng '+SERIES_NAMES[key],filetypes=[('CSV / Excel / MIKE DFS0','*.csv *.xlsx *.dfs0'),('MIKE DFS0','*.dfs0'),('Excel','*.xlsx'),('CSV','*.csv')])
        if not path:return
        try:
            df=read_series_file(path,key,self._choose_dfs_item)
            prepared=prepare_series(df,key)
            if key=='BocHoi_mm' and 'ThoiGian' in prepared:
                mode=simpledialog.askinteger('Cách biểu diễn bốc hơi','1. Tổng mm mỗi bước, thời gian là cuối bước (giờ/ngày/chu kỳ đều).\n2. Tổng mm/tháng, ngày ghi thuộc tháng tương ứng.\n3. Trung bình mm/ngày của tháng.\n4. Tổng mm/ngày, ngày ghi là ngày tương ứng.\nChọn cách biểu diễn trong tệp:',minvalue=1,maxvalue=4,initialvalue=1,parent=self.root)
                if mode is None:return
                prepared.attrs['pet_mode']={1:'step_total',2:'month_total',3:'month_daily_mean',4:'day_total'}[mode]
                prepared.attrs['import_notes'].append('Bốc hơi: '+{1:'tổng mỗi bước, ghi cuối bước',2:'tổng tháng',3:'trung bình ngày của tháng',4:'tổng ngày theo lịch'}[mode]+'; phân bổ đều về bước mô phỏng, giữ tổng lượng.')
            if self._is_demo:
                self.input_series={};self.rain_stations={};self._is_demo=False
                for label in self.series_labels.values():label.config(text='Chưa nhập',foreground='gray')
            self.input_series[key]=prepared
            self.series_labels[key].config(text=f'{os.path.basename(path)} — {len(prepared)} dòng'+(' (có Q thiếu ngày bị loại)' if any('thiếu ngày giờ' in n for n in prepared.attrs.get('import_notes',[])) else ''),foreground='blue')
            self._refresh_inputs()
            self._capture_active_basin();self._update_basins_table()
            if prepared.attrs.get('import_notes'):messagebox.showinfo('Thông tin nhập dữ liệu','\n'.join(prepared.attrs['import_notes']))
        except ImportCancelled:return
        except Exception as exc:messagebox.showerror('Nhập '+SERIES_NAMES[key],str(exc))

    def _request_period_suggestion(self):
        self._suggested_period=self._period()
        self._refresh_inputs()

    def _period(self):
        return self.ent_period_start.get().strip(),self.ent_period_end.get().strip()

    def _refresh_inputs(self):
        self.df_data=None;self.current_sim=None;self.ax_rain.clear();self.ax_flow.clear();self.ax_volume.clear();self.canvas.draw()
        for label in [self.lbl_metric_nse,self.lbl_metric_peak,self.lbl_metric_pbias]:label.config(text='Chưa tính')
        if self._shape_basins and self._active_basin_id is None:
            self.df_data=None;self.current_sim=None
            self.lbl_data_status.config(text='Bấm Chuyển tất cả lưu vực sang NAM, rồi chọn lưu vực mô phỏng.',foreground='#b00020');return
        if self._active_basin_id:
            try:self._assign_spatial_weights()
            except Exception as exc:
                self.df_data=None;self.current_sim=None
                self.lbl_data_status.config(text=str(exc),foreground='#b00020');return
        auto_note=''
        if self.auto_dt.get():
            try:
                inferred=infer_time_step(self.rain_stations,self.input_series)
                if inferred is not None:
                    self.ent_dt.delete(0,'end');self.ent_dt.insert(0,f'{inferred:g}')
            except Exception as exc:self.lbl_data_status.config(text=str(exc),foreground='#b00020');return
        if self._active_basin_id and not self._evap_stations:
            self.lbl_data_status.config(text='Thêm trạm bốc hơi cùng tọa độ và dữ liệu để tính Thiessen cho từng lưu vực.',foreground='#b00020');return
        if self._evap_stations and self.rain_stations:
            try:
                reference=next(item['data'] for item in self.rain_stations.values() if item['weight']>0)
                self.input_series['BocHoi_mm']=weighted_evaporation(self._evap_stations,reference,finite_number(self.ent_dt.get(),'Bước tính',True))
                self.series_labels['BocHoi_mm'].config(text=f'{len(self._evap_stations)} trạm; bốc hơi bình quân Thiessen riêng cho lưu vực.',foreground='blue')
            except Exception as exc:
                self.df_data=None;self.lbl_data_status.config(text=str(exc),foreground='#b00020');return
        current_period=self._period()
        if any(current_period) and current_period!=getattr(self,'_suggested_period',('','')):self.auto_period.set(False)
        if self.auto_period.get():
            try:
                detected=detect_common_period(self.rain_stations,self.input_series,finite_number(self.ent_dt.get(),'Bước tính',True))
                if detected:
                    for entry in [self.ent_period_start,self.ent_period_end]:entry.delete(0,'end')
                    start,end,segments,count=detected
                    self.ent_period_start.insert(0,start);self.ent_period_end.insert(0,end)
                    self._suggested_period=(start,end)
                    auto_note=f' Khoảng tham khảo từ dữ liệu: {count} bước.'+ (f' Có {segments} đoạn; chọn đoạn liên tục dài nhất.' if segments>1 else '')
                else:auto_note=' Chưa đủ mưa/bốc hơi để gợi ý khoảng mô phỏng.'
            except Exception as exc:
                self.lbl_data_status.config(text=str(exc),foreground='#b00020');return
        if self.rain_stations:
            try:self.input_series['Mua_mm']=weighted_rainfall(self.rain_stations,*self._period())
            except Exception as exc:
                self.input_series.pop('Mua_mm',None);self.lbl_data_status.config(text=str(exc),foreground='#b00020');return
        else:self.input_series.pop('Mua_mm',None)
        if not all(k in self.input_series for k in ['Mua_mm','BocHoi_mm']):
            self.lbl_data_status.config(text='Cần nhập đủ mưa và bốc hơi; Q thực đo tùy chọn.',foreground='gray');return
        try:
            _,dt,_,_,_=self._settings()
            self.df_data=merge_series(self.input_series,dt,*self._period())
            count=self.df_data['Q_ThucDo_m3s'].notna().sum()
            self.lbl_data_status.config(text=f'{len(self.df_data)} bước; {count} Q thực đo; {self.df_data.attrs.get("outside_Q_count",0)} Q ngoài khoảng không dùng.\n{self.df_data.iloc[0,0]} → {self.df_data.iloc[-1,0]}'+auto_note,foreground='blue')
        except Exception as exc:self.lbl_data_status.config(text=str(exc),foreground='#b00020')

    def _clear_observed(self):
        self.input_series.pop('Q_ThucDo_m3s',None)
        self.series_labels['Q_ThucDo_m3s'].config(text='Chưa nhập (không bắt buộc)',foreground='gray')
        self._refresh_inputs();self._capture_active_basin();self._update_basins_table()

    def _view_series(self,key,data=None):
        if data is None and key not in self.input_series:
            messagebox.showinfo('Bảng dữ liệu','Chưa nhập '+SERIES_NAMES[key]);return
        window=tk.Toplevel(self.root);window.title(SERIES_NAMES[key]);window.geometry('650x450')
        frame=ttk.Frame(window);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=('time','value'),show='headings')
        tree.heading('time',text='Thời gian (cuối bước)' if series_axis(self.input_series[key] if data is None else data)=='ThoiGian' else 'Bước tính (1, 2, 3…)');tree.heading('value',text=SERIES_NAMES[key])
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');tree.pack(fill='both',expand=True)
        for timestamp,value in (self.input_series[key] if data is None else data).itertuples(index=False,name=None):
            tree.insert('', 'end',values=(str(timestamp),'—' if pd.isna(value) else f'{value:.3f}'))
        ttk.Label(window,text='Có ngày giờ: ghép theo thời gian. Một cột: ghép theo thứ tự bước, cùng thời điểm bắt đầu.').pack(pady=5)

    def _start_calibration_thread(self):
        if self.validation_mode:return
        if self._busy:return
        self._refresh_inputs()
        if self.df_data is None:
            messagebox.showwarning('Dữ liệu',self.lbl_data_status.cget('text'));return
        try:
            area,dt,warm,split,initial=self._settings()
            df=validate_data(self.df_data,dt)
            maxiter=int(self.ent_maxiter.get())
            runs=int(self.ent_runs.get())
            if any(not lo<=self.best_params[k]<=hi for k,(lo,hi) in zip(PARAM_KEYS,self.param_bounds)):
                raise ValueError('Thông số đầu nằm ngoài giới hạn dò. Chỉnh giá trị hoặc giới hạn trong bảng thông số.')
            if maxiter<=0 or runs<=0:raise ValueError('Số thế hệ và số lần chạy phải là số nguyên dương.')
            end=warm+int((len(df)-warm)*split)
            obs=df['Q_ThucDo_m3s'].to_numpy()[warm:end]
            if np.count_nonzero(np.isfinite(obs))<3 or not np.isfinite(compute_nse(obs,np.zeros(len(obs)))):
                raise ValueError('Sau khởi động, phần hiệu chỉnh cần ≥3 Q thực đo và phương sai khác 0.')
            snapshot=(self._signature(),df.copy(deep=True),area,dt,warm,end,initial,maxiter,self.best_params.copy(),runs,self.param_bounds.copy(),self._discharge_mode())
        except Exception as exc:messagebox.showerror('Hiệu chỉnh',str(exc));return
        self._stop_event.clear();self.btn_stop.config(state=tk.NORMAL)
        self._busy=True;self.btn_calibrate.config(state=tk.DISABLED);self.progress_bar.config(value=0,maximum=100)
        self.lbl_calib_status.config(text='Đang hiệu chỉnh; lần đầu Numba cần biên dịch để tăng tốc.' if NUMBA_AVAILABLE else 'Đang hiệu chỉnh bằng Python; cài numba để tăng tốc.',foreground='#D9534F')
        threading.Thread(target=self._run_optimization_worker,args=(snapshot,),daemon=True).start()
        self.root.after(100,self._poll_worker)

    def _stop_calibration(self):
        if self._busy:
            self._stop_event.set();self.btn_stop.config(state=tk.DISABLED)
            self.lbl_calib_status.config(text="Đang dừng; giữ bộ thông số tốt nhất đã tìm được.")

    def _run_optimization_worker(self,snapshot):
        try:
            signature,df,area,dt,warm,end,initial,maxiter=snapshot[:8]
            current=snapshot[8] if len(snapshot)>8 else dict(zip(PARAM_KEYS,[15,100,.5,15,.2,.2,.3,50,1000]))
            runs=snapshot[9] if len(snapshot)>9 else 1
            bounds=snapshot[10] if len(snapshot)>10 else PARAM_BOUNDS
            discharge_mode=snapshot[11] if len(snapshot)>11 else 'mean'
            started=time.perf_counter()
            rain=np.ascontiguousarray(df['Mua_mm'].to_numpy()[:end]);pet=np.ascontiguousarray(df['BocHoi_mm'].to_numpy()[:end]);obs=df['Q_ThucDo_m3s'].to_numpy()
            best_params=current.copy();best_nse=np.nan
            cache={};evaluations=0;cache_hits=0
            valid=np.isfinite(obs[warm:end]);observed=obs[warm:end][valid]
            normalizer=np.sqrt(np.sum((observed-observed.mean())**2))
            if len(observed)<3 or not np.isfinite(normalizer) or normalizer<=0:raise ValueError('Hiệu chỉnh cần ít nhất 3 Q thực đo và phương sai khác 0.')
            cache_limit=max(1,min(5000,16_000_000//max(8,len(observed)*8)))
            def residuals(params):
                nonlocal evaluations,cache_hits
                if self._stop_event.is_set():raise CalibrationStopped()
                key=tuple(float(params[k]) for k in PARAM_KEYS)
                if key in cache:cache_hits+=1;return cache[key]
                sim=calibration_discharge(params,area,rain,pet,dt,initial,self._stop_event,discharge_mode)
                values=(sim[warm:end][valid]-observed)/normalizer
                if not np.all(np.isfinite(values)):raise ValueError('Mô phỏng không hữu hạn.')
                if len(cache)>=cache_limit:cache.clear()
                cache[key]=values;evaluations+=1
                return values
            def score(params):
                values=residuals(params);nse=1-float(np.dot(values,values))
                if not np.isfinite(nse):raise ValueError('NSE không xác định; kiểm tra chuỗi thực đo và giai đoạn đánh giá.')
                return nse
            # Positive storage/time constants span orders of magnitude: search in log space.
            lower=np.array(bounds,dtype=float)[:,0];upper=np.array(bounds,dtype=float)[:,1]
            logarithmic=np.array([k in ('U_max','L_max','CK_12','CK_IF','CK_BF') and lo>0 for k,lo in zip(PARAM_KEYS,lower)])
            low=lower.copy();high=upper.copy();low[logarithmic]=np.log(lower[logarithmic]);high[logarithmic]=np.log(upper[logarithmic])
            def decode(x):
                values=low+np.asarray(x)*(high-low);values[logarithmic]=np.exp(values[logarithmic])
                return dict(zip(PARAM_KEYS,np.clip(values,lower,upper)))
            def encode(params):
                values=np.array([params[k] for k in PARAM_KEYS]);values[logarithmic]=np.log(values[logarithmic])
                return np.clip((values-low)/(high-low),0,1)
            best_params=current.copy();best_nse=score(best_params)
            def objective(x):
                nonlocal best_params,best_nse
                params=decode(x);nse=score(params)
                if nse>best_nse:best_nse=nse;best_params=params.copy()
                return 1-nse
            converged=0
            for run in range(runs):
                generation=0
                def callback(xk,convergence):
                    nonlocal generation
                    generation+=1
                    elapsed=time.perf_counter()-started
                    self._worker_queue.put(('progress',f'Lần {run+1}/{runs} · thế hệ {generation}/{maxiter}\nNSE tốt nhất: {best_nse:.4f} · {evaluations} mô phỏng · {elapsed:.1f} giây',90*(run+generation/maxiter)/runs))
                    return self._stop_event.is_set()
                candidate=encode(best_params)
                population=qmc.LatinHypercube(d=len(PARAM_KEYS),seed=42+run).random(10*len(PARAM_KEYS))
                population[:9]=np.clip(candidate+np.random.default_rng(42+run).normal(0,.08,(9,len(PARAM_KEYS))),0,1)
                population[0]=candidate
                result=differential_evolution(objective,bounds=[(0.,1.)]*len(PARAM_KEYS),maxiter=maxiter,tol=.005,
                    seed=42+run,polish=False,init=population,callback=callback)
                converged+=int(result.success)
            self._worker_queue.put(('progress','Tinh chỉnh cục bộ bộ thông số tốt nhất bằng NAM…',90))
            def local_residual(x):
                objective(x)
                return residuals(decode(x))
            least_squares(local_residual,encode(best_params),bounds=(np.zeros(len(PARAM_KEYS)),np.ones(len(PARAM_KEYS))),max_nfev=60,x_scale='jac',ftol=1e-7,xtol=1e-7,gtol=1e-7)
            # Không bao giờ thay bộ hiện tại bằng bộ có NSE thấp hơn.
            self._worker_queue.put(('done',signature,best_params,float(best_nse),converged==runs,
                f'{time.perf_counter()-started:.1f} giây; {evaluations} phép mô phỏng, dùng lại {cache_hits} kết quả; đã chạy {runs} lần; {converged} lần đạt điều kiện hội tụ, {runs-converged} lần hết giới hạn thế hệ.'))
        except CalibrationStopped:
            self._worker_queue.put(('done',signature,best_params,float(best_nse),False,'Đã dừng theo yêu cầu; giữ bộ tốt nhất đã đánh giá.'))
        except Exception as exc:self._worker_queue.put(('error',str(exc)))

    def _poll_worker(self):
        try:
            result=self._worker_queue.get_nowait()
            while result[0]=='progress':
                try:result=self._worker_queue.get_nowait()
                except queue.Empty:break
        except queue.Empty:self.root.after(100,self._poll_worker);return
        if result[0]=='progress':
            self.lbl_calib_status.config(text=result[1])
            if len(result)>2:self.progress_bar.config(value=result[2])
            self.root.after(100,self._poll_worker);return
        self._busy=False;self.progress_bar.stop();self.progress_bar.config(value=self.progress_bar['value'] if self._stop_event.is_set() else 100 if result[0]=='done' else 0);self.btn_calibrate.config(state=tk.NORMAL);self.btn_stop.config(state=tk.DISABLED)
        if result[0]=='error':
            self.lbl_calib_status.config(text='Hiệu chỉnh thất bại.')
            messagebox.showerror('Hiệu chỉnh',result[1]);return
        _,signature,params,nse,success,reason=result
        if signature!=self._signature():
            self.lbl_calib_status.config(text='Đầu vào đã thay đổi: bỏ kết quả hiệu chỉnh cũ.');return
        self.best_params=params
        if np.isfinite(nse):
            self._parameter_source=self._active_basin_id;self._independent_metrics=None
            if self._active_basin_id:
                record=self._basins[self._active_basin_id];record['validation_results']={};record['validation_source']=None;record['validation_params']=None
            self._calibrated_params=params.copy();self._calibrated_area=self._settings()[0];self._calibrated_discharge_mode=self._discharge_mode()
            _,_,warm,split,_=self._settings();end=warm+int((len(self.df_data)-warm)*split)
            axis=series_axis(self.df_data)
            if end>warm:
                values=self.df_data[axis].iloc[warm:end]
                self._calibration_period=dict(axis=axis,start=str(values.iloc[0]),end=str(values.iloc[-1]))
        self._update_parameter_display();self._recompute_and_plot()
        self.lbl_calib_status.config(text=f'NSE hiệu chỉnh = {nse:.3f}; '+reason,foreground='green' if success else '#b05b00')

    def _recompute_and_plot(self):
        self._refresh_inputs()
        if self.df_data is None:
            messagebox.showwarning('Dữ liệu',self.lbl_data_status.cget('text'));return
        self.current_sim=None
        try:
            area,dt,warm,split,initial=self._settings()
            df=merge_series(self.input_series,dt,*self._period()) if self.input_series else validate_data(self.df_data,dt)
            if warm>=len(df):raise ValueError('Thời gian khởi động phải ngắn hơn chuỗi dữ liệu.')
            rain=df['Mua_mm'].to_numpy();pet=df['BocHoi_mm'].to_numpy();q_obs=df['Q_ThucDo_m3s'].to_numpy()
            if self.validation_mode and not np.isfinite(compute_nse(q_obs[warm:],np.zeros(len(q_obs)-warm))):
                raise ValueError('Kiểm định cần ít nhất 2 Q thực đo sau khởi động và phương sai khác 0.')
            forbidden=getattr(self,'_validation_forbidden_period',None)
            if self.validation_mode and forbidden is not None and forbidden['axis']=='ThoiGian' and series_axis(df)==forbidden['axis']:
                values=df[forbidden['axis']].iloc[warm:]
                low=pd.Timestamp(forbidden['start']) if forbidden['axis']=='ThoiGian' else float(forbidden['start'])
                high=pd.Timestamp(forbidden['end']) if forbidden['axis']=='ThoiGian' else float(forbidden['end'])
                if ((values>=low)&(values<=high)).any():raise ValueError('Thời đoạn kiểm định trùng thời đoạn hiệu chỉnh. Chọn khoảng độc lập hoặc nhập chuỗi mới có thời gian đúng.')
            res=run_nam(self.best_params,area,rain,pet,dt,initial,use_acceleration=NUMBA_AVAILABLE and bool(_nam_kernel.signatures),discharge_mode=self._discharge_mode())
        except Exception as exc:messagebox.showerror('Mô phỏng',str(exc));return
        self.current_sim=res;self._result_signature=self._signature()
        self._run_settings=dict(area=area,dt=dt,warm=warm,split=split,initial=initial,params=self.best_params.copy())
        q_sim=res['Q_sim'];end=warm+int((len(df)-warm)*split)
        train=compute_metrics(q_obs[warm:end],q_sim[warm:end]);validation=compute_metrics(q_obs[end:],q_sim[end:])
        metric=compute_metrics(q_obs[warm:],q_sim[warm:])
        if self.validation_mode and hasattr(self,'_validation_callback'):
            self._independent_metrics={key:float(value) if np.isfinite(value) else None for key,value in metric.items()}
            self._validation_callback(metric,self.best_params.copy(),self._period())
        elif self._active_basin_id:
            if self._parameter_source==self._active_basin_id and self._calibrated_params is not None:
                self._basins[self._active_basin_id]['calibration_metrics']={key:float(value) if np.isfinite(value) else None for key,value in train.items()}
            self._capture_active_basin();self._update_basins_table()
        fmt=lambda v:f'{v:.3f}' if np.isfinite(v) else 'không xác định'
        self.lbl_metric_nse.config(text=f'NSE hiệu chỉnh: {fmt(train["nse"])} | kiểm định: {fmt(validation["nse"])}')
        if self._active_basin_id and self._parameter_source!=self._active_basin_id and not self.validation_mode:
            self.lbl_metric_nse.config(text=f'NSE mô phỏng: {fmt(metric["nse"])} — {metric["n"]} điểm thực đo')
        if self.validation_mode:self.lbl_metric_nse.config(text=f'NSE kiểm định độc lập: {fmt(metric["nse"])} — {metric["n"]} điểm thực đo')
        self.lbl_metric_peak.config(text=f'Đỉnh Q đo/mô phỏng: {fmt(metric["observed_peak"])}/{fmt(metric["simulated_peak"])} m³/s')
        self.lbl_metric_pbias.config(text=f'PBIAS (đo−mô phỏng): {fmt(metric["pbias"])}%')
        self.lbl_calib_status.config(text=f'Sai số cân bằng lớn nhất: {np.max(np.abs(res["Balance_error_mm"])):.2e} mm; loại {warm} bước khởi động.')
        self.ax_rain.clear();self.ax_flow.clear();self.ax_volume.clear()
        dated='ThoiGian' in df
        time=mdates.date2num(pd.to_datetime(df['ThoiGian']).to_numpy()) if dated else np.arange(len(rain))*dt
        step=dt/24 if dated else dt
        if dated:
            self.ax_flow.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3,maxticks=6))
            self.ax_flow.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y\n%H:%M'))
        else:
            self.ax_flow.xaxis.set_major_locator(AutoLocator());self.ax_flow.xaxis.set_major_formatter(ScalarFormatter())
        self.ax_rain.tick_params(axis='x',labelbottom=False)
        self.ax_flow.tick_params(axis='x',labelbottom=False)
        self.ax_rain.bar(time,rain,width=step*.8,color='#1f77b4',label='Mưa tổng mỗi bước (mm)')
        self.ax_rain.set_ylabel('Mưa (mm)');self.ax_rain.set_ylim(max(10.,rain.max()*1.3),0);self.ax_rain.legend(fontsize=8)
        self.ax_rain.set_title('MƯA – DÒNG CHẢY NAM (DÒNG TRÀN ĐIỀU TIẾT BIẾN ĐỔI)',fontsize=10)
        self.ax_flow.plot(time,q_obs,'k--',label='Lưu lượng thực đo')
        self.ax_flow.plot(time,q_sim,'r-',label='Lưu lượng mô phỏng '+('cuối bước' if res['Discharge_mode']=='endpoint' else 'trung bình bước'))
        self.ax_flow.stackplot(time,res['Q_base'],res['Q_inter'],res['Q_surf'],labels=['Dòng ngầm','Dòng sát mặt','Dòng tràn'],alpha=.25)
        if warm:self.ax_flow.axvspan(time[0],time[warm],color='gray',alpha=.2,label='Khởi động (không đánh giá)')
        if end<len(df) and (self._active_basin_id is None or self._parameter_source==self._active_basin_id):self.ax_flow.axvline(time[end],color='navy',linestyle=':',label='Bắt đầu kiểm định')
        self.ax_flow.set(ylabel='Lưu lượng (m³/s)',xlim=(time[0]-step*.5,time[-1]+step*.5))
        self.ax_flow.set_ylim(bottom=0);self.ax_flow.grid(alpha=.3);self.ax_flow.legend(fontsize=8)
        volume=cumulative_water_volume(q_obs,res['Q_sim_mean'],dt,res['Discharge_mode'])
        if volume['valid'].any():
            self.ax_volume.plot(time,volume['observed_m3']/1e6,'k--',label='Thực đo tích lũy')
            self.ax_volume.plot(time,volume['simulated_m3']/1e6,'r-',label='Mô phỏng tích lũy')
            measured=volume['observed_total_m3'];computed=volume['simulated_total_m3']
            difference=100*(computed-measured)/measured if measured>0 else np.nan
            note=f'Tổng đo / tính: {measured/1e6:.3f} / {computed/1e6:.3f} triệu m³; chênh lệch: {fmt(difference)}%'
            self.ax_volume.legend(fontsize=8,loc='upper left')
        else:
            self.ax_volume.plot(time,np.cumsum(res['Q_sim_mean'])*dt*3600/1e6,'r-',label='Mô phỏng tích lũy')
            self.ax_volume.legend(fontsize=8,loc='upper left')
            note='Chưa đủ lưu lượng thực đo để so sánh tổng lượng.'
        self.ax_volume.set_title('TỔNG LƯỢNG NƯỚC TOÀN THỜI ĐOẠN\n'+note,fontsize=8)
        self.ax_volume.set(xlabel='Ngày/tháng/năm – giờ:phút' if dated else 'Thời gian từ bước đầu (giờ)',ylabel='Tích lũy (triệu m³)')
        self.ax_volume.set_ylim(bottom=0);self.ax_volume.grid(alpha=.3)
        if volume['valid'].any():
            rule='Q tức thời: tích phân hình thang giữa hai điểm liên tiếp.' if res['Discharge_mode']=='endpoint' else 'Q trung bình: tổng Q × Δt.'
            self.ax_volume.text(1,.02,rule+' Chỉ so sánh khoảng đủ Q đo.',transform=self.ax_volume.transAxes,ha='right',fontsize=7)
        self.fig.tight_layout();self.canvas.draw()

    def _collect_basin_discharge(self,basin_ids):
        """Run an isolated project copy; keep the visible model and fit unchanged."""
        payload=json.loads(self._project_text())
        window=tk.Toplevel(self.root);window.withdraw()
        try:
            worker=NAMDesktopApp(window)
            worker._apply_project(payload,worker._decode_project(payload))
            tables=[];metadata=[];wide=[];axes=[];steps=[]
            for basin_id in basin_ids:
                if basin_id not in worker._basins:raise ValueError('Lưu vực không tồn tại: '+basin_id)
                worker._activate_basin(basin_id)
                record=worker._basins[basin_id]
                if worker.df_data is None:raise ValueError(record['name']+': '+worker.lbl_data_status.cget('text'))
                area,dt,warm,split,initial=worker._settings()
                df=merge_series(worker.input_series,dt,*worker._period())
                if warm>=len(df):raise ValueError(record['name']+': thời gian khởi động phải ngắn hơn chuỗi dữ liệu.')
                result=run_nam(worker.best_params,area,df.Mua_mm.to_numpy(),df.BocHoi_mm.to_numpy(),dt,initial,discharge_mode=worker._discharge_mode())
                axis=series_axis(df);axes.append(axis);steps.append(dt)
                out=df[[axis]].copy()
                out['MaLuuVuc']=basin_id;out['TenLuuVuc']=record['name']
                out['BuocGio']=dt;out['KhoiDong']=np.arange(len(df))<warm
                out['Q_TinhToan_m3s']=result['Q_sim']
                out['Q_TrungBinhBuoc_m3s']=result['Q_sim_mean'];out['Q_CuoiBuoc_m3s']=result['Q_sim_endpoint']
                for key,label in [('Q_surf','TranMat'),('Q_inter','SatMat'),('Q_base','Ngam')]:out['Q_'+label+'_m3s']=result[key]
                tables.append(out)
                wide.append(pd.Series(result['Q_sim'],index=pd.Index(df[axis],name=axis),name=basin_id+' — '+record['name']))
                metadata.append(dict(MaLuuVuc=basin_id,TenLuuVuc=record['name'],DienTich_km2=area,BuocGio=dt,BatDau=str(df[axis].iloc[0]),KetThuc=str(df[axis].iloc[-1]),LoaiLuuLuong=result['Discharge_mode'],NguonBoThongSo=record.get('parameter_source') or '',**worker.best_params,**initial))
            if not tables:raise ValueError('Chọn ít nhất một lưu vực.')
            # Missing times remain blank; overlapping/nested basins are never summed.
            aligned=pd.concat(wide,axis=1).sort_index().reset_index() if len(set(axes))==1 and (axes[0]=='ThoiGian' or len(set(steps))==1) else None
            return pd.concat(tables,ignore_index=True),pd.DataFrame(metadata),aligned
        finally:window.destroy()

    def _export_basins_dialog(self):
        if not self._project_idle():return
        if not self._basins:
            messagebox.showinfo('Trích lưu lượng','Chuyển các lưu vực từ bản đồ sang NAM trước khi trích kết quả.',parent=self.root);return
        window=tk.Toplevel(self.root);window.title('Trích lưu lượng các lưu vực')
        ttk.Label(window,text='Chọn lưu vực cần trích. Chạy với thông số và thời đoạn riêng đã thiết lập; không dò lại thông số.',wraplength=520).pack(fill='x',padx=10,pady=8)
        choices=ttk.Treeview(window,columns=('name',),show='headings',selectmode='extended',height=12)
        choices.heading('name',text='Lưu vực (Ctrl / Shift để chọn nhiều)');choices.column('name',width=520)
        scroll=ttk.Scrollbar(window,orient='vertical',command=choices.yview);choices.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');choices.pack(fill='both',expand=True,padx=10)
        for bid in self._basins:choices.insert('', 'end',iid=bid,values=(self._basin_display(bid),))
        choices.selection_set(list(self._basins))
        def export():
            if not self._project_idle():return
            selected=choices.selection()
            if not selected:messagebox.showwarning('Trích lưu lượng','Chọn ít nhất một lưu vực.',parent=window);return
            path=filedialog.asksaveasfilename(parent=window,defaultextension='.xlsx',filetypes=[('Excel','*.xlsx')])
            if not path:return
            temporary=None
            try:
                detail,info,aligned=self._collect_basin_discharge(selected)
                with tempfile.NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(path)),suffix='.xlsx',delete=False) as handle:temporary=handle.name
                with pd.ExcelWriter(temporary,engine='openpyxl',datetime_format='dd/mm/yyyy hh:mm:ss') as writer:
                    sheets={'Luu luong chi tiet':detail,'Thong tin luu vuc':info}
                    if aligned is not None:sheets['So sanh luu luong']=aligned
                    for name,table in sheets.items():
                        table.to_excel(writer,sheet_name=name,index=False)
                        sheet=writer.sheets[name];sheet.freeze_panes='B2';sheet.auto_filter.ref=sheet.dimensions
                        for column in sheet.columns:
                            sheet.column_dimensions[column[0].column_letter].width=25
                            for cell in column[1:]:
                                if isinstance(cell.value,(datetime,pd.Timestamp)):cell.number_format='dd/mm/yyyy hh:mm:ss'
                                elif isinstance(cell.value,(int,float)) and not isinstance(cell.value,bool):cell.number_format='0.000'
                os.replace(temporary,path);temporary=None
                messagebox.showinfo('Trích lưu lượng',f'Đã xuất {len(selected)} lưu vực. Các ô thiếu thời điểm giữ trống; không cộng lưu lượng các lưu vực.',parent=window)
            except Exception as exc:messagebox.showerror('Trích lưu lượng',str(exc),parent=window)
            finally:
                if temporary is not None:os.unlink(temporary)
        ttk.Button(window,text='Xuất lưu lượng ra Excel',command=export).pack(fill='x',padx=10,pady=8)

    def _export_csv(self):
        if self.df_data is None:return
        # Tính lại từ đầu vào hiện tại, tránh xuất kết quả cũ với bước giờ mới.
        self._recompute_and_plot()
        if self.current_sim is None:return
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        try:
            out=self.df_data.copy();res=self.current_sim;settings=self._run_settings;dt=settings['dt']
            out['Gio']=np.arange(len(out))*dt
            for column,key in [('Q_MoPhong_m3s','Q_sim'),('Q_TranMat_m3s','Q_surf'),('Q_SatMat_m3s','Q_inter'),('Q_Ngam_m3s','Q_base'),('BocHoiThuc_mm','Evap_actual_mm'),('TruLuong_mm','Storage_mm'),('SaiSoCanBang_mm','Balance_error_mm'),('CK_TranMat_NhoNhat_gio','CK_overland_min_hours')]:out[column]=res[key]
            end=settings['warm']+int((len(out)-settings['warm'])*settings['split'])
            out['GiaiDoan']=['Khoi_dong' if i<settings['warm'] else 'Kiem_dinh_doc_lap' if self.validation_mode else 'Mo_phong' if self._active_basin_id and self._parameter_source!=self._active_basin_id else 'Hieu_chinh' if i<end else 'Kiem_dinh' for i in range(len(out))]
            out['DienTich_km2']=settings['area'];out['BuocGio']=dt
            out['MaLuuVuc']=self._active_basin_id or ''
            out['TenLuuVuc']=self._basins.get(self._active_basin_id,{}).get('name','')
            out['NguonBoThongSo']=self._parameter_source or ''
            for i,(name,item) in enumerate(self._evap_stations.items(),1):
                out[f'BocHoi_Tram_{i}_Ten']=name;out[f'BocHoi_Tram_{i}_TrongSo']=item['weight']
            out['LoaiLuuLuongDanhGia']=res['Discharge_mode']
            out['Q_TrungBinhBuoc_m3s']=res['Q_sim_mean']
            out['Q_CuoiBuoc_m3s']=res['Q_sim_endpoint']
            volume=cumulative_water_volume(out['Q_ThucDo_m3s'],res['Q_sim_mean'],dt,res['Discharge_mode'])
            out['TongLuong_ThucDo_TichLuy_m3']=volume['observed_m3']
            out['TongLuong_MoPhong_CungKhoang_TichLuy_m3']=volume['simulated_m3']
            out['KhoangDuQuanTrac_TongLuong']=volume['valid']
            out['TongLuong_MoPhong_ToanKy_TichLuy_m3']=np.cumsum(res['Q_sim_mean'])*dt*3600.
            for component,label in [('Q_surf','TranMat'),('Q_inter','SatMat'),('Q_base','Ngam')]:
                out[f'Q_{label}_TrungBinhBuoc_m3s']=res[component+'_mean']
                out[f'Q_{label}_CuoiBuoc_m3s']=res[component+'_endpoint']
            out['PhienBanMoHinh']=MODEL_VERSION
            out['BoTinh']=res.get('Engine','Python')
            out['TruLuongDau_mm']=res['Initial_storage_mm']
            out['BatDauYeuCau'],out['KetThucYeuCau']=self._period()
            out['Q_NgoaiKhoang_KhongDung']=self.df_data.attrs.get('outside_Q_count',0)
            out['GhiChuNhapBocHoi']='; '.join(self.input_series.get('BocHoi_mm',pd.DataFrame()).attrs.get('import_notes',[]))
            out['GhiChuNhapQ']='; '.join(self.input_series.get('Q_ThucDo_m3s',pd.DataFrame()).attrs.get('import_notes',[]))
            for i,(name,item) in enumerate(self.rain_stations.items(),1):
                out[f'Tram_{i}_Ten']=name;out[f'Tram_{i}_TrongSo']=item['weight']
                out[f'Tram_{i}_GhiChuNhap']='; '.join(item['data'].attrs.get('import_notes',[]))
                out[f'Tram_{i}_Mua_mm']=item['data'].set_index(series_axis(item['data']))['Mua_mm'].reindex(out[series_axis(item['data'])]).to_numpy()
            for key,value in settings['params'].items():out[key]=value
            for key,value in settings['initial'].items():out['BanDau_'+key]=value
            out.to_csv(path,index=False,encoding='utf-8-sig')
            messagebox.showinfo('Xuất kết quả','Đã xuất lưu lượng, cân bằng nước, giai đoạn đánh giá và thông số.')
        except Exception as exc:messagebox.showerror('Xuất kết quả',str(exc))


# ==============================================================================
# ĐIỂM BẮT ĐẦU CHƯƠNG TRÌNH
# ==============================================================================
if __name__ == "__main__":
    app_root = tk.Tk()
    app = NAMDesktopApp(app_root)
    app_root.mainloop()
