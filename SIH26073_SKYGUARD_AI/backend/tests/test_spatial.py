from datetime import datetime,timezone,timedelta
from app.spatial import SpatialVerifier,haversine_km
import math

def test_support_requires_two_matching_changes_and_two_neighbors():
 v=SpatialVerifier();now=datetime.now(timezone.utc);values={'temperature_c':30.,'pressure_hpa':1008.};delta={'temperature_c':3.,'pressure_hpa':-4.}
 def report():return v.analyze('TARGET',values,13.,80.17,now,weather_change=delta)
 assert report().status=='INSUFFICIENT_NEIGHBORS'
 v.update('N1',values,13.01,80.17,now,True,weather_change=delta)
 v.update('N2',values,13.02,80.17,now,False,weather_change=delta)
 assert report().supporting_neighbors==1 and not report().corroborated
 v.update('N2',values,13.02,80.17,now,True,weather_change=delta)
 assert report().corroborated and report().supporting_neighbors==2
 v.update('N2',values,13.02,80.17,now,True,weather_change=delta,equipment_fault=True)
 assert not report().corroborated

def test_unknown_location_old_future_simulation_and_wrong_direction_are_excluded():
 now=datetime.now(timezone.utc);delta={'temperature_c':3.,'pressure_hpa':-4.};v=SpatialVerifier()
 assert math.isinf(haversine_km(None,None,13,80))
 for name,lat,dt,mode in [('unknown',None,0,'HARDWARE'),('old',13,60,'HARDWARE'),('future',13,-1,'HARDWARE'),('sim',13,0,'SIMULATION')]:
  v.update(name,{},lat,80,now-timedelta(seconds=dt),True,mode,delta)
 assert v.analyze('T',{},13,80,now,weather_change=delta).neighbor_count==0
 for i in range(2):v.update(str(i),{},13,80,now,True,weather_change={'temperature_c':-3.,'pressure_hpa':4.})
 assert not v.analyze('T',{},13,80,now,weather_change=delta).corroborated
