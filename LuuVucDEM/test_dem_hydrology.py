import unittest, tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
if not hasattr(np,"in1d"): np.in1d=np.isin
from affine import Affine
from pysheds.grid import Grid
from pysheds.sview import Raster, ViewFinder
import rasterio
from LuuVucDEM.dem_hydrology import *
class DemTests(unittest.TestCase):
 def setUp(self):self.transform=Affine(10,0,500000,0,-10,2300000)
 def raster(self,data,nodata=-9999):return Raster(np.asarray(data,dtype=float),viewfinder=ViewFinder(affine=self.transform,shape=np.shape(data),nodata=nodata,crs=CRS.from_epsg(32648)))
 def network(self):
  dem=self.raster([[40,40,40],[30,30,30],[20,20,20]])
  directions=np.array([[2,4,8],[2,4,8],[1,0,16]])
  return dem,directions,np.array([[1,1,1],[1,4,1],[1,9,1]])
 def test_planar_slope_with_nodata(self):
  data=np.indices((5,6));z=data[1]*20+data[0]*30;valid=np.ones(z.shape,bool);valid[2,2]=False
  slope=terrain_slope(z,valid,10,10)
  np.testing.assert_allclose(slope[valid],np.sqrt(13)*1000)
 def test_area_main_branch_budget(self):
  dem,fdir,acc=self.network();r=measure_basin(np.ones((3,3),bool),dem,fdir,acc,(2,1),self.transform,1)
  self.assertAlmostEqual(r['DienTich'],.0009)
  self.assertAlmostEqual(r['Dai_SC'],(np.sqrt(200)+10)/1000)
  total=sum(np.hypot(dc*10,dr*10) for code in fdir.flat if code in D8 for dr,dc in [D8[code]])
  self.assertAlmostEqual((r['Dai_SC']+r['Dai_SNhanh'])*1000,total)
  self.assertAlmostEqual(r['Doc_SC_pm'],20/(np.sqrt(200)+10)*1000)
  self.assertAlmostEqual(sum(g.length for g in r['branches']),r['Dai_SNhanh']*1000)
 def test_snap_uses_full_five_by_five_window(self):
  acc=np.ones((7,7));acc[5,5]=100
  self.assertEqual(snap_outlet(*(self.transform*(3.5,3.5)),self.transform,acc,np.ones((7,7),bool)),(5,5))
 def test_snap_rejects_outside_and_nodata(self):
  with self.assertRaises(ValueError):snap_outlet(*(self.transform*(-1,0)),self.transform,np.ones((3,3)),np.ones((3,3),bool))
  with self.assertRaises(ValueError):snap_outlet(*(self.transform*(1,1)),self.transform,np.ones((3,3)),np.zeros((3,3),bool))
 def test_no_stream_is_unknown_not_zero_elevation(self):
  dem,fdir,acc=self.network();r=measure_basin(np.ones((3,3)),dem,fdir,acc,(2,1),self.transform,100)
  self.assertTrue(np.isnan(r['Z_Nguon']));self.assertEqual(r['Z_CuaXa'],20);self.assertTrue(np.isnan(r['Doc_SC_pm']))
 def test_nodata_excluded(self):
  dem,fdir,acc=self.network();dem[0,0]=-9999
  r=measure_basin(np.ones((3,3)),dem,fdir,acc,(2,1),self.transform,1)
  self.assertAlmostEqual(r['DienTich'],.0008)
 def test_nested_catchments_independent(self):
  dem,fdir,acc=self.network()
  upper=catchment_d8(fdir,np.ones(fdir.shape,bool),(1,1));lower=catchment_d8(fdir,np.ones(fdir.shape,bool),(2,1))
  results=[]
  for outlet,mask in [((1,1),upper),((2,1),lower)]:results.append(measure_basin(mask,dem,fdir,acc,outlet,self.transform,1))
  self.assertAlmostEqual(results[0]['DienTich'],.0004);self.assertAlmostEqual(results[1]['DienTich'],.0009)
  reverse=measure_basin(lower,dem,fdir,acc,(2,1),self.transform,1)
  self.assertEqual(reverse['DienTich'],results[1]['DienTich'])
 def test_cycle_does_not_hang_or_count_disconnected_edges(self):
  dem,fdir,acc=self.network();fdir[0,0]=1;fdir[0,1]=16
  r=measure_basin(np.ones((3,3)),dem,fdir,acc,(2,1),self.transform,1)
  self.assertGreater(r['Dai_SC'],0)
 def test_negative_drop_not_hidden(self):
  dem,fdir,acc=self.network();dem[2,1]=100
  r=measure_basin(np.ones((3,3)),dem,fdir,acc,(2,1),self.transform,1)
  self.assertLess(r['Doc_SC_pm'],0)
 def test_metric_conversion_and_unknown_crs(self):
  with tempfile.TemporaryDirectory() as d:
   for name,crs,aff in [('geo',4326,Affine(.001,0,105,0,-.001,21)),('missing',None,self.transform),('metric',32648,self.transform)]:
    source=Path(d)/(name+'.tif');target=Path(d)/(name+'-metric.tif')
    with rasterio.open(source,'w',driver='GTiff',height=10,width=10,count=1,dtype='float32',transform=aff,crs=crs,nodata=-9999) as dst:dst.write(np.ones((10,10),dtype='float32'),1)
    if crs is None:
     with self.assertRaises(ValueError):metric_dem(source,target)
    else:
     output=metric_dem(source,target)
     with rasterio.open(output) as dst:self.assertTrue(CRS(dst.crs).is_projected);self.assertAlmostEqual(CRS(dst.crs).axis_info[0].unit_conversion_factor,1)
 def test_pit_conditioning_flow_and_conservation(self):
  data=100-np.indices((9,9))[0]*2+abs(np.indices((9,9))[1]-4)
  data=data.astype(float);data[3,4]-=10
  dem=self.raster(data);grid=Grid(viewfinder=dem.viewfinder)
  conditioned=grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem)))
  fdir=grid.flowdir(conditioned);acc=grid.accumulation(fdir)
  outlet=np.unravel_index(np.argmax(acc),acc.shape)
  catch=catchment_d8(fdir,np.ones(fdir.shape,bool),outlet)
  self.assertEqual(int(np.sum(catch)),int(acc[outlet]))
  r=measure_basin(catch,dem,fdir,acc,outlet,self.transform,1)
  self.assertAlmostEqual(r['DienTich'],np.sum(catch)*.0001)
if __name__=='__main__':unittest.main(verbosity=2)
