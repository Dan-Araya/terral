# Funciones puras copiadas literalmente; no se importa el programa original.
import numpy as np
import pandas as pd
MAIN=["temperatura","humedad","viento_2m","direccion_2m"]
def features(x):
 b=x[MAIN[:3]].copy()
 b['sin_D']=np.sin(np.deg2rad(x.direccion_2m)); b['cos_D']=np.cos(np.deg2rad(x.direccion_2m))
 f=b.copy()
 for lag in [1,3]:
  for c in b:
   f[f'{c}_lag{lag}']=b[c].shift(lag)
   f[f'{c}_delta{lag}']=b[c]-b[c].shift(lag)
 for c in b: f[f'{c}_media_previa6']=b[c].shift(1).rolling(6,min_periods=6).mean()
 f['V_max_previo6']=b.viento_2m.shift(1).rolling(6,min_periods=6).max()
 for name,angle in [('hora',2*np.pi*x.index.hour/24),('ano',2*np.pi*(x.index.dayofyear-1)/365.25)]:
  f[f'sin_{name}']=np.sin(angle); f[f'cos_{name}']=np.cos(angle)
 return f

def engine(available,above,state,h):
 """Input at each step: record presence, threshold decision and CURRENT state only.
 Target labels and future onsets are deliberately absent from the interface.
 """
 available=np.asarray(available,bool); above=np.asarray(above,bool); state=np.asarray(state,int)
 n=len(state); warning=available & above & (state==0)
 expires=np.maximum.accumulate(np.where(warning,np.arange(n)+h,-1))
 active=expires>np.arange(n)
 issue_episode=np.full(n,-1,int); action=np.full(n,'',object); episodes=[]
 last_end=-1; episode=-1
 for t in np.flatnonzero(warning):
  if t>last_end:
   episode+=1; episodes.append({'episode':episode,'start':int(t),'end':int(t+h),'first_expiry':int(t+h),'n_issues':1,'reactivation':episode>0})
   action[t]='reactivacion' if episode>0 else 'activacion'
  else:
   episodes[-1]['end']=int(t+h); episodes[-1]['n_issues']+=1; action[t]='renovacion'
  issue_episode[t]=episode; last_end=int(t+h)
 hist_episode=np.maximum.accumulate(issue_episode); hist_episode[~active]=-1
 closed=np.full(n,-1,int)
 for e in episodes:
  if e['end']<n: closed[e['end']]=e['episode']
 return {'warning':warning,'expires':expires,'active':active,'episode':hist_episode,'issue_episode':issue_episode,'action':action,'closed':closed,'episodes':episodes}

def classification(active,end,unknown,event,unevaluable):
 """Post-hoc attribution only. Evaluate future (t,end[t]]; never changes engine."""
 n=len(active); t=np.arange(n); clipped=np.minimum(end,n-1)
 def count(mask):
  c=np.cumsum(np.asarray(mask,int)); return c[clipped]-c[t]
 outside=end>=n
 unc=outside| (count(unknown)>0) | (count(unevaluable)>0)
 yes=count(event)>0
 # 0 off, 1 no onset, 2 evaluable onset, 3 indeterminate.
 return np.where(active,np.where(unc,3,np.where(yes,2,1)),0)

def event_links(issue_positions,h,events):
 """All valid pairs; every onset has at most one primary (earliest valid) issue."""
 links=[]; primary=[]
 for eid, onset in events:
  valid=issue_positions[(issue_positions<onset)&(issue_positions+h>=onset)]
  if len(valid):
   primary.append((eid,int(onset),int(valid[0]),int(valid[-1]),len(valid)))
   links.extend((eid,int(onset),int(t),i==0) for i,t in enumerate(valid))
 return links,primary

