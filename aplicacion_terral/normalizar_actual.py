"""Inspección estricta y local de los dos XLS controlados; no hace red."""
import datetime as dt
import io
import re
import xlrd
from .comun import BASE,SENSORES,guardar,leer,sha
from .inferencia import calidad,ventana,EntradaInvalida,emitir
LABELS={'temperatura':'Temperatura del Aire','humedad':'Humedad Relativa','viento':'Velocidad de Viento','viento_2m':'Velocidad de Viento','direccion':'Dirección de viento','direccion_2m':'Dirección de viento','presion':'Presión Atmosférica'}
FIELDS={'Min':'min','Prom':'prom','Max':'max','%Datos':'porcentaje_datos'}

def reparar(s):
    try: return s.encode('latin1').decode('utf8')
    except UnicodeError: return s

def inspeccionar(evidence):
    evidence=BASE/'evidencia'/evidence
    plan=leer(evidence/'plan.json'); records=[]; schema=[]; summaries=[]
    for station in ('6','8'):
        folder=evidence/station; p=folder/'original.xls'
        manifest=leer(evidence/'manifiesto.json')
        if sha(p)!=manifest[f'{station}/original.xls']: raise ValueError('Original alterado')
        request=leer(folder/'solicitud.json')
        assert request['estacion']==station
        assert [v for k,v in request['campos'] if k=='s_cod[]']==[s[1] for s in SENSORES if s[0]==station]
        acquisition=leer(folder/'get.http.json')['finished_utc']
        book=xlrd.open_workbook(p,logfile=io.StringIO())
        if len(book.sheets())!=1: raise ValueError('Esquema no previsto')
        sheet=book.sheet_by_index(0)
        assert sheet.cell_value(0,1)=={'6':'Vicuña','8':'Pisco Elqui'}[station]
        assert sheet.cell_value(1,1)==f"[{plan['fecha_inicio']},{plan['fecha_fin']}]"
        expected=[s for s in SENSORES if s[0]==station]; columns={}
        for col in range(1,sheet.ncols):
            raw=sheet.cell_value(3,col); label=re.sub(r"(?:Ã.|Â.)+",lambda m: reparar(m.group()),raw)
            m=re.fullmatch(r'\[(Min|Prom|Max|%Datos)\]\s*(.*?)\[([\d.]+)m\]',label)
            if not m: raise ValueError('Encabezado inesperado: '+raw)
            field,desc,height=m.groups()
            matches=[s for s in expected if float(height)==s[4] and desc==('' if field=='%Datos' else s[3]+' ')+LABELS[s[2]]]
            if len(matches)!=1: raise ValueError('Identidad/altura/unidad ambigua: '+raw)
            s=matches[0]; key=(s[1],FIELDS[field])
            if key in columns: raise ValueError('Campo duplicado')
            columns[key]=col
            schema.append(dict(estacion=station,sensor=s[1],campo=FIELDS[field],encabezado_original=raw,unidad=s[3],altura_m=s[4],columna_excel=col+1))
        assert set(columns)=={(s[1],field) for s in expected for field in FIELDS.values()}
        seen=set()
        for row in range(4,sheet.nrows):
            label=sheet.cell_value(row,0)
            if not isinstance(label,str) or not re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:00:00',label): continue
            assert plan['fecha_inicio']<=label[:10]<=plan['fecha_fin'] and label not in seen
            seen.add(label)
            for s in expected:
                values={field:sheet.cell_value(row,columns[s[1],field]) for field in FIELDS.values()}
                # No se aceptan números codificados como texto en el XLS.
                for field,value in values.items():
                    if value!='' and sheet.cell_type(row,columns[s[1],field])!=xlrd.XL_CELL_NUMBER: raise ValueError('Tipo XLS incompatible')
                records.append(dict(estacion=station,sensor=s[1],variable=s[2],unidad=s[3],altura_m=s[4],marca_original=label,
                    **values,adquisicion_utc=acquisition,procedencia=dict(archivo_original=str(p.relative_to(BASE)),sha256_original=sha(p),hoja=sheet.name,fila_excel=row+1)))
        assert len(seen)==24
        for s in expected:
            group=[r for r in records if r['estacion']==station and r['sensor']==s[1]]
            valid=[r for r in group if calidad(r) is not None]
            summaries.append(dict(estacion=station,sensor=s[1],horas_etiquetadas=len(group),horas_validas=len(valid),
                primera_valida=min((r['marca_original'] for r in valid),default=None),ultima_valida=max((r['marca_original'] for r in valid),default=None),
                ceros_validos=sum(calidad(r)==0 for r in valid),pct_cero=sum(r['porcentaje_datos']==0 for r in group)))
    windows=[]
    for mark in sorted({r['marca_original'] for r in records}):
        try: ventana(records,mark); windows.append(mark)
        except EntradaInvalida: pass
    report=dict(estado='formato_verificado_compatibilidad_pendiente',esquemas=schema,sensores=summaries,
        ventanas_completas=windows,registro_adquisicion_utc={station:leer(evidence/station/'get.http.json')['finished_utc'] for station in ('6','8')},
        zona_historica_confirmada=False,posicion_intervalo_confirmada=False,continuidad_instrumental_confirmada=False,
        nota='La etiqueta futura o %Datos=0 se conserva como faltante, nunca como valor observado. Los códigos se vinculan por solicitud+menú oficial+descriptor/altura único del XLS, no están escritos en el encabezado XLS.')
    guardar(evidence/'observaciones_normalizadas.json',records)
    guardar(evidence/'contraste.json',report)
    if windows:
        mark=windows[-1]; t=dt.datetime.fromisoformat(mark)
        selected=[r for r in records if t-dt.timedelta(hours=6)<=dt.datetime.fromisoformat(r['marca_original'])<=t]
        inp=dict(registros=selected,emision=mark,modo='actual',adquisicion_utc=max(r['adquisicion_utc'] for r in selected),ahora_utc=leer(evidence/'8/get.http.json')['finished_utc'])
        guardar(BASE/'ejemplos/actual_no_habilitado_entrada.json',inp)
        guardar(BASE/'ejemplos/actual_no_habilitado_salida.json',emitir(**inp))
    guardar(evidence/'manifiesto_derivados.json',{name:sha(evidence/name) for name in ('observaciones_normalizadas.json','contraste.json')})
    print({'sensores':len(summaries),'ventanas_completas':windows,'inferencias_actuales_emitidas':0})
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('evidencia'); inspeccionar(p.parse_args().evidencia)
