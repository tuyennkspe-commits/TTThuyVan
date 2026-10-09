import importlib.util, unittest
from unittest.mock import patch
import numpy as np
from scipy.stats import pearson3, gumbel_r, skew
spec=importlib.util.spec_from_file_location('tstv',str(__import__('pathlib').Path(__file__).with_name('TSTV-2026-V1-GiaoDien.py')));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Var:
 def __init__(self,x):self.x=x
 def get(self):return self.x
class Checks(unittest.TestCase):
 def setUp(self):
  self.app=m.TSTVAdvancedApp.__new__(m.TSTVAdvancedApp)
  self.app.sorted_data=np.array([2.,3.,4.,6.,9.,12.])
  self.app.dist_var=Var('PEARSON III');self.app.method_var=Var(1)
 def test_skew(self):
  mean,sd,cs=self.app.sample_moments(self.app.sorted_data)
  self.assertAlmostEqual(cs,skew(self.app.sorted_data,bias=False))
 def test_pearson_zero_skew(self):
  np.testing.assert_allclose(self.app.calculate_xp([5,50,95],10,.3,0,'PEARSON III'),pearson3.isf([.05,.5,.95],0,loc=10,scale=3))
 def test_gumbel(self):
  beta=3*np.sqrt(6)/np.pi
  np.testing.assert_allclose(self.app.calculate_xp([5,50,95],10,.3,7,'GUMBEL'),gumbel_r.isf([.05,.5,.95],loc=10-np.euler_gamma*beta,scale=beta))
 def test_log_moments(self):
  self.app.dist_var.x='LOG-PEARSON III'
  mean,sd,cs,*_=self.app.get_distribution_parameters()
  y=np.log10(self.app.sorted_data)
  self.assertAlmostEqual(mean,y.mean());self.assertAlmostEqual(sd,y.std(ddof=1))
  np.testing.assert_allclose(self.app.calculate_xp([5,50,95],mean,sd,cs,'LOG-PEARSON III'),10**pearson3.isf([.05,.5,.95],skew(y,bias=False),loc=y.mean(),scale=y.std(ddof=1)))
 def test_log_fit_uses_every_parameter(self):
  self.app.dist_var.x='LOG-PEARSON III';self.app.method_var.x=2
  self.app.ent_fit_xbq=Var('1,2');self.app.ent_fit_cv=Var('.25');self.app.ent_fit_cs=Var('0')
  result=self.app.get_distribution_parameters()
  self.assertEqual(result[:3],(1.2,.25,0))
  self.assertAlmostEqual(float(self.app.calculate_xp(50,*result[:3],result[3])),10**1.2)
 def test_three_points_all_distributions(self):
  for dist,mean,spread,cs in [('PEARSON III',10,.25,.7),('LOG-PEARSON III',1.2,.3,.7),('GUMBEL',10,.25,1.1395)]:
   points=self.app.calculate_xp([5,50,95],mean,spread,cs,dist)
   self.app.dist_var.x=dist;self.app.method_var.x=3
   self.app.ent_x5,self.app.ent_x50,self.app.ent_x95=(Var(str(x)) for x in points)
   result=self.app.get_distribution_parameters();self.assertIsNotNone(result,dist)
   np.testing.assert_allclose(self.app.calculate_xp([5,50,95],*result[:3],dist),points,rtol=1e-4)
 def test_invalid_log_never_discards_rows(self):
  self.app.dist_var.x='LOG-PEARSON III';self.app.sorted_data=np.array([0.,1.,2.,3.])
  with patch.object(m.messagebox,'showerror') as error:
   self.assertIsNone(self.app.get_distribution_parameters());self.assertTrue(error.called)
 def test_constant_series(self):
  self.app.sorted_data=np.ones(5)*5
  result=self.app.get_distribution_parameters()
  np.testing.assert_allclose(self.app.calculate_xp([5,50,95],*result[:3],result[3]),5)
 def test_probability_domain(self):
  for p in (0,100,np.nan):
   with self.assertRaises(ValueError):self.app.calculate_xp(p,5,.2,0,'PEARSON III')
 def test_plotting_positions(self):
  self.app.cbo_formula=type('Combo',(),{'current':lambda _:2})()
  ranks,prob,name=self.app.get_empirical_probabilities()
  np.testing.assert_allclose(prob,(ranks-.5)/6*100);self.assertIn('Hazen',name)
if __name__=='__main__':unittest.main(verbosity=2)
