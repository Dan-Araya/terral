"""Síntesis reproducible posterior; no modifica protocolo, modelos ni políticas."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['MPLBACKEND']='Agg'; os.environ['MPLCONFIGDIR']='/tmp/horizontes-mpl'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
BASE=Path(__file__).resolve().parent

def complete(out):
 out=Path(out); pm=pd.read_csv(out/'tablas/metricas_probabilidades.csv'); m=pd.read_csv(out/'tablas/metricas_avisos.csv'); d=pd.read_csv(out/'tablas/distribucion_anticipacion.csv'); policies=pd.read_csv(out/'tablas/politicas.csv'); ci=pd.read_csv(out/'tablas/intervalos_pareados.csv').fillna({'politica':''})
 p=pd.read_csv(out/'predicciones_validacion.csv',parse_dates=['emision'])
 curves=[]
 for (h,bl,arm),z in p.groupby(['horizonte_h','bloque','modelo']):
  g=z.groupby('probabilidad').objetivo.agg(['sum','size']).sort_index(ascending=False); g['precision']=g['sum'].cumsum()/g['size'].cumsum(); g['recall']=g['sum'].cumsum()/z.objetivo.sum(); g=g.reset_index().rename(columns={'probabilidad':'umbral','sum':'positivos_en_empate','size':'n_en_empate'}); g['horizonte_h']=h; g['bloque']=bl; g['modelo']=arm; curves.append(g)
 pd.concat(curves,ignore_index=True).to_csv(out/'tablas/curvas_precision_recall.csv',index=False,float_format='%.17g')
 lines=['# Cierre de la etapa Huanta: INIA y Llanos de Huanta','','[Protocolo](../../protocolo.md) · [Informe completo](informe.md) · [Comandos](../../README.md)','','Se reajustaron 72 modelos externos y 144 internos por ejecución; La Laguna permanece sin entrenar. El soporte y los inicios por partición constan en tablas/particiones.csv. El mismo soporte permite comparar las cuatro variantes y los seis horizontes; las prevalencias cambian con la ventana.','', '## Aporte de Huanta','']
 c=ci[(ci.politica.eq(''))&ci.contraste.isin(['C-A','D-B'])][['horizonte_h','contraste','metrica','estimacion','p025','p975']]; lines.append(c.to_markdown(index=False,floatfmt='.5g'))
 lines += ['', 'Los signos e intervalos deben leerse junto a las tres particiones y al criterio de consistencia del informe completo. No basta un contraste favorable en AP; Brier, estabilidad y carga de avisos pueden discrepar. Los IC son marginales exploratorios, sin cobertura conjunta 95%. AP no es porcentaje de aciertos ni permite elegir una ventana ganadora sin considerar su prevalencia.', '', '## Anticipación, detección y carga de avisos','']
 for h in [1,3,6,8,12,24]:
  z=m[m.horizonte_h.eq(h)&m.bloque.eq('AGREGADO')&m.politica.str.startswith('presupuesto')]
  lines += ['',f'### Ventana de {h} horas','',z[['modelo','politica','inicios_anticipados','inicios_omitidos','inicios_evaluables','falsas_alarmas','redundantes','falsas_alarmas_por_mes','horas_bajo_aviso','proporcion_tiempo_aviso']].to_markdown(index=False,floatfmt='.4g')]
  dd=d[d.horizonte_h.eq(h)&d.bloque.eq('AGREGADO')&d.politica.str.startswith('presupuesto')]
  lines += ['', 'Distribución de anticipación efectiva entre detectados (el denominador de las fracciones ≥k del informe principal incluye también omitidos):', '', dd.to_markdown(index=False,floatfmt='.4g')]
  fig,axs=plt.subplots(1,2,figsize=(11,4))
  for arm in 'ABCD':
   zz=z[z.modelo.eq(arm)].copy(); zz['presupuesto']=zz.politica.str.replace('presupuesto_','').astype(int); zz=zz.sort_values('presupuesto'); axs[0].plot(zz.presupuesto,zz.falsas_alarmas_por_mes,'o-',label=arm)
   for policy in ['presupuesto_1','presupuesto_4']:
    row=zz[zz.politica.eq(policy)]
    if len(row):axs[1].plot([k for k in [1,3,6,8,12,24] if k<=h],[row[f'fraccion_eventos_ge_{k}h'].iloc[0] for k in [1,3,6,8,12,24] if k<=h],'o-',label=f'{arm}, {policy[-1]} FP/mes interno')
  axs[0].plot([1,8],[1,8],'k--',label='Presupuesto=tasa observada'); axs[0].set(xlabel='Presupuesto solicitado (FP/mes interno)',ylabel='FP/mes externo observado'); axs[1].set(xlabel='Anticipación mínima (h)',ylabel='Fracción de todos los eventos elegibles',ylim=(0,1.05))
  for ax in axs:ax.legend(fontsize=7); ax.grid(alpha=.2)
  fig.suptitle(f'Ventana {h} h · escenarios exploratorios'); fig.tight_layout(); fig.savefig(out/f'graficos/politicas_{h}h.png',dpi=140); plt.close(fig)
  lines += ['',f'![Presupuesto y anticipación {h}h](graficos/politicas_{h}h.png)']
 lines += ['', '## Políticas no disponibles', '', 'Cuando no existe umbral factible dentro del entrenamiento se declara no disponible. No se sustituye por cero avisos ni se combina como si tuviera evaluación en los tres bloques. Las métricas por partición de las políticas disponibles permanecen en metricas_avisos.csv. Los intervalos completos, incluidos brazos válidos cuando otro no tiene política, están en tablas/intervalos_completos.csv; corrección aditiva documentada en ../../incidencias.md.', '', policies[policies.estado.ne('congelada')].to_markdown(index=False), '', '## Soporte, incertidumbre y límites','', 'El soporte de Huanta excluye sus huecos; los recuentos por partición figuran en tablas/particiones.csv. Es una muestra pequeña para distinguir políticas y, especialmente, detectar con anticipación exactamente de 24 horas. Los entrenamientos expansivos se solapan y no se suman como eventos independientes. Las pérdidas frente a los experimentos anteriores están reconstruidas en tablas/perdidas_soporte.csv: no se comparan sus métricas sobre soportes distintos. Una ventana de 24 horas puede acertar un inicio próximo; por sí sola no prueba 24 horas de anticipación.', '', 'Cada episodio se vincula como máximo a un inicio; los siguientes avisos sobre un inicio ya usado son redundantes y se informan aparte de falsos. Las horas bajo aviso son emisiones activas evaluables, sin prolongarlas artificialmente por el horizonte. Mes equivalente=730,5 horas. Los puntos de las curvas corresponden a umbrales discretos; no se interpolan políticas. Bajar el umbral puede unir episodios y reducir detecciones bajo la correspondencia uno a uno, por lo que el recall de eventos no tiene que ser monótono. Las políticas fueron seleccionadas únicamente con OOF temporal interno; no garantizan cumplir el presupuesto futuro. Los presupuestos no se declaran aceptables ni se adopta política operacional.', '', 'Persisten las limitaciones instrumentales y temporales del protocolo: altura T/HR de INIA, latencia, posición del intervalo y zona histórica sin confirmar. El estudio refiere al criterio histórico y no demuestra mecanismo físico ni capacidad operacional.', '', '## Integridad y reproducción','']
 for name in ['verificacion_independiente.json','auditoria_adicional.json','reproduccion.json']:
  path=out/name
  if path.exists():
   obj=json.loads(path.read_text()); lines.append(f'{name}: {obj.get("resultado")}' + (f'; {obj["archivos_comparados"]} archivos comparados; diferencias: {obj["diferencias"]}.' if 'archivos_comparados' in obj else '.'))
 lines += ['', '## Alcance de esta etapa', '', 'Hipótesis previa del usuario: Huanta, al este de la zona de formación, podría registrar condiciones precursoras. No es un mecanismo demostrado. Solo sensores LLHTA, LLHHR, LLHVV2M, LLHDV2M y LLHPA a 2 m. Sin relleno con 10 m. Pisco y su extensión se conservan intactos. La comparación directa entre estaciones queda pendiente: sus soportes difieren. No se entrenó La Laguna ni horizontes 36–72 h. Véanse pérdidas por año y partición en tablas/efecto_huecos_huanta.csv y protocolo de etapa en ../../etapa_huanta/protocolo_etapa.md.']
 delta=pd.read_csv(out/'tablas/diferencias_pareadas.csv').fillna({'politica':''})
 statuses=[]
 for h in [1,3,6,8,12,24]:
  for contrast in ['B-A','C-A','D-B']:
   c=ci[ci.horizonte_h.eq(h)&ci.contraste.eq(contrast)&ci.politica.eq('')].set_index('metrica')
   z=delta[delta.horizonte_h.eq(h)&delta.contraste.eq(contrast)&delta.politica.eq('')&delta.bloque.ne('AGREGADO')]
   ap=c.loc['AP'];br=c.loc['Brier']
   good=(z[z.metrica.eq('AP')].delta>0).all() and (z[z.metrica.eq('Brier')].delta<0).all() and ap.p025>0 and br.p975<0
   bad=(z[z.metrica.eq('AP')].delta<0).all() and (z[z.metrica.eq('Brier')].delta>0).all() and ap.p975<0 and br.p025>0
   status='mejora consistente' if good else ('empeoramiento consistente' if bad else ('ausencia de evidencia de mejora' if ap.p025<=0<=ap.p975 and br.p025<=0<=br.p975 else 'incierto'))
   statuses.append(dict(horizonte_h=h,contraste=contrast,resultado=status,delta_AP=ap.estimacion,AP_p025=ap.p025,AP_p975=ap.p975,delta_Brier=br.estimacion,Brier_p025=br.p025,Brier_p975=br.p975))
 status_table=pd.DataFrame(statuses);status_table.to_csv(out/'tablas/conclusiones_consistencia.csv',index=False,float_format='%.17g')
 part=pd.read_csv(out/'tablas/particiones.csv');val=part[part.rol.eq('val')&part.horizonte_h.eq(24)]
 lines[6:6]=['## Respuestas según el criterio previo de consistencia','',status_table.to_markdown(index=False,floatfmt='.5g'),'','Soporte de validación externo (el mismo para las cuatro variantes y seis horizontes):','',val.to_markdown(index=False),'',f"Total: {int(val.n.sum())} emisiones y {int(val.inicios.sum())} inicios elegibles en las validaciones. No se suman entrenamientos expansivos.",'']
 gap=pd.read_csv(out/'tablas/efecto_huecos_huanta.csv')
 z=gap[gap.causa.eq('hueco_largo_T')&gap.horizonte_h.eq(24)&gap.ventanas_afectadas.gt(0)]
 lines += ['', '## Pérdida por el hueco largo de temperatura', '', 'LLHTA no utilizable entre 28/04/2015 11:00 y 30/04/2016 23:00: 8.845 horas de calendario. Las siguientes son pérdidas de oportunidades evaluables respecto a INIA con presión propia y futuro completo 24 h. Las causas se solapan y no se suman; la pérdida marginal mantiene disponibles los otros sensores. Detalle completo por año, rol y horizonte en efecto_huecos_huanta.csv.', '', z.to_markdown(index=False), '', 'La ausencia también reduce el entrenamiento interno, por lo que las conclusiones quedan condicionadas al soporte disponible. No se atribuye una causa instrumental ni se extrapola al período faltante. La disponibilidad de políticas está documentada por partición; un agregado solo aparece con las tres particiones disponibles.']
 (out/'cierre.md').write_text('\n\n'.join(lines)+'\n')
if __name__=='__main__':complete(Path(sys.argv[1]) if len(sys.argv)>1 else BASE/'resultados/pisco')
