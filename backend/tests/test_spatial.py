from datetime import datetime,timezone

from app.spatial import SpatialVerifier


def test_spatial_requires_real_independent_anomaly_support():
    verifier=SpatialVerifier();now=datetime.now(timezone.utc)
    values={"temperature_c":30.0,"pressure_hpa":1008.0,"humidity_pct":72.0}
    empty=verifier.analyze("TARGET",values,13.0,80.17,now)
    assert empty.status=="INSUFFICIENT_NEIGHBORS" and empty.neighbor_count==0

    verifier.update("NEIGHBOR_1",values,13.01,80.17,now,anomaly=False)
    verifier.update("NEIGHBOR_2",values,13.02,80.17,now,anomaly=False)
    localized=verifier.analyze("TARGET",values,13.0,80.17,now)
    assert localized.status=="LOCALIZED" and localized.supporting_neighbors==0

    verifier.update("NEIGHBOR_1",values,13.01,80.17,now,anomaly=True)
    verifier.update("NEIGHBOR_2",values,13.02,80.17,now,anomaly=True)
    corroborated=verifier.analyze("TARGET",values,13.0,80.17,now)
    assert corroborated.status=="CORROBORATED" and corroborated.supporting_neighbors==2


def test_simulation_and_hardware_are_never_mixed():
    verifier=SpatialVerifier();now=datetime.now(timezone.utc)
    values={"temperature_c":30.0,"pressure_hpa":1008.0}
    verifier.update("SIM_1",values,13.01,80.17,now,anomaly=True,source_mode="SIMULATION")
    verifier.update("SIM_2",values,13.02,80.17,now,anomaly=True,source_mode="SIMULATION")
    report=verifier.analyze("HARDWARE_1",values,13.0,80.17,now,source_mode="HARDWARE")
    assert report.status=="INSUFFICIENT_NEIGHBORS" and report.neighbor_count==0
