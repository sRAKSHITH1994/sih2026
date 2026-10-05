"""Portable NumPy inference on the exported float32 arrays, with mask gating."""
import numpy as np


def gate(probabilities, features):
    p=np.array(probabilities,copy=True)
    x=np.atleast_2d(features);p=np.atleast_2d(p)
    for cls,mask in [(5,51),(6,50),(7,52),(8,53),(9,54)]:p[x[:,mask]<.5,cls]=0
    # Atmospheric classes require the BMP. Firmware declines inference without it.
    p[x[:,48]<.5,1:5]=0
    p/=np.maximum(p.sum(axis=1,keepdims=True),1e-20)
    return p[0] if np.ndim(features)==1 else p


def infer(features,weights):
    x=(np.asarray(features,dtype=np.float32)-weights['mean'])/weights['scale']
    for i in (1,2):x=np.maximum(0,x@weights[f'w{i}']+weights[f'b{i}'])
    x=x@weights['w3']+weights['b3'];x-=np.max(x,axis=-1,keepdims=True)
    p=np.exp(x);p/=p.sum(axis=-1,keepdims=True)
    return gate(p,features)
