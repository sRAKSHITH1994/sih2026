import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'edge_training'))
from train_edge_mlp import real_dataset
from corpus import session
from feature_pipeline import CLASS_NAMES

def test_real_data_session_leakage_is_rejected(tmp_path):
 df,labels,_=session(0,1,120);df['session_id']='reused';df['split']='train';df['ground_truth']='NORMAL';df.loc[100:,'split']='test'
 p=tmp_path/'real.csv';df.to_csv(p,index=False)
 with pytest.raises(ValueError,match='Session leakage'):real_dataset(p)

def test_real_data_uses_labels_and_masks_optional_nan(tmp_path):
 frames=[]
 for split in ['train','validation','test']:
  for cls in range(10):
   df,y,_=session(cls,150+cls,120);df['session_id']=split+str(cls);df['split']=split;df['ground_truth']=[CLASS_NAMES[i] for i in y]
   df['solar_wm2']=np.nan;df['solar_valid']=0;frames.append(df)
 p=tmp_path/'real.csv';pd.concat(frames).to_csv(p,index=False);sets=real_dataset(p)
 assert all(np.isfinite(v[0]).all() for v in sets.values())
 assert set(sets['train'][1])==set(range(10))
