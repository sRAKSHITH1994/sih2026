from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime,timezone

from .config import MIN_SPATIAL_NEIGHBORS,NEIGHBOR_MAX_AGE_SECONDS,SPATIAL_RADIUS_KM,SPATIAL_SCALES


def haversine_km(lat1,lon1,lat2,lon2):
    if None in (lat1,lon1,lat2,lon2):return 0.0
    radius=6371.0
    p1=math.radians(lat1);p2=math.radians(lat2)
    dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return radius*2*math.atan2(math.sqrt(a),math.sqrt(1-a))


@dataclass
class SpatialReport:
    status:str
    neighbor_count:int
    agreement:float
    corroborated:bool
    neighbors:list[dict]
    explanation:str
    supporting_neighbors:int=0

    def to_dict(self):
        return {"status":self.status,"neighbor_count":self.neighbor_count,
                "agreement":round(self.agreement,4),"corroborated":self.corroborated,
                "neighbors":self.neighbors,"explanation":self.explanation,
                "supporting_neighbors":self.supporting_neighbors}


class SpatialVerifier:
    def __init__(self):self.latest={}

    def update(self,station_id,values,latitude,longitude,received_at=None,anomaly=False,source_mode="HARDWARE"):
        self.latest[station_id]={"values":dict(values),"latitude":latitude,"longitude":longitude,
                                 "received_at":received_at or datetime.now(timezone.utc),
                                 "anomaly":bool(anomaly),"source_mode":str(source_mode).upper()}

    def analyze(self,station_id,values,latitude,longitude,now=None,source_mode="HARDWARE"):
        now=now or datetime.now(timezone.utc)
        source_mode=str(source_mode).upper()
        candidates=[]
        for other_id,record in self.latest.items():
            if other_id==station_id:continue
            # Evaluation/simulation data must never corroborate physical AWS data.
            if record.get("source_mode","HARDWARE")!=source_mode:continue
            age=(now-record["received_at"]).total_seconds()
            distance=haversine_km(latitude,longitude,record["latitude"],record["longitude"])
            if age>NEIGHBOR_MAX_AGE_SECONDS or distance>SPATIAL_RADIUS_KM:continue
            common=[name for name in values if name in record["values"] and name in SPATIAL_SCALES]
            if not common:continue
            normalized=[abs(values[name]-record["values"][name])/SPATIAL_SCALES[name] for name in common]
            distance_score=sum(normalized)/len(normalized)
            agreement=max(0.0,1.0-distance_score)
            candidates.append({"station_id":other_id,"age_seconds":round(age,1),
                               "distance_km":round(distance,2),"agreement":round(agreement,4),
                               "common_features":common,"anomaly_support":bool(record.get("anomaly"))})
        if len(candidates)<MIN_SPATIAL_NEIGHBORS:
            kind="simulated" if source_mode=="SIMULATION" else "real"
            return SpatialReport("INSUFFICIENT_NEIGHBORS",len(candidates),0.0,False,candidates,
                                 f"No spatial claim made: fewer than two fresh {kind} neighbouring stations are available.")
        value_agreement=sum(item["agreement"] for item in candidates)/len(candidates)
        supporting=sum(bool(item["anomaly_support"]) for item in candidates)
        support_rate=supporting/len(candidates)
        # Similar absolute readings are not sufficient evidence of the same
        # event. At least half of real neighbours must independently alert.
        agreement=value_agreement*support_rate
        corroborated=value_agreement>=.65 and support_rate>=.5
        kind="simulated" if source_mode=="SIMULATION" else "real"
        return SpatialReport("CORROBORATED" if corroborated else "LOCALIZED",len(candidates),agreement,
                             corroborated,candidates,
                             f"{supporting}/{len(candidates)} {kind} neighbours independently support the anomaly; "
                             f"their measurement agreement is {value_agreement*100:.1f}%.",supporting)

    def reset(self):self.latest.clear()
