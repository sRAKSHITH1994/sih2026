from __future__ import annotations

import json
from pathlib import Path
from itertools import combinations
from math import factorial

import numpy as np


def _sigmoid(x):
    return 1.0/(1.0+np.exp(-np.clip(x,-20.0,20.0)))


class NumpyLSTMAutoencoder:
    """Small, genuinely trained LSTM sequence autoencoder.

    It is intentionally NumPy-only so the Global Brain can run on an ordinary
    hackathon laptop without TensorFlow/PyTorch. Both encoder and decoder gates
    are optimized through back-propagation through time with Adam.
    """

    def __init__(self,sequence_length=20,input_dim=3,hidden_dim=12,seed=42):
        self.sequence_length=int(sequence_length)
        self.input_dim=int(input_dim)
        self.hidden_dim=int(hidden_dim)
        self.seed=int(seed)
        self.feature_names=["temperature_c","pressure_hpa","humidity_pct"]
        self.mean=np.zeros(self.input_dim,dtype=np.float32)
        self.std=np.ones(self.input_dim,dtype=np.float32)
        self.threshold=1.0
        self.score_scale=.25
        self.trained=False
        self.sample_interval_seconds=60
        self.training_provenance="unrecorded"
        self._init_params()

    def _init_params(self):
        rng=np.random.default_rng(self.seed)
        fan=self.input_dim+self.hidden_dim
        scale=np.sqrt(2.0/(fan+self.hidden_dim*4))
        self.params={
            "Wenc":rng.normal(0,scale,(fan,4*self.hidden_dim)).astype(np.float32),
            "benc":np.zeros(4*self.hidden_dim,dtype=np.float32),
            "Wdec":rng.normal(0,scale,(fan,4*self.hidden_dim)).astype(np.float32),
            "bdec":np.zeros(4*self.hidden_dim,dtype=np.float32),
            "Why":rng.normal(0,np.sqrt(2/(self.hidden_dim+self.input_dim)),
                             (self.hidden_dim,self.input_dim)).astype(np.float32),
            "by":np.zeros(self.input_dim,dtype=np.float32),
        }
        # Forget-gate bias improves stable memory at the start of training.
        self.params["benc"][self.hidden_dim:2*self.hidden_dim]=1.0
        self.params["bdec"][self.hidden_dim:2*self.hidden_dim]=1.0

    def _cell_forward(self,x,h_prev,c_prev,W,b):
        joined=np.concatenate((x,h_prev),axis=1)
        gates=joined@W+b
        h=self.hidden_dim
        i=_sigmoid(gates[:,:h]);f=_sigmoid(gates[:,h:2*h])
        g=np.tanh(gates[:,2*h:3*h]);o=_sigmoid(gates[:,3*h:])
        c=f*c_prev+i*g
        out=o*np.tanh(c)
        return out,c,(joined,i,f,g,o,c,c_prev)

    def _cell_backward(self,dh,dc,cache,W):
        joined,i,f,g,o,c,c_prev=cache
        tc=np.tanh(c)
        do=dh*tc
        dc_total=dc+dh*o*(1.0-tc*tc)
        df=dc_total*c_prev
        dc_prev=dc_total*f
        di=dc_total*g
        dg=dc_total*i
        da=np.concatenate((di*i*(1-i),df*f*(1-f),dg*(1-g*g),do*o*(1-o)),axis=1)
        dW=joined.T@da
        db=da.sum(axis=0)
        djoined=da@W.T
        return djoined[:,:self.input_dim],djoined[:,self.input_dim:],dc_prev,dW,db

    def _forward(self,x):
        batch=x.shape[0]
        h=np.zeros((batch,self.hidden_dim),dtype=np.float32)
        c=np.zeros_like(h)
        enc=[]
        for t in range(self.sequence_length):
            h,c,cache=self._cell_forward(x[:,t,:],h,c,self.params["Wenc"],self.params["benc"])
            enc.append(cache)

        dec=[];outputs=[];hidden=[]
        zero=np.zeros((batch,self.input_dim),dtype=np.float32)
        for _ in range(self.sequence_length):
            h,c,cache=self._cell_forward(zero,h,c,self.params["Wdec"],self.params["bdec"])
            dec.append(cache);hidden.append(h)
            outputs.append(h@self.params["Why"]+self.params["by"])
        return np.stack(outputs,axis=1),enc,dec,hidden

    def _loss_and_gradients(self,x):
        y,enc,dec,hidden=self._forward(x)
        difference=y-x
        loss=float(np.mean(difference*difference))
        dy=(2.0/difference.size)*difference
        gradients={name:np.zeros_like(value) for name,value in self.params.items()}
        dh=np.zeros((x.shape[0],self.hidden_dim),dtype=np.float32)
        dc=np.zeros_like(dh)

        for t in range(self.sequence_length-1,-1,-1):
            gradients["Why"]+=hidden[t].T@dy[:,t,:]
            gradients["by"]+=dy[:,t,:].sum(axis=0)
            dh=dh+dy[:,t,:]@self.params["Why"].T
            _,dh,dc,dW,db=self._cell_backward(dh,dc,dec[t],self.params["Wdec"])
            gradients["Wdec"]+=dW;gradients["bdec"]+=db

        for t in range(self.sequence_length-1,-1,-1):
            _,dh,dc,dW,db=self._cell_backward(dh,dc,enc[t],self.params["Wenc"])
            gradients["Wenc"]+=dW;gradients["benc"]+=db
        return loss,gradients

    def make_sequences(self,values,stride=1):
        array=np.asarray(values,dtype=np.float32)
        if len(array)<self.sequence_length:return np.empty((0,self.sequence_length,self.input_dim),dtype=np.float32)
        return np.stack([array[i:i+self.sequence_length]
                         for i in range(0,len(array)-self.sequence_length+1,stride)])

    def fit(self,values,epochs=24,batch_size=64,learning_rate=.002,verbose=False):
        values=np.asarray(values,dtype=np.float32)
        flat=values.reshape(-1,self.input_dim)
        self.mean=flat.mean(axis=0)
        self.std=flat.std(axis=0)
        self.std=np.where(self.std<1e-4,1.0,self.std).astype(np.float32)
        scaled=(values-self.mean)/self.std
        sequences=scaled.copy() if scaled.ndim==3 else self.make_sequences(scaled,stride=2)
        if len(sequences)<10:raise ValueError("Need at least 10 normal sequences to train the LSTM autoencoder")

        rng=np.random.default_rng(self.seed)
        first={name:np.zeros_like(value) for name,value in self.params.items()}
        second={name:np.zeros_like(value) for name,value in self.params.items()}
        step=0
        for epoch in range(int(epochs)):
            rng.shuffle(sequences)
            losses=[]
            for start in range(0,len(sequences),batch_size):
                batch=sequences[start:start+batch_size]
                loss,gradients=self._loss_and_gradients(batch)
                losses.append(loss);step+=1
                for name,gradient in gradients.items():
                    np.clip(gradient,-1.0,1.0,out=gradient)
                    first[name]=.9*first[name]+.1*gradient
                    second[name]=.999*second[name]+.001*(gradient*gradient)
                    mhat=first[name]/(1-.9**step);vhat=second[name]/(1-.999**step)
                    self.params[name]-=learning_rate*mhat/(np.sqrt(vhat)+1e-8)
            if verbose and (epoch==0 or (epoch+1)%4==0):
                print(f"epoch {epoch+1:02d}/{epochs} loss={np.mean(losses):.6f}")

        losses=self.sequence_losses(sequences,already_scaled=True)
        self.threshold=float(np.percentile(losses,99.5))
        mad=float(np.median(np.abs(losses-np.median(losses))))
        self.score_scale=max(mad*6.0,self.threshold*.12,1e-5)
        self.trained=True
        return self

    def sequence_losses(self,sequences,already_scaled=False):
        sequences=np.asarray(sequences,dtype=np.float32)
        if not already_scaled:sequences=(sequences-self.mean)/self.std
        result=[]
        for start in range(0,len(sequences),256):
            batch=sequences[start:start+256]
            reconstructed,*_=self._forward(batch)
            result.extend(np.mean((reconstructed-batch)**2,axis=(1,2)).tolist())
        return np.asarray(result,dtype=np.float32)

    def score(self,window):
        window=np.asarray(window,dtype=np.float32)
        if window.shape!=(self.sequence_length,self.input_dim):
            raise ValueError(f"Expected window {(self.sequence_length,self.input_dim)}, got {window.shape}")
        scaled=(window-self.mean)/self.std
        reconstructed,*_=self._forward(scaled[None,:,:])
        error=(reconstructed[0]-scaled)**2
        loss=float(error.mean())
        z=(loss-self.threshold)/self.score_scale
        score=float(1.0/(1.0+np.exp(-np.clip(z,-20,20))))
        contributions=error.mean(axis=0)
        contribution_total=float(contributions.sum()) or 1.0
        attribution={name:float(value/contribution_total)
                     for name,value in zip(self.feature_names,contributions)}
        return {
            "ready":True,"loss":loss,"threshold":self.threshold,"score":score,
            "anomaly":loss>self.threshold,"attribution":attribution,
        }

    def reconstruction_loss(self,window):
        """Return reconstruction loss without thresholding or recursive explanation."""
        window=np.asarray(window,dtype=np.float32)
        scaled=(window-self.mean)/self.std
        reconstructed,*_=self._forward(scaled[None,:,:])
        return float(np.mean((reconstructed[0]-scaled)**2))

    def exact_shapley(self,window):
        """Exact Shapley attribution over the model's input channels.

        Excluded channels are replaced by their normal training mean. With two
        or three atmospheric inputs there are only 4 or 8 coalitions, so this
        is fast enough for the Global Brain and is genuine Shapley attribution,
        not a label placed on reconstruction error.
        """
        window=np.asarray(window,dtype=np.float32)
        n=self.input_dim
        coalition_loss={}
        for mask in range(1<<n):
            candidate=np.broadcast_to(self.mean,(self.sequence_length,n)).copy()
            for index in range(n):
                if mask&(1<<index):candidate[:,index]=window[:,index]
            coalition_loss[mask]=self.reconstruction_loss(candidate)
        values=[]
        denominator=factorial(n)
        for index in range(n):
            contribution=0.0
            remaining=[item for item in range(n) if item!=index]
            for size in range(n):
                weight=factorial(size)*factorial(n-size-1)/denominator
                for subset in combinations(remaining,size):
                    mask=sum(1<<item for item in subset)
                    contribution+=weight*(coalition_loss[mask|(1<<index)]-coalition_loss[mask])
            values.append(float(contribution))
        absolute=sum(abs(value) for value in values) or 1.0
        return {"method":"exact_shapley_feature_coalitions",
                "signed":{name:value for name,value in zip(self.feature_names,values)},
                "importance":{name:abs(value)/absolute for name,value in zip(self.feature_names,values)},
                "baseline_loss":coalition_loss[0],"full_loss":coalition_loss[(1<<n)-1]}

    def save(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        metadata=json.dumps({
            "sequence_length":self.sequence_length,"input_dim":self.input_dim,
            "hidden_dim":self.hidden_dim,"seed":self.seed,"feature_names":self.feature_names,
            "threshold":self.threshold,"score_scale":self.score_scale,"trained":self.trained,
            "sample_interval_seconds":self.sample_interval_seconds,"training_provenance":self.training_provenance,
        })
        np.savez_compressed(path,metadata=np.array(metadata),mean=self.mean,std=self.std,**self.params)

    @classmethod
    def load(cls,path):
        data=np.load(path,allow_pickle=False)
        metadata=json.loads(str(data["metadata"]))
        model=cls(metadata["sequence_length"],metadata["input_dim"],metadata["hidden_dim"],metadata["seed"])
        model.feature_names=list(metadata["feature_names"])
        model.threshold=float(metadata["threshold"]);model.score_scale=float(metadata["score_scale"])
        model.trained=bool(metadata["trained"]);model.mean=data["mean"];model.std=data["std"]
        model.sample_interval_seconds=int(metadata.get("sample_interval_seconds",60))
        model.training_provenance=metadata.get("training_provenance","legacy artifact; minute CSV")
        for name in model.params:model.params[name]=data[name]
        return model
