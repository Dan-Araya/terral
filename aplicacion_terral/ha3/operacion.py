"""Corte causal, selección nominal y ledger HA-3. Sin red ni entrenamiento."""
import datetime as dt
import hashlib
import json
import uuid
from ..comun import BASE, SPECS, HORIZONTES, leer, sha
from ..inferencia import calidad, ventana, predictores, probabilidades, cargar_modelo, evaluar_frescura
from ..g2 import almacen as a
from ..habilitacion_actual.preparacion import ultima_ventana_comun, utc, canon

POLITICA = leer(BASE/'ha3/politica.json')
INCERTIDUMBRES = [
    'Zona y posición del intervalo sin confirmar; edad física desconocida.',
    'Calidad utilizable no equivale a dato definitivo; las observaciones pueden revisarse.',
    'Correspondencia histórica, continuidad instrumental y alturas pendientes (INIA T/HR 1,5/2 m).',
    'Evaluación retrospectiva no demuestra desempeño con datos provisionales disponibles al emitir.',
    'Modelos independientes sin recalibración ni coherencia impuesta entre horizontes.'
]
TABLAS = {
 'ha3_emisiones': 'id TEXT PRIMARY KEY, clave TEXT NOT NULL UNIQUE, ciclo TEXT NOT NULL REFERENCES ciclos(id), utc TEXT NOT NULL, referencia TEXT NOT NULL, anterior TEXT REFERENCES ha3_emisiones(id), documento TEXT NOT NULL',
 'ha3_evaluaciones': 'id TEXT PRIMARY KEY, ciclo TEXT NOT NULL REFERENCES ciclos(id), utc TEXT NOT NULL, documento TEXT NOT NULL',
 'ha3_publicaciones': 'ciclo TEXT PRIMARY KEY REFERENCES ciclos(id), utc TEXT NOT NULL, documento TEXT NOT NULL'
}


def migrar(db):
    for name, schema in TABLAS.items():
        db.execute(f'CREATE TABLE IF NOT EXISTS {name} ({schema})')
        for op in ('UPDATE', 'DELETE'):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS {name}_no_{op} BEFORE {op} ON {name} BEGIN SELECT RAISE(ABORT, 'registro inmutable'); END")


def existe(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE name='ha3_emisiones'").fetchone() is not None


def registros_al_corte(db, corte, hasta_ciclo=None):
    cut = utc(corte)
    # Orden de versiones de almacenamiento; compara instantes, no cadenas con formatos UTC distintos.
    rows = db.execute('''SELECT o.*, r.id rid, r.utc, r.procedencia, r.adquisicion, q.ciclo
        FROM recepciones r JOIN observaciones o ON o.id=r.observacion
        JOIN adquisiciones q ON q.id=r.adquisicion
        JOIN ciclos c ON c.id=q.ciclo JOIN cierres x ON x.ciclo=c.id
        WHERE x.estado='completo' AND c.rowid<=COALESCE(
          (SELECT rowid FROM ciclos WHERE id=?),9223372036854775807)
        ORDER BY o.version,r.id''', (hasta_ciclo,))
    latest = {}
    for row in rows:
        if utc(row['utc']) >= cut:  # Exclusivamente recibidas ANTES del corte.
            continue
        key = row['estacion'], row['sensor'], row['marca']
        latest[key] = dict(json.loads(row['contenido']), adquisicion_utc=row['utc'],
            procedencia=json.loads(row['procedencia']), version=row['version'],
            observacion_id=row['id'], recepcion_id=row['rid'], adquisicion_id=row['adquisicion'],
            ciclo_recepcion=row['ciclo'], contenido_sha256=row['hash'])
    return sorted(latest.values(), key=lambda r: (r['marca_original'],r['estacion'],r['sensor']))


def avance_sensores(db, corte, hasta_ciclo=None):
    cut=utc(corte)
    history={k:dict(estacion=k[0],sensor=k[1],ultima_marca_original=None,
                   ultimo_avance_utc=None,ciclos_sin_avance=0) for k in SPECS}
    seen={k:set() for k in SPECS}
    rows=db.execute('''SELECT o.estacion,o.sensor,o.marca,o.contenido,r.utc,r.id,q.ciclo
      FROM recepciones r JOIN observaciones o ON o.id=r.observacion
      JOIN adquisiciones q ON q.id=r.adquisicion
      JOIN ciclos c ON c.id=q.ciclo JOIN cierres x ON x.ciclo=c.id
      WHERE x.estado='completo' AND c.rowid<=COALESCE(
        (SELECT rowid FROM ciclos WHERE id=?),9223372036854775807)
      ORDER BY julianday(r.utc),r.id''', (hasta_ciclo,))
    for r in rows:
        if utc(r['utc']) >= cut: continue
        key=r['estacion'],r['sensor']; state=history[key]
        meaningful=any(json.loads(r['contenido'])[f] != '' for f in ('min','prom','max'))
        if meaningful and (state['ultima_marca_original'] is None or r['marca']>state['ultima_marca_original']):
            state.update(ultima_marca_original=r['marca'],ultimo_avance_utc=r['utc'])
            seen[key]={r['ciclo']}
        elif state['ultimo_avance_utc']:
            seen[key].add(r['ciclo'])
    for key,state in history.items():
        state['ciclos_sin_avance']=max(0,len(seen[key])-1)
        state['horas_desde_avance']=((cut-utc(state['ultimo_avance_utc'])).total_seconds()/3600
                                     if state['ultimo_avance_utc'] else None)
    return list(history.values())


def evaluar(db, corte, fallo=None, *, records=None, avances=None):
    records=registros_al_corte(db,corte) if records is None else records
    candidate=ultima_ventana_comun(records)
    selected=candidate['registros'] if candidate else []
    reasons=[]
    if fallo: reasons.append('fallo_adquisicion')
    if not candidate: reasons.append('antecedentes_incompletos_o_invalidos')
    caches=[evaluar_frescura(r['adquisicion_utc'],corte,2) for r in selected]
    if any(c['estado']!='fresco' for c in caches): reasons.append('datos_obsoletos')
    active=False
    if candidate:
        _,rows=ventana(selected,candidate['referencia_original'])
        r=rows[-1]
        active=r['6','39']>11 and r['6','40']<30 and r['6','36']>2 and 0<=r['6','37']<=180
        if active: reasons.append('evento_activo')
    out=dict(politica='HA-3',politica_sha256=sha(BASE/'ha3/politica.json'), modo='actual_experimental',
        corte_disponibilidad_utc=corte, estado=reasons[0] if reasons else 'estimacion_disponible',
        motivos=reasons, elegible=not reasons, calidad='valida' if candidate else 'invalida',
        completitud=bool(candidate), criterio='activo' if active else ('inactivo' if candidate else 'desconocido'),
        referencia_nominal=candidate['referencia_original'] if candidate else None,
        desde_nominal=candidate['desde_original'] if candidate else None,
        zona=None,intervalo_fisico=None,edad_fisica_h=None,
        edad_recepcion_max_h=max((c['edad_h'] for c in caches),default=None),
        avances=avance_sensores(db,corte) if avances is None else avances,incertidumbres=INCERTIDUMBRES,
        ultimas_marcas=[dict(estacion=s,sensor=sid,marca_original=max((r['marca_original'] for r in records
            if (r['estacion'],r['sensor'])==(s,sid) and any(r[f]!='' for f in ('min','prom','max'))),default=None)) for s,sid in SPECS])
    return out,selected


def procesar(db, ciclo, corte=None, fallo=None):
    corte=corte or a.ahora(); utc(corte)
    migrar(db)
    # Solo ciclos cerrados; un fallo/interrupción nunca permite emitir desde caché previa.
    closed=db.execute('SELECT * FROM cierres WHERE ciclo=?',(ciclo,)).fetchone()
    if closed is None: raise ValueError('Ciclo sin cerrar')
    if utc(closed['fin_utc'])>utc(corte): raise ValueError('Cierre posterior al corte')
    if closed['estado']!='completo': fallo=fallo or closed['estado']
    out,selected=evaluar(db,corte,fallo,records=registros_al_corte(db,corte,ciclo),
                         avances=avance_sensores(db,corte,ciclo))
    out['emisiones_nuevas']=[]
    if out['elegible']:
        model=cargar_modelo(); model_hash=sha(BASE/'modelos/D_v1.json')
        t,rows=ventana(selected,out['referencia_nominal'])
        probs=probabilidades(predictores(t,rows),model)
        for h in HORIZONTES:
            key=identidad(selected,out['referencia_nominal'],h)
            if db.execute('SELECT 1 FROM ha3_emisiones WHERE clave=?',(key,)).fetchone(): continue
            prev=db.execute('SELECT id FROM ha3_emisiones WHERE referencia=? AND json_extract(documento,\'$.horizonte_nominal_h\')=? ORDER BY rowid DESC LIMIT 1', (out['referencia_nominal'],h)).fetchone()
            eid='ha3-'+uuid.uuid4().hex
            doc=dict(out, id=eid,clave_idempotencia=key,emision_utc=corte,ciclo=ciclo,
                modelo=model['version'],modelo_sha256=model_hash,horizonte_nominal_h=h,
                probabilidad=probs[str(h)],revision_de=prev['id'] if prev else None,
                entradas=selected,transformaciones='Motor G1 congelado: ventana, predictores, probabilidades',
                motor_sha256=sha(BASE/'inferencia.py'))
            doc.pop('emisiones_nuevas')
            db.execute('INSERT INTO ha3_emisiones VALUES(?,?,?,?,?,?,?)',
                (eid,key,ciclo,corte,out['referencia_nominal'],doc['revision_de'],canon(doc)))
            out['emisiones_nuevas'].append(eid)
    db.execute('INSERT INTO ha3_evaluaciones VALUES(?,?,?,?)',('eval-'+uuid.uuid4().hex,ciclo,corte,canon(out)))
    if closed['estado']=='completo' and not fallo:
        publicar(db,ciclo,corte,out)
    return out


def publicar(db,ciclo,corte,state):
    # El límite de ciclo y de recepción fija la versión publicada para siempre.
    # Se confirma con cierre, evaluación y ledger en la transacción del escritor.
    records=registros_al_corte(db,corte,ciclo)
    selected=ultima_ventana_comun(records)
    emissions={}
    if state['elegible']:
        if not selected or selected['referencia_original']!=state['referencia_nominal']:
            raise ValueError('Publicación sin la ventana evaluada')
        for h in HORIZONTES:
            row=db.execute('SELECT documento FROM ha3_emisiones WHERE clave=?',
                (identidad(selected['registros'],state['referencia_nominal'],h),)).fetchone()
            if row: emissions[str(h)]=publica(json.loads(row['documento']))
        if len(emissions)!=len(HORIZONTES):
            raise ValueError('Publicación elegible sin ledger completo')
    db.execute('INSERT OR IGNORE INTO ha3_publicaciones VALUES(?,?,?)',
        (ciclo,corte,canon(dict(estado=state,emisiones=emissions,
                              avances=avance_sensores(db,corte,ciclo)))))


def preparar_publicacion(db):
    """Migración sin inferencia ni emisiones nuevas: usa una evaluación ya confirmada."""
    migrar(db)
    if db.execute('SELECT 1 FROM ha3_publicaciones LIMIT 1').fetchone(): return
    row=db.execute('''SELECT e.* FROM ha3_evaluaciones e
        JOIN cierres x ON x.ciclo=e.ciclo JOIN ciclos c ON c.id=e.ciclo
        WHERE x.estado='completo' ORDER BY c.rowid DESC,e.rowid DESC LIMIT 1''').fetchone()
    if row: publicar(db,row['ciclo'],row['utc'],json.loads(row['documento']))


def cerrar(db,ciclo,fallo=None,current=None):
    # Conserva evaluación G2 y añade HA-3 dentro de la misma transacción del ciclo.
    current=current or a.ahora()
    a.cerrar(db,ciclo,fallo,current)
    return procesar(db,ciclo,current,fallo)


def publica(doc):
    return {k:v for k,v in doc.items() if k not in ('entradas','transformaciones','avances','ultimas_marcas')}


def panel(db,current):
    last=db.execute('SELECT c.id,c.inicio_utc,x.estado,x.fin_utc FROM ciclos c LEFT JOIN cierres x ON x.ciclo=c.id ORDER BY c.rowid DESC LIMIT 1').fetchone()
    failed=db.execute("SELECT ciclo,fin_utc,estado FROM cierres WHERE estado!='completo' ORDER BY rowid DESC LIMIT 1").fetchone()
    has_publications=db.execute("SELECT 1 FROM sqlite_master WHERE name='ha3_publicaciones'").fetchone()
    pub=db.execute('''SELECT p.* FROM ha3_publicaciones p JOIN ciclos c ON c.id=p.ciclo
                     ORDER BY c.rowid DESC LIMIT 1''').fetchone() if has_publications else None
    records=registros_al_corte(db,pub['utc'],pub['ciclo']) if pub else []
    saved=json.loads(pub['documento']) if pub else {}
    advances=saved.get('avances',[])
    for sensor in advances:
        if sensor['ultimo_avance_utc']:
            sensor['horas_desde_avance']=(utc(current)-utc(sensor['ultimo_avance_utc'])).total_seconds()/3600
    state,_=evaluar(db,current,records=records,avances=advances)
    state['corte_disponibilidad_utc']=pub['utc'] if pub else None
    state['evaluacion_frescura_utc']=current
    if not pub:
        state.update(estado='sin_adquisiciones',elegible=False,motivos=['sin_adquisiciones'])
    latest=saved.get('emisiones',{})
    available=len(latest)==len(HORIZONTES) and state['elegible'] and saved['estado']['elegible']
    groups=[]
    for station,sensor in SPECS:
        group=[r for r in records if (r['estacion'],r['sensor'])==(station,sensor)]
        meaningful=[r for r in group if any(r[k]!='' for k in ('min','prom','max'))]
        last_row=max(meaningful,key=lambda r:r['marca_original'],default=None)
        valid=max((r for r in meaningful if calidad(r) is not None),key=lambda r:r['marca_original'],default=None)
        groups.append(dict(estacion=station,sensor=sensor,
            ultima=a.publica(last_row,current) if last_row else None,
            ultima_valida=a.publica(valid,current) if valid else None,
            filas_vacias=len(group)-len(meaningful)))
    mark=max((r['marca_original'] for r in records if any(r[k]!='' for k in ('min','prom','max'))),default='')
    return dict(estado=state,estimacion=latest if available else None,
                ultimo_resultado_registrado=latest or None,
                publicacion=dict(ciclo=pub['ciclo'],cierre_utc=pub['utc']) if pub else None,
                operacion=dict(ultimo_ciclo=dict(last) if last else None,
                    ultimo_fallo=dict(failed) if failed else None,
                    estado_escritor=('sin_cierre' if last['estado'] is None else last['estado']) if last else 'sin_ciclos'),
                observaciones=groups,
                series=[a.publica(r,current) for r in records if r['marca_original'].startswith(mark[:10]) and r['marca_original']<=mark],
                historial=historial(db),
                version='HA-3',modo='actual_experimental')


def historial(db, antes=None, limite=120):
    if not existe(db): return dict(emisiones=[],siguiente_antes=None)
    rows=db.execute('SELECT rowid,documento FROM ha3_emisiones WHERE rowid<? ORDER BY rowid DESC LIMIT ?',
                    (antes or 2**63-1,limite)).fetchall()
    return dict(emisiones=[publica(json.loads(r['documento'])) for r in rows],
                siguiente_antes=rows[-1]['rowid'] if len(rows)==limite else None)


def identidad(selected, referencia, horizonte):
    # No incluye recepciones ni contenedor: no rejuvenecer entradas idénticas.
    content=[{k:r[k] for k in ('observacion_id','version','contenido_sha256','marca_original','estacion','sensor')} for r in selected]
    return hashlib.sha256(canon(dict(ventana=referencia,entradas=content,
        modelo=sha(BASE/'modelos/D_v1.json'),horizonte=horizonte,
        politica=sha(BASE/'ha3/politica.json'))).encode()).hexdigest()
