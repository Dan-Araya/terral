#!/usr/bin/env python3
"""Resúmenes descriptivos y cierre, sin nuevos ajustes ni decisiones del diseño."""
import os,sys,json,hashlib
os.environ['MPLCONFIGDIR']='/tmp/laguna-v1-mpl'; sys.modules['numexpr']=None
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
T=OUT/'tablas'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def table(d):
 def f(v): return f'{v:.7g}' if isinstance(v,(float,np.floating)) else str(v)
 return '| '+' | '.join(d.columns)+' |\n| '+' | '.join(['---']*len(d.columns))+' |\n'+'\n'.join('| '+' | '.join(f(v) for v in row)+' |' for row in d.itertuples(index=False,name=None))+'\n'
pred=pd.read_csv(OUT/'predicciones_validacion.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
parts=pd.read_csv(T/'particiones.csv'); extra=pd.read_csv(T/'elegibilidad_adicional.csv').fillna({'id_inicio_objetivo':''})
support=pd.read_csv(T/'soporte_potencial_y_perdidas.csv')
ci=pd.read_csv(T/'intervalos_pareados.csv').fillna({'politica':''})
members=pd.read_csv(T/'ejemplos_comunes.csv').fillna({'id_inicio_objetivo':''})
def ids(d,c): return {v for vals in d[c] for v in vals.split('|') if v}
rows=[]
for h in [1,3]:
 d=pred[pred.horizonte_h.eq(h)&pred.modelo.eq('A')]; base=extra[extra.horizonte_h.eq(h)&extra.rol.eq('validacion')]
 rows.append({'horizonte_h':h,'horas_elegibles_validacion':len(d),'ejemplos_positivos':int(d.objetivo.sum()),'inicios_distintos':len(ids(d,'id_inicio_objetivo')),'base_INIA_elegible':len(base),'horas_excluidas_adicionales':int(base.motivo_primario.ne('incluida').sum()),'inicios_sin_oportunidad_por_exclusion':len(ids(base,'id_inicio_objetivo')-ids(d,'id_inicio_objetivo'))})
summary=pd.DataFrame(rows); summary.to_csv(T/'soporte_validacion_agregado.csv',index=False)
reasons=[]
for keys,d in extra.groupby(['horizonte_h','bloque','rol']):
 for c in [c for c in extra if c.endswith('ventana_incompleta')]:
  bad=d[c].astype(bool)
  reasons.append(dict(zip(['horizonte_h','bloque','rol'],keys),motivo=c,horas=int(bad.sum()),positivos=int(d.loc[bad,'objetivo'].sum()),inicios_afectados=len(ids(d.loc[bad],'id_inicio_objetivo'))))
r=pd.DataFrame(reasons); r.to_csv(T/'exclusiones_adicionales_resumen.csv',index=False)
# Aggregate AP/Brier and paired differences already calculated by the original bootstrap.
ci[ci.politica.eq('')].to_csv(T/'metricas_y_diferencias_agregadas.csv',index=False)
cov=pd.read_csv(T/'cobertura_anual_laguna.csv')
fig,axs=plt.subplots(1,2,figsize=(13,4),layout='constrained')
pivot=cov.assign(cobertura=100*cov.utilizables/cov.horas_calendario).pivot(index='variable',columns='ano',values='cobertura')
im=axs[0].imshow(pivot,aspect='auto',vmin=0,vmax=100,cmap='viridis')
axs[0].set_xticks(range(len(pivot.columns)),pivot.columns,rotation=45); axs[0].set_yticks(range(len(pivot)),pivot.index); axs[0].set_title('La Laguna: datos utilizables por año'); fig.colorbar(im,ax=axs[0],label='% horas del calendario')
z=support[support.horizonte_h.eq(1)&support.rol.eq('validacion')&support.brazo_potencial.eq('A')]
axs[1].bar(z.bloque,z.base_elegible_A,label='INIA básica elegible',color='#aaa'); axs[1].bar(z.bloque,z.comun_4_brazos,label='Soporte común sin presión Laguna',color='#0072B2'); axs[1].set(ylabel='Horas',title='Emisiones de validación · horizonte 1 h'); axs[1].legend(fontsize=8)
fig.savefig(OUT/'graficos/cobertura_y_soporte.png',dpi=160,bbox_inches='tight'); plt.close(fig)
if '--solo-tablas' in sys.argv: raise SystemExit('Resúmenes y figura descriptiva guardados.')
lines=['','## Diagnósticos adicionales y cierre','','Validación agregada sin duplicar bienios (no se suman entrenamientos expansivos):','',table(summary),'','Motivos adicionales no excluyentes por partición/rol están en exclusiones_adicionales_resumen.csv; las exclusiones básicas por estado, objetivo, antecedentes y purgas constan separadamente en exclusiones_resumen.csv. El detalle hora a hora permite reconstruir la causa primaria. Los huecos de presión complementaria no intervienen en ninguno de esos conteos.','','Sensores utilizados, ceros válidos y máscara:','',table(pd.read_csv(T/'sensores_laguna.csv')),'','![Cobertura y soporte](graficos/cobertura_y_soporte.png)','','Las verificaciones se ejecutan con verificar.py (etiquetas, soporte, fronteras/purgas, escalas y probabilidades, AP/Brier/calibración e IC horarios), verificar_avisos.py (grupos completos, correspondencias, métricas y todos los IC de avisos), verificar_huecos.py (cobertura, huecos y efecto por sensor), verificar_calidad_corregida.py (lectura separada, identidad/altura/unidad, máscara y aplicación a todas las ventanas) y verificar_sin_presion.py (whitelist y contrafactual de presión sintética ausente/constante/arbitraria sin consultar LAGELPA). No se impuso una cantidad de comprobaciones. Comparten fuentes derivadas y algunas funciones de ingestión; no certifican exactitud instrumental ni ausencia absoluta de errores.']
for name in ['verificacion.json','verificacion_independiente.json','verificacion_avisos.json','verificacion_huecos.json','verificacion_calidad.json','verificacion_sin_presion.json','auditoria_metodo.json','reproduccion.json']:
 rec=json.loads((OUT/name).read_text()); assert rec['resultado']=='conforme'; lines+=['',f'{name}: conforme.']
rep=json.loads((OUT/'reproduccion.json').read_text()); lines+=['',f"La repetición completa reajustó 24 modelos y reprodujo exactamente {rep['n_archivos_identicos']} archivos deterministas por SHA-256. El inventario conservacion_previa.json y los hashes antes/después confirman conservación del catálogo, fuentes y experimentos anteriores. Se guardan todos los resultados favorables y desfavorables, sin elegir umbral. Las conclusiones se restringen al criterio histórico 2013–2023."]
lines += ['', 'Incidencia de verificación: la versión inicial verificar_calidad.py suponía 96.408 filas por sensor. La tabla de La Laguna materializa 92.688 desde 2013-06-05; se conserva el fallo y se usa verificar_calidad_corregida.py, con trazabilidad en correccion_verificador.json e incidencias_ejecucion.md. La corrección comprueba filas existentes y todas las marcas usadas sin cambiar máscaras, soporte o resultados. Los gráficos de avisos se redibujan con una leyenda para la rejilla completa para evitar rótulos superpuestos; sin cambios numéricos.']
p=OUT/'informe.md'; text=p.read_text(); marker='\n## Diagnósticos adicionales y cierre'; text=text.split(marker)[0]; p.write_text(text+'\n'.join(lines)+'\n')
files=[{'archivo':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifiesto_entregables.json' and not p.name.endswith('.log')]
(OUT/'manifiesto_entregables.json').write_text(json.dumps({'archivos':files,'limites':'Excluye este propio manifiesto y logs que pueden seguir abiertos; hashes de fuentes y conservación se registran por separado.'},ensure_ascii=False,indent=2)+'\n')
print(table(summary)); print('Informe, resúmenes y manifiesto final guardados.')
