"""Independent HEC-18 (2012) worked examples and numerical boundary checks.

Extract the dependency-free calculation classes so this suite also runs without Tk.
"""
import ast, math, unittest
from pathlib import Path
ns={'math':math,'G':9.81}
p=Path(__file__).resolve().parents[1] / 'TTXoiCau_v4.py';tree=ast.parse(p.read_text())
for name in ['HEC18Tables','HEC18Calculations']:
 n=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==name);exec(compile(ast.Module(body=[n],type_ignores=[]),str(p),'exec'),ns)
C=ns['HEC18Calculations']; ft=.3048
class HECDocumentExamples(unittest.TestCase):
 def test_contraction_example_6_6_1(self):
  r=C.contraction_scour(27300*ft**3,8.6*ft,9.86*ft,322*ft,118.25*ft,.0007,.004,.33*ft,y0=7.1*ft)
  self.assertAlmostEqual(r['y2']/ft,17.2,delta=.15); self.assertAlmostEqual(r['ysc']/ft,10.1,delta=.15)
 def test_simple_pier_7_10_1(self):
  ys,fr=C.pier_scour_csu(10.2*ft,11.02*ft,4*ft,1,1,1.1)
  self.assertAlmostEqual(ys/ft,9.9,delta=.1);self.assertAlmostEqual(fr,.61,delta=.01)
 def test_angle_7_10_2(self):
  k2=C.pier_k2(20,59*ft,4*ft); self.assertAlmostEqual(k2,2.86,delta=.01)
  ys,_=C.pier_scour_csu(10.2*ft,11.02*ft,4*ft,1,k2,1.1);self.assertAlmostEqual(ys/ft,28.3,delta=.3)
 def test_exposed_footing_7_10_3(self):
  r=C.complex_pier(10.2*ft,11.02*ft,4*ft,1,1,1.1,1,False,-.33*ft,5.25*ft,2.5*ft,8*ft,1*ft,4*ft,2,3,3*ft,
   d50_m=.00032,d84_m=.0073,Lpc=65*ft)
  self.assertEqual(r['cap_case'],2)
  self.assertAlmostEqual(r['ys_pier']/ft,.6,delta=.05)
  self.assertAlmostEqual(r['vf']/ft,9.84,delta=.1)
  self.assertAlmostEqual(r['ys_pc']/ft,14.8,delta=.2)
  self.assertAlmostEqual(r['ys_total']/ft,15.4,delta=.2)
 def test_complex_7_10_4(self):
  r=C.complex_pier(51.8*ft,11.2*ft,32*ft,1.1,1,1.1,1,False,25.5*ft,16*ft,8.62*ft,53.25*ft,
   5.5*ft,13.75*ft,3,4,22*ft,d50_m=.00032,d84_m=.0073,Lpc=53.25*ft)
  self.assertAlmostEqual(r['ys_pier']/ft,3.2,delta=.15)
  # Printed example reads approximate chart values .07, .58, 1.16, .79.
  self.assertAlmostEqual(r['ys_pc']/ft,12.8,delta=.9)
  self.assertAlmostEqual(r['ys_pg']/ft,21.24,delta=1.2)
 def test_hire_8_7_2(self):
  r=C.abutment_scour(6.2*ft,9.9*ft,742*ft,.82,110);self.assertAlmostEqual(r['ys']/ft,33.9,delta=.3)
 def test_no_flow_and_integral(self):
  self.assertEqual(C.abutment_scour(2,0,5,1)['ys'],0)
  a=C.wet_segment(0,2,10)[2];b=C.wet_segment(1e-9,2,10)[2];self.assertAlmostEqual(a,b,places=6)
  self.assertAlmostEqual(C.wet_segment(1,2,10)[2],3/8*10*(2**(8/3)-1),places=8)
 def test_km_six_rows_and_skew(self):
  self.assertEqual(C.pile_group_factors(1,2.5,12,4,4,1,3)[1],C.pile_group_factors(1,2.5,6,4,4,1,3)[1])
  self.assertEqual(C.pile_group_factors(1,2.5,12,4,4,1,3,skewed=True)[1],1)
 def test_projected_width_and_roughness(self):
  self.assertAlmostEqual(C.projected_pile_width(1,3,6,4,0),4)
  self.assertGreater(C.projected_pile_width(1,3,6,4,10),4)
  self.assertEqual(C.grain_roughness(.0073),.0073);self.assertAlmostEqual(C.grain_roughness(.0073,'gravel'),.02555)
 def test_q_ratio_y0_and_grain_floor(self):
  r=C.contraction_scour(200,3,5,30,20,.00001,.001,.01,q1=100,y0=2)
  self.assertAlmostEqual(r['y2_lb'],3*2**(6/7)*(30/20)**r['k1'])
  self.assertAlmostEqual(r['dm'],.00025)
  self.assertAlmostEqual(r['ysc'],max(0,r['y2']-2))
 def test_froehlich_8_7_1(self):
  # Imperial input avoids the inconsistent metric ya printed in this example.
  r=C.abutment_scour(3.5*ft,960/262.5*ft,(960/23)*ft,.82,70)
  self.assertEqual(r['method'],'Froehlich')
  self.assertAlmostEqual(r['ys']/ft,13,delta=.3)
 def test_negative_stem_height_figure_7_6(self):
  # Chart includes -1 <= h1/a <= 2; don't silently clamp h1 to zero.
  self.assertAlmostEqual(C.kh_pier_stem(-.5,1,0),.4075+.4271*.5+.1615*.25+.0269*.125)
 def test_invalid_grains_and_pile_counts(self):
  for y,d in [(0,.001),(2,0),(2,-.001)]:
   with self.assertRaises(ValueError): C.critical_velocity_vc(y,d)
  with self.assertRaises(ValueError): C.grain_roughness(0)
  with self.assertRaises(ValueError): C.projected_pile_width(1,3,2.5,4)
 def test_cap_geometry_and_shape_are_independent(self):
  r=C.complex_pier(10,2,2,1,1,1.1,1,False,2,2,1,6,1,3,3,4,4,
      Lpc=40,theta_deg=20,cap_k1=1.1)
  self.assertAlmostEqual(r['k2_pc'],C.pier_k2(20,40,6))
  self.assertEqual(r['k1_pc'],1)
  r=C.complex_pier(10,2,2,1,1,1.1,1,False,-.1,2,1,6,1,3,3,4,4,
      Lpc=40,cap_k1=1.1)
  self.assertEqual(r['k1_pc'],1.1)
 def test_case2_has_no_separate_pile_term(self):
  r=C.complex_pier(3,1,1,1,1,1.1,1,False,-2,3,1,3,1,3,3,4,4)
  self.assertEqual(r['cap_case'],2)
  self.assertEqual(r['ys_pg'],0)
  self.assertAlmostEqual(r['ys_total'],r['ys_pier']+r['ys_pc'])
 def test_live_bed_armoring_is_explicit(self):
  # Coarse grains alone do not imply a confirmed armoring condition.
  r=C.contraction_scour(100,3,20,100,10,.02,.001,.1)
  self.assertAlmostEqual(r['y2'],r['y2_lb'])
  a=C.contraction_scour(100,3,20,100,10,.02,.001,.1,armored=True)
  self.assertAlmostEqual(a['y2'],min(a['y2_lb'],a['y2_cw']))
 def test_initial_exposure_all_elevation_cases(self):
  self.assertEqual(C.foundation_exposure(0,-5,2,5)['state'],'Bệ và cọc còn chôn')
  self.assertEqual(C.foundation_exposure(0,-2,2,5)['state'],'Bệ và cọc còn chôn')
  self.assertEqual(C.foundation_exposure(0,-1,2,5)['state'],'Lộ bệ')
  self.assertEqual(C.foundation_exposure(0,0,2,5)['state'],'Lộ bệ')
  self.assertEqual(C.foundation_exposure(0,1,2,5)['state'],'Lộ bệ & cọc')
  self.assertEqual(C.foundation_exposure(0,1,2,.5)['state'],'Lộ cọc (bệ ngoài nước)')
  self.assertEqual(C.foundation_exposure(0,1,2,5,has_piles=False)['state'],'Lộ bệ')
  self.assertEqual(C.foundation_exposure(0,1,2,5,has_cap=False)['state'],'Trụ không có bệ')
 def test_deep_buried_cap_does_not_reduce_stem_or_require_d84(self):
  expected,_=C.pier_scour_csu(5,.1,1,1,1,1.1)
  r=C.complex_pier(5,.1,1,1,1,1.1,1,False,-20,2,1,3,1,3,3,4,4,d84_m=0)
  self.assertEqual(r['cap_case'],0)
  self.assertAlmostEqual(r['ys_total'],expected)
  self.assertEqual(r['ys_pc'],0);self.assertEqual(r['ys_pg'],0)
 def test_no_cap_and_no_piles_are_structural_flags(self):
  r=C.complex_pier(5,1,1,1,1,1.1,1,False,1,2,1,3,1,3,3,4,4,has_cap=False,d84_m=0)
  self.assertEqual(r['cap_case'],0);self.assertEqual(r['ys_pc'],0)
  r=C.complex_pier(5,1,1,1,1,1.1,1,False,1,2,1,3,1,3,3,4,4,pile_exposed=False)
  self.assertEqual(r['cap_case'],1);self.assertEqual(r['ys_pg'],0)
 def test_exposure_changes_after_lowering_bed(self):
  self.assertEqual(C.foundation_exposure(0,-1,2,5)['state'],'Lộ bệ')
  self.assertEqual(C.foundation_exposure(-2,-1,2,5)['state'],'Lộ bệ & cọc')
 def test_ppll_interval_partial_segments_and_conservation(self):
  total=C.blocked_flow_from_segments([2,2,2],[0,10,10],1,0,20)
  part=C.blocked_flow_from_segments([2,2,2],[0,10,10],1,2,7)
  self.assertAlmostEqual(part['Ae'],10);self.assertAlmostEqual(part['L_prime'],5)
  self.assertAlmostEqual(part['ya'],2);self.assertAlmostEqual(part['Qe'],total['Qe']/4)
  a=C.blocked_flow_from_segments([2,2,2],[0,10,10],1,0,12)
  b=C.blocked_flow_from_segments([2,2,2],[0,10,10],1,12,20)
  self.assertAlmostEqual(a['Qe']+b['Qe'],total['Qe'])
 def test_ppll_interval_crossing_wet_edge(self):
  r=C.blocked_flow_from_segments([-1,1],[0,10],1,0,10)
  self.assertAlmostEqual(r['L_prime'],5);self.assertAlmostEqual(r['Ae'],2.5)
  self.assertAlmostEqual(r['Qe'],1.875)
  with self.assertRaises(ValueError): C.blocked_flow_from_segments([-1,1],[0,10],1,0,4)
  with self.assertRaises(ValueError): C.blocked_flow_from_segments([1,1],[0,10],1,0,11)
 def test_requested_initial_mode_does_not_change_footing_to_piles(self):
  args=(5,3,1,1,1,1.1,1,False,-.01,1,1,3,1,3,3,4,4)
  standard=C.complex_pier(*args)
  initial=C.complex_pier(*args,initial_only=True)
  self.assertEqual(standard['cap_case'],1)
  self.assertEqual(initial['cap_case'],2);self.assertEqual(initial['ys_pg'],0)
 def test_requested_initial_mode_keeps_buried_foundation_buried(self):
  r=C.complex_pier(5,3,1,1,1,1.1,1,False,-2.1,2,1,3,1,3,3,4,4,initial_only=True,d84_m=0)
  self.assertEqual(r['cap_case'],0);self.assertEqual(r['ys_pc'],0);self.assertEqual(r['ys_pg'],0)
 def test_general_abutment_independent_input_combinations(self):
  combinations=[dict(qe=30,ae=15,ya=3,length=5),dict(qe=30,ve=2,ya=3,length=5),
   dict(ve=2,ae=15,ya=3,length=5),dict(qe=30,ya=3,length=5,blocked_width=5),
   dict(qe=30,ae=15,length=5,blocked_width=5),dict(ve=2,ya=3,length=5,blocked_width=5),
   dict(qe=30,ve=2,length=5,blocked_width=5),dict(qe=30,ae=15,ve=2,ya=3,length=5)]
  for inputs in combinations:
   with self.subTest(inputs=inputs):
    r=C.resolve_abutment_hydraulics(**inputs)
    for key,val in dict(Qe=30,Ae=15,Ve=2,ya=3,L_prime=5).items():self.assertAlmostEqual(r[key],val)
 def test_general_abutment_rejects_underdetermined_or_inconsistent(self):
  for inputs in [dict(ae=15,ya=3,length=5),dict(qe=30),dict(qe=30,ae=15,ve=4,ya=3,length=5),
    dict(qe=30,ae=15,ya=2,length=5,blocked_width=5),dict(qe=-1,ae=15,ya=3,length=5),dict(qe=30,ae=0,ya=3,length=5)]:
   with self.subTest(inputs=inputs),self.assertRaises(ValueError):C.resolve_abutment_hydraulics(**inputs)
 def test_general_abutment_zero_discharge_and_decimal_comma(self):
  r=C.resolve_abutment_hydraulics(qe=0,ae=15,ya=3,length=5)
  self.assertEqual(r['Ve'],0);self.assertEqual(r['Ae'],15)
  self.assertEqual(C.optional_number('1,56'),1.56)
  self.assertEqual(C.optional_number('1.234,56'),1234.56)
  self.assertEqual(C.optional_number('1,234.56'),1234.56)
  self.assertIsNone(C.optional_number(''))
  with self.assertRaises(ValueError):C.optional_number('NaN')
 def test_froehlich_example_keeps_area_width_distinct_from_active_length(self):
  # HEC §8.7.1: Ae=3.5*75 ft² but active L′=960/23≈42 ft, not 75 ft.
  r=C.resolve_abutment_hydraulics(qe=960*ft**3,ae=262.5*ft**2,ya=3.5*ft,length=960/23*ft)
  self.assertAlmostEqual(r['ya']/ft,3.5)
  self.assertAlmostEqual(r['Ve']/ft,960/262.5)
  self.assertNotAlmostEqual(r['Ae']/r['ya'],r['L_prime'])
 def test_direct_velocity_without_flow_or_area(self):
  r=C.resolve_abutment_hydraulics(ve=9.9*ft,ya=6.2*ft,length=742*ft)
  self.assertIsNone(r['Qe']);self.assertIsNone(r['Ae'])
  scour=C.abutment_scour(r['ya'],r['Ve'],r['L_prime'],.82,110)
  self.assertAlmostEqual(scour['ys']/ft,33.9,delta=.3)
  zero=C.resolve_abutment_hydraulics(ve=0,ya=2,length=3)
  self.assertEqual(C.abutment_scour(zero['ya'],zero['Ve'],zero['L_prime'],1)['ys'],0)
if __name__=='__main__': unittest.main(verbosity=2)
