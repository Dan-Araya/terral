"""Motor independiente: solo biblioteca estándar, observaciones y JSON congelado."""
import datetime as dt
import math
from .comun import BASE, HORIZONTES, SPECS, leer, sha

class EntradaInvalida(ValueError): pass

def numero(value):
    if isinstance(value,bool): return None
    try: value=float(value)
    except (TypeError,ValueError): return None
    return value if math.isfinite(value) else None

def calidad(r):
    key=(str(r.get('estacion')),str(r.get('sensor')))
    if key not in SPECS: raise EntradaInvalida('sensor_no_autorizado')
    s=SPECS[key]
    if (r.get('variable'),r.get('unidad'),numero(r.get('altura_m')))!=(s[2],s[3],s[4]):
        raise EntradaInvalida('identidad_unidad_altura_incompatible')
    avg,pct=numero(r.get('prom')),numero(r.get('porcentaje_datos'))
    good=avg is not None and pct is not None and 0<pct<=100 and s[5]<=avg<=s[6]
    if key[0]=='8':
        vals=[numero(r.get(c)) for c in ('min','prom','max')]
        good=good and all(v is not None and s[5]<=v<=s[6] for v in vals)
        if good and s[2]!='direccion': good=vals[0]<=vals[1]<=vals[2]
    return avg if good else None

def ventana(registros,emision):
    try: t=dt.datetime.fromisoformat(emision)
    except (ValueError,TypeError): raise EntradaInvalida('marca_emision_invalida')
    if t.tzinfo is not None or t.minute or t.second or t.microsecond: raise EntradaInvalida('marca_original_no_horaria_sin_zona')
    times=[t-dt.timedelta(hours=k) for k in range(6,-1,-1)]
    selected={}; reasons=[]
    for r in registros:
        try: stamp=dt.datetime.fromisoformat(r['marca_original'])
        except (KeyError,ValueError,TypeError): raise EntradaInvalida('marca_invalida')
        if stamp not in times: continue # Nunca usa información futura ni registros anteriores a t-6.
        key=(stamp,str(r.get('estacion')),str(r.get('sensor')))
        if key in selected: raise EntradaInvalida('duplicado_hora_sensor')
        selected[key]=calidad(r)
    result=[]
    for stamp in times:
        row={}
        for station,sid in SPECS:
            value=selected.get((stamp,station,sid))
            if value is None: reasons.append(f'{stamp.isoformat()}:{station}/{sid}:ausente_o_invalido')
            row[station,sid]=value
        result.append(row)
    if reasons: raise EntradaInvalida(';'.join(reasons))
    return t,result

def predictores(t,rows):
    def group(station,variables,prefix,wind=None,calendar=False):
        values={name:[r[station,sid] for r in rows] for name,sid in variables}
        direction='37' if station=='6' else '57'
        if prefix!='INIA_':
            for name,fn in [('sin_D',math.sin),('cos_D',math.cos)]:
                values[name]=[fn(math.radians(r[station,direction])) for r in rows]
        out={name:v[-1] for name,v in values.items()}
        for lag in (1,3):
            for name,v in values.items():
                out[f'{name}_lag{lag}']=v[-1-lag]; out[f'{name}_delta{lag}']=v[-1]-v[-1-lag]
        for name,v in values.items(): out[f'{name}_media_previa6']=sum(v[:-1])/6
        if wind: out['V_max_previo6']=max(values[wind][:-1])
        if calendar:
            for name,angle in [('hora',2*math.pi*t.hour/24),('ano',2*math.pi*(t.timetuple().tm_yday-1)/365.25)]:
                out[f'sin_{name}']=math.sin(angle); out[f'cos_{name}']=math.cos(angle)
        return {prefix+k:v for k,v in out.items()}
    f=group('6',[('temperatura','39'),('humedad','40'),('viento_2m','36')],'',wind='viento_2m',calendar=True)
    f.update(group('6',[('presion','VCNPA')],'INIA_'))
    f.update(group('8',[('temperatura','59'),('humedad','60'),('viento','56'),('presion','PEPA')],'PE_',wind='viento'))
    return f

def cargar_modelo():
    p=BASE/'modelos/D_v1.json'
    if sha(p)!=leer(BASE/'modelos/manifiesto.json')['D_v1.json']: raise ValueError('Modelo alterado')
    model=leer(p); names=model['orden_variables']
    if len(names)!=78 or len(set(names))!=78 or set(model['modelos'])!={str(h) for h in HORIZONTES}: raise ValueError('Esquema modelo inválido')
    for h,m in model['modelos'].items():
        if m['horizonte_h']!=int(h): raise ValueError('Horizonte incompatible')
        for key in ('media','escala','coeficientes'):
            if len(m[key])!=78 or any(numero(x) is None for x in m[key]): raise ValueError('Vector inválido')
        if any(x<=0 for x in m['escala']) or numero(m['intercepto']) is None: raise ValueError('Escala/intercepto inválido')
    return model

def probabilidades(f,model):
    if list(f)!=model['orden_variables']: raise EntradaInvalida('orden_variables_incompatible')
    values=list(f.values()); result={}
    for h,m in model['modelos'].items():
        z=m['intercepto']+sum(c*(v-a)/s for v,a,s,c in zip(values,m['media'],m['escala'],m['coeficientes']))
        result[h]=1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))
    return result

def emitir(registros,emision,*,modo='historico',adquisicion_utc=None,ahora_utc=None,fallo_adquisicion=None):
    if modo not in ('historico','actual'): raise ValueError('Modo inválido')
    model=cargar_modelo()
    output=dict(version_contrato='1.0',modo=modo,modelo=model['version'],modelo_sha256=sha(BASE/'modelos/D_v1.json'),
        estaciones=model['sensores'],hora_observacion_original=emision,adquisicion_utc=adquisicion_utc,
        convencion_temporal=model['convencion_temporal'],calidad='pendiente',completitud=False,
        frescura={'estado':'no_aplica_historico' if modo=='historico' else 'no_evaluable','edad_h':None,'max_edad_h':None},
        criterio='desconocido',elegible=False,estado=None,motivos=[],estimaciones={str(h):None for h in HORIZONTES},
        trazabilidad={'entradas_sha256':None},advertencia=model['advertencia'])
    # Hash del contenido normalizado, independiente del archivo contenedor.
    import json,hashlib
    output['trazabilidad']['entradas_sha256']=hashlib.sha256(json.dumps(registros,sort_keys=True,ensure_ascii=False,allow_nan=True).encode()).hexdigest()
    reasons=[]
    if modo=='actual':
        policy=leer(BASE/'politica_actual.json')
        output['frescura']['politica']=policy
        output['frescura']['edad_desde_adquisicion_h']=None
        if adquisicion_utc:
            try:
                current=ahora_utc or dt.datetime.now(dt.timezone.utc).isoformat()
                age=evaluar_frescura(adquisicion_utc,current,policy['max_edad_cache_adquisicion_h'])
                output['frescura']['edad_desde_adquisicion_h']=age['edad_h']
                if age['estado']=='datos_obsoletos':
                    reasons.append('datos_obsoletos'); output['frescura']['estado']='datos_obsoletos'
                elif age['estado']=='marca_futura': reasons.append('adquisicion_futura_invalida')
                output['frescura']['estado_cache']=age['estado']
            except (ValueError,TypeError): reasons.append('adquisicion_utc_invalida')
        else: reasons.append('fecha_adquisicion_pendiente')
    if fallo_adquisicion:
        reasons.insert(0,'fallo_adquisicion')
        output['detalle_fallo_adquisicion']=str(fallo_adquisicion)
    f=None
    try:
        t,rows=ventana(registros,emision)
        if modo=='historico' and t.year not in (2022,2023): raise EntradaInvalida('emision_fuera_bloque_historico_2022_2023')
        output['calidad']='valida'; output['completitud']=True
        active=rows[-1]['6','39']>11 and rows[-1]['6','40']<30 and rows[-1]['6','36']>2 and 0<=rows[-1]['6','37']<=180
        output['criterio']='activo' if active else 'inactivo'
        if active: reasons.append('evento_activo')
        f=predictores(t,rows)
    except EntradaInvalida as e:
        reasons.append('antecedentes_incompletos_o_invalidos'); output['calidad']='invalida'
        output['motivos'].append(str(e))
    if modo=='actual':
        # G1 no posee prueba documental de zona/intervalo ni latencia por sensor.
        # Ningún parámetro del llamador permite eludir este bloqueo.
        if reasons==['fecha_adquisicion_pendiente']: reasons=[]
        reasons.append('compatibilidad_temporal_pendiente')
        reasons.append('politica_frescura_pendiente')
    output['motivos']=reasons+output['motivos']
    output['estado']=reasons[0] if reasons else 'estimacion_disponible'
    if not reasons:
        output['elegible']=True; output['estimaciones']=probabilidades(f,model)
        output['trazabilidad']['predictor_desde']=(t-dt.timedelta(hours=6)).isoformat()
        output['trazabilidad']['predictor_hasta']=t.isoformat()
    return output

def evaluar_frescura(observacion_utc,ahora_utc,max_edad_h):
    """Para G2 tras confirmar conversión y latencia; jamás interpreta una marca sin zona."""
    if not math.isfinite(max_edad_h) or max_edad_h<=0: raise ValueError('Umbral explícito positivo requerido')
    a,b=map(dt.datetime.fromisoformat,(observacion_utc,ahora_utc))
    if a.utcoffset()!=dt.timedelta(0) or b.utcoffset()!=dt.timedelta(0): raise ValueError('UTC explícito requerido')
    age=(b-a).total_seconds()/3600
    return {'edad_h':age,'max_edad_h':max_edad_h,'estado':'datos_obsoletos' if age>max_edad_h else ('marca_futura' if age<0 else 'fresco')}

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(); p.add_argument('entrada'); args=p.parse_args()
    inp=leer(args.entrada)
    print(json.dumps(emitir(**inp),ensure_ascii=False,indent=2,allow_nan=False))
