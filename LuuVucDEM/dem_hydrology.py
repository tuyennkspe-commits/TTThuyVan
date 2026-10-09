"""Metric D8 catchment measurements. Elevation must be supplied in metres."""
import numpy as np
from shapely.geometry import shape, LineString
from shapely.ops import unary_union
from rasterio.features import shapes
from pyproj import CRS, Transformer
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
D8={64:(-1,0),128:(-1,1),1:(0,1),2:(1,1),4:(1,0),8:(1,-1),16:(0,-1),32:(-1,-1)}

def metric_dem(source, destination):
    """Reject unknown CRS; warp non-metric/geographic/rotated grids to local UTM."""
    with rasterio.open(source) as src:
        if src.crs is None: raise ValueError('DEM thiếu hệ tọa độ; phải khai báo đúng CRS trước khi xử lý.')
        band=src.read(1,masked=True).astype(float)
        if np.any(~np.isfinite(band.compressed())):
            raise ValueError('DEM có cao độ NaN/vô cực chưa khai báo NoData.')
        crs=CRS(src.crs)
        metric=crs.is_projected and all(abs(a.unit_conversion_factor-1)<1e-9 for a in crs.axis_info[:2])
        if metric and src.transform.b==0 and src.transform.d==0 and src.transform.a>0 and src.transform.e<0:
            if np.any(np.ma.getmaskarray(band)):
                profile=src.profile.copy();profile.update(dtype='float64',nodata=-999999.0,count=1)
                with rasterio.open(destination,'w',**profile) as dst:dst.write(band.filled(-999999.0),1)
                return destination
            return source
        lon,lat=Transformer.from_crs(crs,4326,always_xy=True).transform((src.bounds.left+src.bounds.right)/2,(src.bounds.bottom+src.bounds.top)/2)
        if not -80<=lat<=84: raise ValueError('Ngoài miền UTM; hãy cung cấp DEM chiếu phẳng mét phù hợp.')
        target=CRS.from_epsg((32600 if lat>=0 else 32700)+min(60,max(1,int((lon+180)//6)+1)))
        transform,width,height=calculate_default_transform(src.crs,target,src.width,src.height,*src.bounds)
        profile=src.profile.copy();profile.update(crs=target,transform=transform,width=width,height=height,dtype='float64',nodata=-999999.0,count=1)
        source_data=src.read(1,masked=True).astype(float).filled(-999999.0)
        with rasterio.open(destination,'w',**profile) as dst:
            reproject(source_data,rasterio.band(dst,1),src_transform=src.transform,src_crs=src.crs,src_nodata=-999999.0,dst_transform=transform,dst_crs=target,dst_nodata=-999999.0,resampling=Resampling.bilinear)
    return destination

def valid_dem(dem):
    data=np.asarray(dem,dtype=float)
    valid=np.isfinite(data)
    raster_mask=getattr(dem,'mask',None)
    if raster_mask is not None: valid &= np.asarray(raster_mask,dtype=bool)
    nodata=getattr(dem,'nodata',None)
    if nodata is not None: valid &= data!=nodata
    return data,valid

def snap_outlet(x,y,transform,acc,valid,radius=2):
    c,r=~transform*(x,y);r,c=int(np.floor(r)),int(np.floor(c))
    if not 0<=r<valid.shape[0] or not 0<=c<valid.shape[1]: raise ValueError('Cửa xả nằm ngoài phạm vi DEM.')
    r0,r1=max(0,r-radius),min(valid.shape[0],r+radius+1)
    c0,c1=max(0,c-radius),min(valid.shape[1],c+radius+1)
    local=np.where(valid[r0:r1,c0:c1],np.asarray(acc)[r0:r1,c0:c1],-np.inf)
    if not np.any(np.isfinite(local)): raise ValueError('Không có ô DEM hợp lệ gần cửa xả.')
    best=np.nanmax(local); candidates=np.argwhere(local==best)
    rr,cc=min(candidates,key=lambda rc:(rc[0]+r0-r)**2+(rc[1]+c0-c)**2)
    return int(rr+r0),int(cc+c0)

def terrain_slope(data,valid,dx,dy):
    z=np.where(valid,data,np.nan)
    # Adjacent NoData never treated as an elevation; available one-sided differences at boundaries.
    def derivative(axis,spacing):
        before=np.full_like(z,np.nan);after=before.copy()
        if axis==1: before[:,1:]=z[:,:-1];after[:,:-1]=z[:,1:]
        else: before[1:,:]=z[:-1,:];after[:-1,:]=z[1:,:]
        both=np.isfinite(before)&np.isfinite(after)
        return np.where(both,(after-before)/(2*spacing),np.where(np.isfinite(after),(after-z)/spacing,np.where(np.isfinite(before),(z-before)/spacing,np.nan)))
    return np.hypot(derivative(1,dx),derivative(0,dy))*1000

def measure_basin(mask,dem,fdir,acc,outlet,transform,threshold):
    if int(threshold)!=threshold or threshold<1: raise ValueError('Ngưỡng tạo sông phải là số nguyên dương, tính theo số ô góp nước.')
    data,valid=valid_dem(dem);mask=np.asarray(mask,dtype=bool)&valid
    if not mask[outlet]: raise ValueError('Cửa xả không thuộc lưu vực hợp lệ.')
    dx,dy=abs(transform.a),abs(transform.e)
    if dx<=0 or dy<=0 or transform.b!=0 or transform.d!=0:raise ValueError('Cần lưới thẳng trục với kích thước ô dương.')
    polygons=[shape(g) for g,v in shapes(mask.astype('uint8'),mask=mask,transform=transform,connectivity=4) if v==1]
    polygon=unary_union(polygons)
    slopes=terrain_slope(data,valid,dx,dy)[mask]
    slope=float(np.nanmean(slopes)) if np.any(np.isfinite(slopes)) else np.nan
    streams=(np.asarray(acc)>=threshold)&mask
    edges={}
    for r,c in np.argwhere(streams):
        p=(int(r),int(c))
        if p==outlet:continue
        direction=D8.get(int(fdir[p]))
        if direction is None:continue
        q=(p[0]+direction[0],p[1]+direction[1])
        if 0<=q[0]<mask.shape[0] and 0<=q[1]<mask.shape[1] and mask[q] and streams[q]:
            edges[p]=(q,float(np.hypot(direction[1]*dx,direction[0]*dy)))
    distances={outlet:0.0}
    for source in edges:
        path=[];seen=set();p=source
        while p not in distances and p in edges and p not in seen:
            seen.add(p);path.append(p);p=edges[p][0]
        distance=distances.get(p,np.nan)
        for node in reversed(path):
            distance=distance+edges[node][1];distances[node]=distance
    connected={p:edge for p,edge in edges.items() if np.isfinite(distances.get(p,np.nan))}
    best=max((p for p in connected),key=lambda p:distances[p],default=outlet)
    main_nodes=[best];main_edges=set();p=best
    while p!=outlet:
        main_edges.add(p);p=connected[p][0];main_nodes.append(p)
    def xy(p):return transform*(p[1]+.5,p[0]+.5)
    main=LineString([xy(p) for p in main_nodes]) if len(main_nodes)>1 else None
    branches=[LineString([xy(p),xy(q)]) for p,(q,length) in connected.items() if p not in main_edges]
    length=distances[best] if best!=outlet else 0.0
    source_z=float(data[best]) if main is not None else np.nan
    out_z=float(data[outlet])
    # Negative source-outlet drop is retained: it indicates filled depressions/raw DEM artefacts.
    drop_slope=(source_z-out_z)/length*1000 if length>0 else np.nan
    return dict(geometry=polygon,DienTich=float(mask.sum()*dx*dy/1e6),Doc_LV_pm=slope,Z_Nguon=source_z,Z_CuaXa=out_z,Dai_SC=length/1000,Doc_SC_pm=drop_slope,Dai_SNhanh=sum(e[1] for p,e in connected.items() if p not in main_edges)/1000,main=main,branches=branches)

from numba import njit
@njit(cache=True)
def _catchment_d8(directions, valid, outlet_row, outlet_col):
    rows,cols=directions.shape
    result=np.zeros((rows,cols),dtype=np.bool_)
    stack=np.empty(rows*cols,dtype=np.int64)
    stack[0]=outlet_row*cols+outlet_col;size=1
    result[outlet_row,outlet_col]=True
    drs=(-1,-1,0,1,1,1,0,-1)
    dcs=(0,1,1,1,0,-1,-1,-1)
    incoming=(4,8,16,32,64,128,1,2)
    while size:
        size-=1;index=stack[size];r=index//cols;c=index%cols
        for k in range(8):
            nr=r+drs[k];nc=c+dcs[k]
            if 0<=nr<rows and 0<=nc<cols and valid[nr,nc] and not result[nr,nc] and directions[nr,nc]==incoming[k]:
                result[nr,nc]=True;stack[size]=nr*cols+nc;size+=1
    return result

def catchment_d8(fdir,valid,outlet):
    """Reverse D8 including raster rim cells; do not silently remove boundary contributors."""
    if not valid[outlet]:raise ValueError('Cửa xả nằm trên NoData.')
    return _catchment_d8(np.asarray(fdir),np.asarray(valid,dtype=np.bool_),outlet[0],outlet[1])
