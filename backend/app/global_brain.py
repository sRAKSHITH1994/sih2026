from __future__ import annotations

from collections import defaultdict,deque
from datetime import datetime,timezone
from pathlib import Path
import math
import time

import numpy as np

from .config import CORE_FEATURES,CORE_TP_FEATURES,MODEL_TP_PATH,MODEL_TPH_PATH
from .lstm_autoencoder import NumpyLSTMAutoencoder
from .schemas import GlobalDecision
from .sensor_registry import flatten_sensor_values
from .spatial import SpatialVerifier


class AdaptiveFeatureMonitor:
    """Sensor-agnostic adaptive detector for newly attached optional channels."""
    def __init__(self,window=60):
        self.window=window;self.history=defaultdict(lambda:defaultdict(lambda:deque(maxlen=window)))

    def evaluate(self,station_id,values):
        scores={}
        for name,value in values.items():
            history=self.history[station_id][name]
            if len(history)>=20:
                array=np.asarray(history,dtype=float);median=float(np.median(array))
                mad=float(np.median(np.abs(array-median)))
                scale=max(1.4826*mad,float(np.std(array))*.35,1e-3)
                z=abs(value-median)/scale
                scores[name]=min(1.0,max(0.0,(z-2.5)/3.5))
            history.append(value)
        return scores

    def clear_features(self,station_id,names):
        for name in names:self.history[station_id].pop(name,None)

    def reset(self):self.history.clear()


class GlobalBrainEngine:
    def __init__(self,model_path:Path=MODEL_TPH_PATH,tp_model_path:Path=MODEL_TP_PATH):
        self.models={}
        if Path(model_path).exists():self.models["TPH"]=NumpyLSTMAutoencoder.load(model_path)
        if Path(tp_model_path).exists():self.models["TP"]=NumpyLSTMAutoencoder.load(tp_model_path)
        self.model=self.models.get("TPH")  # Backwards-compatible public attribute.
        self.core_history={
            "TPH":defaultdict(lambda:deque(maxlen=self.models.get("TPH").sequence_length if self.models.get("TPH") else 20)),
            "TP":defaultdict(lambda:deque(maxlen=self.models.get("TP").sequence_length if self.models.get("TP") else 20)),
        }
        self.spatial=SpatialVerifier();self.dynamic=AdaptiveFeatureMonitor()

    def reset(self):
        for histories in self.core_history.values():histories.clear()
        self.spatial.reset();self.dynamic.reset()

    def reset_station(self,station_id):
        for histories in self.core_history.values():histories.pop(station_id,None)
        self.dynamic.history.pop(station_id,None)
        self.spatial.latest.pop(station_id,None)

    def _temporal(self,station_id,values):
        tp_complete=all(name in values for name in CORE_TP_FEATURES)
        tph_complete=all(name in values for name in CORE_FEATURES)
        if not tp_complete:
            self.core_history["TP"][station_id].clear();self.core_history["TPH"][station_id].clear()
            return {"ready":False,"profile":"NONE","score":0.0,"anomaly":False,"loss":None,"threshold":None,
                    "attribution":{},"shapley":{},"reason":"Temperature/pressure inputs are incomplete."}
        self.core_history["TP"][station_id].append([values[name] for name in CORE_TP_FEATURES])
        if tph_complete:self.core_history["TPH"][station_id].append([values[name] for name in CORE_FEATURES])
        else:self.core_history["TPH"][station_id].clear()
        profile="TPH" if tph_complete and "TPH" in self.models else "TP"
        model=self.models.get(profile);history=self.core_history[profile][station_id]
        if not model or len(history)<history.maxlen:
            return {"ready":False,"profile":profile,"score":0.0,"anomaly":False,"loss":None,
                    "threshold":model.threshold if model else None,"attribution":{},"shapley":{},
                    "reason":f"{profile} temporal warm-up {len(history)}/{history.maxlen}." if model else f"{profile} model is unavailable."}
        window=np.asarray(history,dtype=np.float32);report=model.score(window)
        report["profile"]=profile;report["shapley"]=model.exact_shapley(window)
        report["reason"]=(f"Trained {profile} LSTM reconstruction error exceeded its normal-sequence threshold."
                          if report["anomaly"] else f"{profile} sequence reconstructed within the learned normal envelope.")
        return report

    @staticmethod
    def _multivariate(values):
        reasons=[];score=1.0
        t=values.get("temperature_c");p=values.get("pressure_hpa");h=values.get("humidity_pct")
        if t is not None and not -50<=t<=70:score-=.6;reasons.append("temperature outside physical AWS range")
        if p is not None and not 850<=p<=1100:score-=.6;reasons.append("pressure outside physical AWS range")
        if h is not None and not 0<=h<=100:score-=.8;reasons.append("humidity outside 0-100%")
        if t is not None and h is not None:
            # Approximate dew point must not materially exceed air temperature.
            dew=t-(100-h)/5.0
            if dew>t+.5:score-=.4;reasons.append("dew-point relationship is impossible")
        return {"score":max(0.0,score),"consistent":score>=.65,
                "explanation":"; ".join(reasons) if reasons else "Core measurements satisfy physical consistency checks."}

    def process(self,packet:dict,received_at=None):
        start=time.perf_counter();received_at=received_at or datetime.now(timezone.utc)
        station_id=packet["station_id"];values,active_sensors=flatten_sensor_values(packet)
        core_complete=all(name in values for name in CORE_FEATURES)
        if not core_complete:self.dynamic.clear_features(station_id,CORE_FEATURES)
        temporal=self._temporal(station_id,values)
        # T/P/H already have a trained sequence model and edge rules. The
        # adaptive monitor is reserved for optional/new channels, preventing
        # duplicate detectors from turning normal diurnal drift into alerts.
        optional_values={name:value for name,value in values.items() if name not in CORE_FEATURES}
        dynamic_scores=self.dynamic.evaluate(station_id,optional_values)
        source_mode=str(packet.get("source_mode","HARDWARE")).upper()
        spatial=self.spatial.analyze(station_id,values,packet.get("latitude"),packet.get("longitude"),received_at,source_mode)
        multivariate=self._multivariate(values)
        local=packet.get("local_brain",{})
        local_alert=bool(local.get("anomaly"))
        invalid_attached=[name for name,s in packet.get("sensors",{}).items() if s.get("attached") and not s.get("valid")]
        dynamic_alerts=[name for name,score in dynamic_scores.items() if score>=.5]
        model_alert=bool(temporal.get("anomaly"))
        alert=local_alert or model_alert or bool(dynamic_alerts) or bool(invalid_attached)

        local_fault=str(local.get("fault_type","NORMAL")).upper()
        affected=list(dict.fromkeys(list(local.get("affected_sensors",[]))+invalid_attached+dynamic_alerts))
        attribution=temporal.get("attribution",{})
        if attribution:
            affected.extend([name for name,value in attribution.items() if value>=.34])
            affected=list(dict.fromkeys(affected))

        # MPU_POSITION_ADDITION: physical mounting evidence is not a weather event.
        pose = local.get("station_position", {})
        position_alert = bool(pose.get("active")) and bool(pose.get("calibrated"))
        if position_alert:
            alert = True
            affected = list(dict.fromkeys(affected + ["station"]))
            critical = bool(pose.get("critical"))
            other_critical = bool(invalid_attached) or float(local.get("severity_score", 0)) >= 80
            decision = GlobalDecision(
                category="STATION_POSITION_FAULT",
                specific_type="STATION_FALLEN" if critical else "STATION_TILTED",
                anomaly=True, sensor_fault=bool(invalid_attached),
                confidence=float(local.get("confidence", .9)),
                severity="CRITICAL" if critical or other_critical else "HIGH",
                explanation=local.get("explanation", "The station moved outside its calibrated orientation tolerance."),
                affected_features=affected,
            )
        elif invalid_attached or local_fault in {"DATA_LOSS","COMMUNICATION_FAULT"}:
            decision=GlobalDecision(category="SENSOR_FAULT",specific_type="DATA_LOSS",anomaly=True,
                sensor_fault=True,confidence=max(.9,float(local.get("confidence",0))),severity="CRITICAL",
                explanation=f"Configured sensor data is unavailable: {', '.join(invalid_attached or affected)}. Spatial weather validation is bypassed because this is a hardware/data-integrity failure.",affected_features=affected)
        elif alert and spatial.corroborated and multivariate["consistent"]:
            confidence=min(.98,.55+.35*spatial.agreement+.10*multivariate["score"])
            decision=GlobalDecision(category="GENUINE_WEATHER_EVENT",specific_type="SPATIOTEMPORAL_EVENT",anomaly=True,
                genuine_weather=True,confidence=confidence,severity="HIGH",
                explanation=f"The temporal change is corroborated by {spatial.neighbor_count} {'simulated' if source_mode=='SIMULATION' else 'real'} neighbouring stations ({spatial.agreement*100:.1f}% agreement) and remains physically consistent.",affected_features=affected)
        elif alert and spatial.status=="LOCALIZED":
            confidence=min(.98,max(.75,.55+.30*(1-spatial.agreement)+.13*float(local.get("confidence",0))))
            fault=local_fault if local_fault not in {"NORMAL","NONE"} else "LOCALIZED_SENSOR_ANOMALY"
            decision=GlobalDecision(category="SENSOR_FAULT",specific_type=fault,anomaly=True,sensor_fault=True,
                confidence=confidence,severity="HIGH",
                explanation=f"The station anomaly is not reproduced by nearby stations ({spatial.agreement*100:.1f}% agreement), indicating a localized sensor or station fault.",affected_features=affected)
        elif alert:
            confidence=min(.85,max(.55,float(local.get("confidence",0)),float(temporal.get("score",0))))
            decision=GlobalDecision(category="UNVERIFIED_ANOMALY",specific_type=local_fault if local_fault!="NORMAL" else "TEMPORAL_ANOMALY",
                anomaly=True,confidence=confidence,severity="WARNING",
                explanation=f"An anomaly is present, but there are not enough fresh {'simulated' if source_mode=='SIMULATION' else 'real'} neighbouring stations to label it as weather or a localized fault. The system refuses to fabricate spatial evidence.",affected_features=affected)
        else:
            normal_explanation=("Local checks are normal. The trained T/P model remains active without humidity; the T/P/H model activates automatically after an external humidity sensor supplies 20 valid samples."
                                if temporal.get("profile")=="TP" else
                                "Local checks, trained temporal reconstruction and available physical-consistency checks are normal.")
            decision=GlobalDecision(category="NORMAL",specific_type="NORMAL",anomaly=False,confidence=.97,severity="NORMAL",
                explanation=normal_explanation,affected_features=[])

        evidence={
            "local_brain":local,"lstm":temporal,"spatial":spatial.to_dict(),
            "multivariate":multivariate,"dynamic_feature_scores":dynamic_scores,
            "active_sensors":active_sensors,"active_features":sorted(values),
            "xai":{"local_edge_method":"gradient_x_input_top_features",
                   "local_edge_features":local.get("ml_top_features",""),
                   "global_method":temporal.get("shapley",{}).get("method","waiting"),
                   "global_importance":temporal.get("shapley",{}).get("importance",{})},
            "model":"trained_edge_mlp + dual_profile_numpy_lstm + real_station_spatial_verification",
        }
        decision.evidence=evidence
        self.spatial.update(station_id,values,packet.get("latitude"),packet.get("longitude"),received_at,alert,source_mode)
        return decision.model_dump(),(time.perf_counter()-start)*1000.0
