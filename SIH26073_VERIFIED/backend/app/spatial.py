from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import math
from .config import MIN_SPATIAL_NEIGHBORS,NEIGHBOR_MAX_AGE_SECONDS,SPATIAL_RADIUS_KM,SPATIAL_SCALES

def haversine_km(a,b,c,d):
 if any(x is None or not math.isfinite(x) for x in (a,b,c,d)):return math.inf
 p1,p2=map(math.radians,(a,c));dp=math.radians(c-a);dl=math.radians(d-b)
 h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371*2*math.atan2(math.sqrt(h),math.sqrt(max(0,1-h)))
@dataclass
class SpatialReport:
 status:str
 neighbor_count:int=0
 agreement:float=0.
 corroborated:bool=False
 neighbors:list=None
 explanation:str=''
 supporting_neighbors:int=0
 def to_dict(self):return asdict(self)
class SpatialVerifier:
 def __init__(self):self.latest={}
 def update(self,station_id,values,latitude,longitude,received_at=None,anomaly=False,source_mode='HARDWARE',weather_change=None,equipment_fault=False):
  self.latest[(source_mode,station_id)]={'values':dict(values),'latitude':latitude,'longitude':longitude,
    'received_at':received_at or datetime.now(timezone.utc),'anomaly':bool(anomaly),'weather_change':weather_change or {},'equipment_fault':equipment_fault}
 def analyze(self,station_id,values,latitude,longitude,now=None,source_mode='HARDWARE',weather_change=None):
  now=now or datetime.now(timezone.utc);candidates=[];changes=weather_change or {}
  for (mode,other),r in self.latest.items():
   if other==station_id or mode!=source_mode:continue
   distance=haversine_km(latitude,longitude,r['latitude'],r['longitude']);age=(now-r['received_at']).total_seconds()
   if not 0<=age<=min(NEIGHBOR_MAX_AGE_SECONDS,30) or distance>SPATIAL_RADIUS_KM:continue
   common=[k for k in changes if k in r['weather_change'] and k in SPATIAL_SCALES]
   matches=[k for k in common if changes[k]*r['weather_change'][k]>0 and abs(changes[k]-r['weather_change'][k])<=SPATIAL_SCALES[k] and .5<=abs(changes[k]/r['weather_change'][k])<=2.]
   supported=not r['equipment_fault'] and r['anomaly'] and len(matches)>=2
   candidates.append({'station_id':other,'distance_km':round(distance,2),'age_seconds':round(age,1),'anomaly_support':supported,'matching_features':matches})
  support=sum(x['anomaly_support'] for x in candidates);count=len(candidates)
  enough=count>=max(2,MIN_SPATIAL_NEIGHBORS);corroborated=enough and support>=max(2,MIN_SPATIAL_NEIGHBORS) and support/count>=.5
  status='CORROBORATED' if corroborated else 'INSUFFICIENT_NEIGHBORS' if not enough else 'NOT_CORROBORATED'
  return SpatialReport(status,count,support/max(1,count),corroborated,candidates,
    f'{support} independent stations support matching changes in at least two weather channels. Unknown locations and equipment faults are excluded.',support)
 def reset(self):self.latest.clear()
