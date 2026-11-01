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
 lines=['# Cierre de la primera etapa: INIA y Pisco Elqui','','[Protocolo](../../protocolo.md) · [Informe completo](informe.md) · [Comandos](../../README.md)','','Se reajustaron 72 modelos externos y 144 internos por ejecución; las otras estaciones permanecen sin entrenar. Las validaciones contienen 51.750 emisiones comunes y 79 inicios elegibles. El mismo soporte permite comparar las cuatro variantes y los seis horizontes; las prevalencias cambian con la ventana.','', '## Aporte de Pisco','']
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
 lines += ['', '## Políticas no disponibles', '', 'Cuando no existe umbral factible dentro del entrenamiento se declara no disponible. No se sustituye por cero avisos ni se combina como si tuviera evaluación en los tres bloques. Las métricas por partición de las políticas disponibles permanecen en metricas_avisos.csv. Los intervalos completos, incluidos brazos válidos cuando otro no tiene política, están en tablas/intervalos_completos.csv; corrección aditiva documentada en ../../incidencias.md.', '', policies[policies.estado.ne('congelada')].to_markdown(index=False), '', '## Soporte, incertidumbre y límites','', 'Las validaciones aportan 29, 29 y 21 inicios. Es una muestra pequeña para distinguir políticas y, especialmente, detectar con anticipación exactamente de 24 horas. Los entrenamientos expansivos se solapan y no se suman como eventos independientes. Las pérdidas frente a los experimentos anteriores están reconstruidas en tablas/perdidas_soporte.csv: no se comparan sus métricas sobre soportes distintos. Una ventana de 24 horas puede acertar un inicio próximo; por sí sola no prueba 24 horas de anticipación.', '', 'Cada episodio se vincula como máximo a un inicio; los siguientes avisos sobre un inicio ya usado son redundantes y se informan aparte de falsos. Las horas bajo aviso son emisiones activas evaluables, sin prolongarlas artificialmente por el horizonte. Mes equivalente=730,5 horas. Los puntos de las curvas corresponden a umbrales discretos; no se interpolan políticas. Bajar el umbral puede unir episodios y reducir detecciones bajo la correspondencia uno a uno, por lo que el recall de eventos no tiene que ser monótono. Las políticas fueron seleccionadas únicamente con OOF temporal interno; no garantizan cumplir el presupuesto futuro. Los presupuestos no se declaran aceptables ni se adopta política operacional.', '', 'Persisten las limitaciones instrumentales y temporales del protocolo: altura T/HR de INIA, latencia, posición del intervalo y zona histórica sin confirmar. El estudio refiere al criterio histórico y no demuestra mecanismo físico ni capacidad operacional.', '', '## Integridad y reproducción','']
 for name in ['verificacion_independiente.json','auditoria_adicional.json','reproduccion.json']:
  path=out/name
  if path.exists():
   obj=json.loads(path.read_text()); lines.append(f'{name}: {obj.get("resultado")}' + (f'; {obj["archivos_comparados"]} archivos comparados; diferencias: {obj["diferencias"]}.' if 'archivos_comparados' in obj else '.'))
 lines += ['', 'Las correcciones de implementación y la restauración acreditada de un CSV derivado se documentan en [incidencias](../../incidencias.md). Ambos manifiestos previos conservan su hash completo; modelos y métricas coinciden en las dos ejecuciones.', '', '## Continuación preparada','', 'Huanta está configurada con T/HR y V/D a 2 m y presión local, manteniendo las cuatro variantes, horizontes y políticas. No se ha ejecutado. Comandos para un encargo posterior que autorice esa etapa:', '', '```bash\npython investigacion_ceazamet/estudio_horizontes_inicio_v1/estudio.py preparar --etapa huanta --activar-etapa-pendiente\npython investigacion_ceazamet/estudio_horizontes_inicio_v1/estudio.py ejecutar --etapa huanta --activar-etapa-pendiente\npython investigacion_ceazamet/estudio_horizontes_inicio_v1/estudio.py verificar --etapa huanta --activar-etapa-pendiente\npython investigacion_ceazamet/estudio_horizontes_inicio_v1/estudio.py reproducir --etapa huanta --activar-etapa-pendiente\n```', '', 'La Laguna sin presión y la síntesis siguen pendientes.']
 (out/'cierre.md').write_text('\n\n'.join(lines)+'\n')
if __name__=='__main__':complete(Path(sys.argv[1]) if len(sys.argv)>1 else BASE/'resultados/pisco')
