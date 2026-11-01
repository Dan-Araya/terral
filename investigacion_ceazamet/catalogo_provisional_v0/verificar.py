#!/usr/bin/env python3
"""Controles independientes de archivos entregados, sin regenerar ni modificar fuentes."""
import sys
sys.modules['numexpr']=None
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent; ROOT=OUT.parent.parent
SRC=OUT.parent/'diagnostico_2013_2023'
LO,HI=pd.Timestamp('2013-01-01'),pd.Timestamp('2023-12-31 23:00')
MAIN=['temperatura','humedad','viento_2m','direccion_2m']
checks=[]
def check(name,condition):
    assert bool(condition),name
    checks.append(name)
def read(n): return pd.read_csv(OUT/f'{n}.csv')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
c=read('catalogo_referencia'); hr=read('horas_referencia'); tr=read('trazabilidad_catalogo')
f=read('banderas'); s=read('seleccion_revision'); om=read('posibles_omisiones'); oh=read('condiciones_omisiones_horarias')
dg=read('datos_graficos'); e=read('evidencia_por_ventana')
check('156 IDs únicos y estado inicial intacto',len(c)==156 and c.id_tramo.nunique()==156 and c.estado.eq('candidato por criterio histórico, sin confirmar').all())
check('867 horas, sin duplicados',len(hr)==867 and c.horas_candidatas.sum()==867 and not hr.fecha_sin_zona.duplicated().any())
for _,r in c.iterrows():
    a,b=pd.Timestamp(r.primera_marca),pd.Timestamp(r.ultima_marca)
    check('ID estable '+r.id_tramo,r.id_tramo=='VCN-INIA-v0-'+a.strftime('%Y%m%dT%H%M'))
    g=hr[hr.id_tramo.eq(r.id_tramo)]; dates=pd.to_datetime(g.fecha_sin_zona)
    assert len(g)==r.horas_candidatas and dates.min()==a and dates.max()==b
    assert pd.DatetimeIndex(dates).equals(pd.date_range(a,b,freq='h'))
    assert g.temperatura.gt(11).all() and g.humedad.lt(30).all() and g.viento_2m.gt(2).all() and g.direccion_2m.between(0,180).all()
    assert g.estado.eq('cumple').all() and g.validez_conjunta.all()
    assert np.isclose(r.max_promedio_horario_ms,g.viento_2m.max(),atol=1e-6)
    assert np.isclose(r.viento_medio_ms,g.viento_2m.mean(),atol=1e-6)
    z=tr[tr.id_tramo.eq(r.id_tramo)]; w=z[z.variable.eq('viento_2m')]
    assert np.isclose(r.max_horario_publicado_ms,w['max'].max(),atol=1e-6)
    assert len(z)==4*len(g) and z.valido.all()
check('Referencias estrictas y máximos diferenciados',True)
source=pd.read_csv(SRC/'tablas/estados_horarios.csv'); source['fecha_sin_zona']=pd.to_datetime(source.fecha_sin_zona)
check('Partición fuente 867/95096/445',source.estado.value_counts().to_dict()=={'no_cumple':95096,'cumple':867,'no_evaluable':445})
check('Todas las candidatas fuente conservadas',set(hr.fecha_sin_zona)==set(source.loc[source.estado.eq('cumple'),'fecha_sin_zona'].astype(str)))
indexed=source.set_index('fecha_sin_zona')
for _,r in c.iterrows():
    a,b=pd.Timestamp(r.primera_marca),pd.Timestamp(r.ultima_marca)
    left=a==LO or indexed.loc[a-pd.Timedelta(hours=1),'estado']=='no_evaluable'
    right=b==HI or indexed.loc[b+pd.Timedelta(hours=1),'estado']=='no_evaluable'
    assert left==r.censura_izq and right==r.censura_der
check('Censura reproducida sin ampliar intervalos',True)
raw=pd.read_csv(SRC/'tablas/trazabilidad_observaciones.csv')
trace=raw.iloc[tr.fila_tabla_diagnostico.astype(int).values-2].reset_index(drop=True)
for col in ['fecha','variable','csv_fuente','fila_csv','sha256_original','hoja','fila_excel','sensor','unidad','altura_encabezado_m','min','prom','max','porcentaje_datos','valido']:
    if pd.api.types.is_numeric_dtype(trace[col]): assert np.allclose(trace[col],tr[col],equal_nan=True,atol=1e-6)
    else: assert trace[col].fillna('').astype(str).equals(tr[col].fillna('').astype(str)),col
check('3468 enlaces a filas y valores fuente exactos',len(tr)==3468)
for name in ['dias_historicos','eventos_por_dias']:
    pd.testing.assert_frame_equal(read(name),pd.read_csv(SRC/'tablas'/f'{name}.csv'))
check('Tablas de días conservadas separadamente',True)
check('Banderas no cambian catálogo',set(f.id_tramo)==set(c.id_tramo) and len(f)==156)
sens=read('sensibilidad_por_tramo'); check('1560 comparaciones, solo configuraciones previas',len(sens)==1560 and sens.groupby('id_tramo').size().eq(10).all())
check('Cortos 1 y 2 h sin filtrado',f.corto.sum()==37 and f.una_hora.sum()==26 and f.dos_horas.sum()==11)
check('30 ventanas, once años, cuatro épocas, sin duplicados',len(s)==30 and s.ano.nunique()==11 and s.epoca.nunique()==4 and s.id_objeto.nunique()==30)
windows=[]
for _,r in s.iterrows():
    a,b=pd.Timestamp(r.inicio_ventana),pd.Timestamp(r.fin_ventana)
    assert LO<=a<=b<=HI and (b-a)/pd.Timedelta(hours=1)==47
    assert all(not (a<=y and b>=x) for x,y in windows)
    windows.append((a,b)); assert (OUT/r.grafico).exists()
    g=dg[dg.id_revision.eq(r.id_revision)]; dates=pd.to_datetime(g.fecha_sin_zona)
    assert len(g)==48 and pd.DatetimeIndex(dates).equals(pd.date_range(a,b,freq='h'))
    expected=indexed.loc[dates]
    for v in MAIN:
        # En esta fuente las desconocidas conjuntas coinciden con faltantes de las cuatro variables.
        assert np.allclose(g[v].values,expected[v].where(expected.validez_conjunta).values,equal_nan=True,atol=1e-6)
    assert np.array_equal(g.estado_original.values,expected.estado.values)
check('1440 puntos horarios sin imputar, ventanas de 48 marcas sin solapamiento',len(dg)==1440)
check('68 omisiones, 24 fuera de abril–agosto',len(om)==68 and om.fuera_abril_agosto.sum()==24)
check('Cuatro marcas conocidas que no cumplen por cada omisión',len(oh)==4*len(om) and oh.estado_original.eq('no_cumple').all())
for _,r in om.iterrows():
    g=oh[oh.id_omision.eq(r.id_omision)].sort_values('fecha_sin_zona'); dates=pd.to_datetime(g.fecha_sin_zona)
    assert pd.DatetimeIndex(dates).equals(pd.date_range(r.primera_marca,r.ultima_marca,freq='h'))
    d=g.iloc[-1][['temperatura','humedad','viento_2m']]-g.iloc[0][['temperatura','humedad','viento_2m']]
    assert np.allclose(d.to_numpy(dtype=float),[r.dT_3h,r.dHR_3h,r.dV_3h],atol=1e-6)
    assert r.dT_3h>=r.limite_dT-1e-6 and r.dHR_3h<=r.limite_dHR+1e-6 and r.dV_3h>=r.limite_dV-1e-6
    for _,z in g.iterrows():
        failed=';'.join(n for n,b in [('T>11',z.temperatura>11),('HR<30',z.humedad<30),('V>2',z.viento_2m>2),('D_en_0_180',0<=z.direccion_2m<=180)] if not b)
        assert failed==z.condiciones_fallidas and failed
check('Cambios y condiciones originales fallidas comprobados por hora',True)
check('Referencia exploratoria con n suficiente',read('referencias_cambios_mes_hora').n.ge(100).all())
check('Evidencia registrada para cada ventana, sin confirmaciones forzadas',set(e.id_revision)==set(s.id_revision) and len(e)==30 and not e.confirmacion_horaria.any())
check('30 consultas efectivamente registradas',len(read('bitacora_busqueda_ventanas'))==30)
for name,cols in [('catalogo_referencia',['primera_marca','ultima_marca']),('horas_referencia',['fecha_sin_zona']),('posibles_omisiones',['primera_marca','ultima_marca','llegada']),('datos_graficos',['fecha_sin_zona']),('huecos_proximos',['marca_desconocida'])]:
    d=read(name)
    for col in cols: check('Límites temporales '+name+'.'+col,pd.to_datetime(d[col]).between(LO,HI).all())
for _,r in read('manifiesto_entradas').iterrows(): check('Fuente intacta '+r.archivo,sha(ROOT/r.archivo)==r.sha256)
audit=json.loads((OUT/'comprobaciones.json').read_text())
check('Hash del protocolo y constructor vigentes',sha(OUT/'protocolo.md')==audit['protocolo_sha256'] and sha(OUT/'construir.py')==audit['script_sha256'])
result={'resultado':'correcto','numero_controles':len(checks),'controles':checks,'limite':'Verifica procesamiento y trazabilidad; no confirma meteorología ni garantiza exhaustividad de evidencia web.'}
(OUT/'verificacion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(f'Correcto: {len(checks)} controles; 156 tramos/867 horas; 30 ventanas; fuentes intactas.')
