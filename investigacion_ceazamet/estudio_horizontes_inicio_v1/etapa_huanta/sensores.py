import heredado as b
from heredado import *
ROOT=Path(__file__).resolve().parent.parent.parent
IDX=b.IDX
STATION='llanos_de_huanta'
EXPECTED={'LLHTA':('temperatura',2.),'LLHHR':('humedad',2.),'LLHVV2M':('viento',2.),'LLHDV2M':('direccion',2.),'LLHPA':('presion',2.)}
def save(d,name): b.save(d,name)
def extension(x,prefix,wind=None):
 f=x.copy()
 for lag in [1,3]:
  for c in x:
   f[f'{c}_lag{lag}']=x[c].shift(lag); f[f'{c}_delta{lag}']=x[c]-x[c].shift(lag)
 for c in x: f[f'{c}_media_previa6']=x[c].shift(1).rolling(6,min_periods=6).mean()
 if wind: f['V_max_previo6']=x[wind].shift(1).rolling(6,min_periods=6).max()
 return f.add_prefix(prefix)
def allfeatures(x,p,pe):
 z=pe[[c for c in ['temperatura','humedad','viento','presion'] if c in pe]].copy()
 z['sin_D']=np.sin(np.deg2rad(pe.direccion)); z['cos_D']=np.cos(np.deg2rad(pe.direccion))
 return pd.concat([b.features(x),extension(p.to_frame('presion'),'INIA_'),extension(z,'LLH_',wind='viento')],axis=1)
def load_extra(manifest):
 confpath=ROOT/'estaciones_complementarias/configuracion.json'
 config=json.loads(confpath.read_text()); assert config['start']=='2013-01-01' and config['end']=='2023-12-31'
 station=next(s for s in config['stations'] if s['slug']==STATION)
 specs={s['code']:s for s in station['sensors']}
 for sid,(v,height) in EXPECTED.items(): assert specs[sid]['variable']==v and specs[sid]['height_m']==height
 prs=[]; meta=[]
 for year in range(2013,2024):
  q=pd.read_csv(ROOT/f'historico_inia/derivados/observaciones_{year}.csv',usecols=['fecha_sin_zona','variable','sensor','altura_encabezado_m','unidad','prom','porcentaje_datos','prom_utilizable_revision'])
  dt=pd.to_datetime(q.fecha_sin_zona); assert dt.between(b.START,b.END).all() and dt.dt.year.eq(year).all()
  basic=q[q.variable.isin(b.MAIN)]
  assert not (basic.prom_utilizable_revision.eq(1)&basic.porcentaje_datos.gt(100)).any()
  meta.append(q[q.variable.isin(b.MAIN+['presion'])][['variable','sensor','altura_encabezado_m','unidad']].drop_duplicates().assign(ano=year))
  q=q[q.variable.eq('presion')].copy(); assert not q.fecha_sin_zona.duplicated().any()
  good=np.isfinite(q.prom)&q.porcentaje_datos.gt(0)&q.porcentaje_datos.le(100)&q.prom_utilizable_revision.eq(1)
  prs.append(pd.Series(q.prom.where(good).to_numpy(),index=pd.to_datetime(q.fecha_sin_zona)))
 p=pd.concat(prs).reindex(IDX); save(pd.concat(meta),'metadatos_inia')
 path=ROOT/f'estaciones_complementarias/{STATION}/derivados/horarias.csv'
 integrity=ROOT/f'estaciones_complementarias/{STATION}/derivados/integridad.json'
 assert b.digest(path)==json.loads(integrity.read_text())['tables_sha256']['horarias.csv']
 q=pd.read_csv(path,dtype={'sensor':str},usecols=['fecha_sin_zona','sensor','variable','altura_m','unidad','min','prom','max','porcentaje_datos','presente','utilizable_revision','problemas'])
 dt=pd.to_datetime(q.fecha_sin_zona); assert dt.between(b.START,b.END).all() and dt.eq(dt.dt.floor('h')).all()
 q=q[q.sensor.isin(EXPECTED)].copy(); q['fecha']=pd.to_datetime(q.fecha_sin_zona)
 assert not q.duplicated(['fecha','sensor']).any()
 limits={'temperatura':(-50,60),'humedad':(0,100),'viento':(0,75),'direccion':(0,360),'presion':(300,1100)}
 masks=[]
 for sid,(v,height) in EXPECTED.items():
  z=q[q.sensor.eq(sid)]; assert z.variable.eq(v).all() and z.altura_m.eq(height).all() and z.unidad.eq(specs[sid]['unit']).all()
  good=np.isfinite(z[['min','prom','max','porcentaje_datos']]).all(axis=1)&z.porcentaje_datos.gt(0)&z.porcentaje_datos.le(100)
  for c in ['min','prom','max']: good &= z[c].between(*limits[v])
  if v!='direccion': good &= z['min'].le(z.prom)&z.prom.le(z['max'])
  assert np.array_equal(good,z.utilizable_revision.eq(1))
  masks.append({'sensor':sid,'variable':v,'altura_m':height,'unidad':specs[sid]['unit'],'filas':len(z),'utilizables':int(good.sum()),'ceros_validos':int((good&z.prom.eq(0)).sum())})
 q.loc[~q.utilizable_revision.eq(1),'prom']=np.nan
 pe=q.pivot(index='fecha',columns='variable',values='prom').reindex(IDX)
 save(pd.DataFrame(masks),'sensores_huanta')
 for path in [confpath,path,integrity]:
  manifest.append({'archivo':str(path.relative_to(b.ROOT)),'sha256_antes':b.digest(path)})
 return p,pe
