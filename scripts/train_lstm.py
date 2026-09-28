from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))

from app.config import CORE_FEATURES,CORE_TP_FEATURES,MODEL_TP_PATH,MODEL_TPH_PATH
from app.lstm_autoencoder import NumpyLSTMAutoencoder


def load_normal(path,features):
    frame=pd.read_csv(path)
    if "anomaly" in frame:frame=frame[frame["anomaly"]==0]
    source={"temperature_c":"temperature","pressure_hpa":"pressure","humidity_pct":"humidity"}
    return frame[[source[name] for name in features]].to_numpy(dtype=np.float32)


def train_profile(features,path,hidden_dim):
    train=load_normal(ROOT/"backend"/"data"/"train.csv",features)
    validation=load_normal(ROOT/"backend"/"data"/"val.csv",features)
    model=NumpyLSTMAutoencoder(sequence_length=20,input_dim=len(features),hidden_dim=hidden_dim,seed=42)
    model.feature_names=list(features)
    model.fit(train,epochs=24,batch_size=96,learning_rate=.002,verbose=True)
    scaled=(validation-model.mean)/model.std
    sequences=model.make_sequences(scaled,stride=2)
    losses=model.sequence_losses(sequences,already_scaled=True)
    model.threshold=float(np.percentile(losses,99.2))
    mad=float(np.median(np.abs(losses-np.median(losses))))
    model.score_scale=max(mad*6.0,model.threshold*.12,1e-5)
    model.save(path)
    print(f"saved {path}")
    print(f"features={features} validation_sequences={len(losses)} threshold={model.threshold:.6f} median_loss={np.median(losses):.6f}")


def main():
    train_profile(CORE_TP_FEATURES,MODEL_TP_PATH,10)
    train_profile(CORE_FEATURES,MODEL_TPH_PATH,12)


if __name__=="__main__":main()
