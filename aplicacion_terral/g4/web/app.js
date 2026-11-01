'use strict';
const content = document.querySelector('#content');
let mode = 'actual', caseId = 'ordinario', horizon = 6, data, sequence = 0, revealed = false, variable = '2', station = '6';
const stations = {'6':'INIA · Vicuña','8':'Pisco Elqui'};
const names = {temperatura:'Temperatura',humedad:'Humedad relativa',viento_2m:'Velocidad del viento',viento:'Velocidad del viento',direccion_2m:'Dirección del viento',direccion:'Dirección del viento',presion:'Presión local'};
const fmt = (n, digits=2) => Number(n).toLocaleString('es-CL',{maximumFractionDigits:digits,minimumFractionDigits:digits});
const esc = x => String(x ?? 'No disponible').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const mark = s => s ? esc(s.replace('T',' ')) : 'No disponible';
const labels = {antecedentes_incompletos_o_invalidos:'Antecedentes incompletos o inválidos',compatibilidad_temporal_pendiente:'Compatibilidad temporal pendiente',politica_frescura_pendiente:'Frescura física pendiente',fallo_adquisicion:'Último ciclo fallido o interrumpido',datos_obsoletos:'Caché antigua',evento_activo:'Evento activo',sin_adquisiciones:'Sin adquisiciones',estimacion_disponible:'Estimación disponible'};
const human = s => labels[s] || String(s || 'No disponible').replaceAll('_',' ');
async function get(url) {const r = await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('No se pudo leer el almacén local.');return r.json();}
// También admite HTML anterior que haya sido recibido antes de la publicación.
document.body?.classList.add('compact');
const oldHero=document.querySelector('.hero');
if(oldHero)oldHero.outerHTML='<section class="intro"><h1>Observatorio del terral</h1><p>Estimaciones y observaciones meteorológicas del Valle del Elqui.</p></section>';
document.querySelector('.workspace-head')?.remove();
document.querySelector('.method-link')?.remove();
document.querySelector('.local-tag')?.remove();
let readFailed=false;
async function load(){
 const request=++sequence;
 content.setAttribute('aria-busy','true');
 try{
  const result=await get('/api/actual');
  if(request!==sequence)return;
  // Una sola respuesta compuesta: nunca mezclar publicaciones ni adelantar observaciones.
  data=result;readFailed=false;render();
 }catch(e){
  if(request!==sequence)return;
  readFailed=true;
  if(data)render();
  else {content.innerHTML='<div class="error"><h2>Estimación no disponible</h2><p>No se pudieron leer los datos.</p><button class="button" id="retry">Volver a leer</button></div>';document.querySelector('#retry').onclick=load;}
 }finally{if(request===sequence)content.setAttribute('aria-busy','false');}
}
function metric(r,group){if(!r)return `<div class="metric"><span class="label">Sensor ${esc(group.sensor)}</span><strong class="invalid">Sin datos</strong><p class="small">${group.filas_vacias || 0} filas vacías</p></div>`;
const valid=r.calidad==='valida';return `<div class="metric"><span class="label">${names[r.variable] || esc(r.variable)}</span><strong class="${valid?'':'invalid'}">${valid?fmt(r.prom):'Dato inválido'}</strong>${valid?`<span class="unit">${esc(r.unidad)}</span>`:''}<details><summary>Sensor ${esc(r.sensor)} · ${esc(r.altura_m)} m · ${valid?'válido':'inválido'}</summary><dl><dt>Marca original · sin zona confirmada</dt><dd>${mark(r.marca_original)}</dd><dt>Mínimo / promedio / máximo (${esc(r.unidad)})</dt><dd>${esc(r.min)} / ${esc(r.prom)} / ${esc(r.max)}</dd><dt>Cobertura reportada</dt><dd>${esc(r.porcentaje_datos)} %</dd>${r.adquisicion_utc?`<dt>Recepción UTC</dt><dd>${mark(r.adquisicion_utc)}</dd><dt>Edad de caché al consultar</dt><dd>${fmt(r.cache.edad_h)} h · ${r.cache.estado==='fresco'?'dentro de 2 h':'antigua'}. Edad física desconocida.</dd><dt>Versión</dt><dd>${esc(r.version)}</dd>`:'<dt>Uso histórico</dt><dd>Antecedente del modelo. Marca nominal conservada.</dd>'}${group?`<dt>Filas vacías almacenadas</dt><dd>${group.filas_vacias}</dd>${!valid && group.ultima_valida?`<dt>Última válida anterior (no sustituye la última)</dt><dd>${esc(group.ultima_valida.prom)} ${esc(r.unidad)} · ${mark(group.ultima_valida.marca_original)}</dd>`:''}`:''}</dl></details></div>`;}
function stationCards(rows,groups=null){return `<div class="stations">${['6','8'].map(s=>{const rs=rows.filter(r=>r.estacion===s);const ms=groups?groups.filter(g=>g.estacion===s).map(g=>metric(g.ultima,g)).join(''):rs.map(r=>metric(r,null)).join('');const marks=[...new Set(rs.map(r=>r.marca_original))];return `<article class="station"><h4><span class="dot ${s==='8'?'pisco':''}"></span>${stations[s]}</h4><p class="station-note">${marks.length?`Última marca: ${mark(marks.sort().at(-1))} · sin zona confirmada`:'Sin observaciones disponibles'}</p><div class="metrics">${ms}</div></article>`;}).join('')}</div>`;}
function graphs(rows){const variables=[['Temperatura','°C',r=>r.variable==='temperatura'],['Humedad relativa','%',r=>r.variable==='humedad'],['Velocidad del viento','m/s',r=>r.variable.startsWith('viento')],['Presión INIA','hPa',r=>r.variable==='presion'&&r.estacion==='6'],['Presión Pisco','hPa',r=>r.variable==='presion'&&r.estacion==='8']];const [title,unit,filter]=variables[Number(variable)];return `<section class="chart-panel" aria-label="Gráfico de observaciones"><div class="card-heading"><h3>Observaciones</h3><label class="sr-only" for="variable">Variable del gráfico</label><select id="variable">${variables.map(([name],i)=>`<option value="${i}" ${String(i)===variable?'selected':''}>${name}</option>`).join('')}</select></div><p class="small">${mode==='historico'?'Siete horas de antecedentes':'Último día almacenado'} · promedios horarios</p>${chart(title,unit,rows.filter(filter))}<p class="chart-note">Marcas originales sin zona confirmada. Huecos sin interpolación. Presiones locales por separado.</p></section>`;}
function chart(title,unit,rows){const valid=rows.filter(r=>r.calidad==='valida' && r.prom!=null && r.prom!=='' && Number.isFinite(Number(r.prom)));if(!valid.length)return `<article class="chart"><h4>${title} · ${unit}</h4><p>Sin datos válidos disponibles</p></article>`;
const times=[...new Set(rows.map(r=>r.marca_original))].sort();const values=valid.map(r=>Number(r.prom));let lo=Math.min(...values),hi=Math.max(...values);const pad=Math.max((hi-lo)*.15,.2);lo-=pad;hi+=pad;const x=t=>48+(times.length>1?times.indexOf(t)/(times.length-1):.5)*382;const y=v=>146-(v-lo)/(hi-lo)*112;
let svg=`<svg viewBox="0 0 460 186" role="img" aria-label="${title}, ${unit}, promedios horarios. Valores, estaciones y marcas en los puntos del gráfico.">`;
for(let i=0;i<3;i++){const v=lo+(hi-lo)*i/2;svg+=`<line x1="48" y1="${y(v)}" x2="430" y2="${y(v)}" stroke="#e1e6dc"/><text x="40" y="${y(v)+3}" text-anchor="end">${fmt(v,1)}</text>`;}
svg+=`<text x="48" y="175">${times[0].slice(11,16)}</text><text x="430" y="175" text-anchor="end">${times.at(-1).slice(11,16)}</text>`;
let legend='';for(const s of ['6','8']){const series=rows.filter(r=>r.estacion===s).sort((a,b)=>a.marca_original.localeCompare(b.marca_original));if(!series.length)continue;const color=s==='6'?'#1682c4':'#3b547f';let prev=null;for(const r of series){if(r.calidad!=='valida'||r.prom==null||r.prom===''||!Number.isFinite(Number(r.prom))){prev=null;continue;}const point=[x(r.marca_original),y(Number(r.prom))];if(prev && r.marca_original.replace(' ','T')===nominalShift(prev.r.marca_original,1).replace(' ','T')){svg+=`<line x1="${prev.p[0]}" y1="${prev.p[1]}" x2="${point[0]}" y2="${point[1]}" stroke="${color}" stroke-width="2"/>`;}// Adyacencia de etiquetas nominales, sin asignarles zona.
svg+=`<circle cx="${point[0]}" cy="${point[1]}" r="2.5" fill="${color}"><title>${stations[s]} · ${esc(r.marca_original)} · ${esc(r.prom)} ${unit}</title></circle>`;prev={p:point,r};}const r=series[0];legend+=`<span><i class="${s==='8'?'pisco':''}"></i>${s==='6'?'INIA':'Pisco'} · ${esc(r.sensor)} · ${r.altura_m} m</span>`;}
return `<article class="chart"><h4>${title} <span class="unit">${unit}</span></h4><p>${times[0].slice(0,10)} · ${valid.length} registros válidos</p>${svg}</svg><div class="legend">${legend}</div></article>`;}
function table(rows){return `<details class="records"><summary>Consultar valores exactos de las observaciones (${rows.length} registros)</summary><div class="data-table"><table><caption>Promedios horarios y calidad; etiquetas temporales sin zona confirmada</caption><thead><tr><th>Estación</th><th>Sensor / altura</th><th>Variable</th><th>Marca original</th><th>Promedio</th><th>Unidad</th><th>Calidad</th><th>Cobertura %</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${stations[r.estacion]}</td><td>${esc(r.sensor)} / ${r.altura_m} m</td><td>${names[r.variable]}</td><td>${mark(r.marca_original)}</td><td>${r.prom===''?'Sin dato':esc(r.prom)}</td><td>${esc(r.unidad)}</td><td>${r.calidad==='valida'?'Válida':'Inválida / vacía'}</td><td>${r.porcentaje_datos===''?'Sin dato':esc(r.porcentaje_datos)}</td></tr>`).join('')}</tbody></table></div></details>`;}
function horizonControls(){return `<div class="horizon-control"><span class="control-label" id="horizon-label">Horizonte del modelo</span><div class="horizons" role="group" aria-labelledby="horizon-label">${[1,3,6,8,12,24].map(h=>`<button data-h="${h}" aria-pressed="${h===horizon}">${h} h</button>`).join('')}</div></div>`;}
function conditions(rows){
 const rs=rows.filter(r=>r.estacion===station);
 const vars=[['temperatura','Temperatura'],['humedad','Humedad relativa'],['viento','Velocidad del viento'],['direccion','Dirección del viento'],['presion','Presión local']];
 return `<section class="conditions"><div class="card-heading"><h3>Condiciones</h3><label class="sr-only" for="station">Estación del resumen</label><select id="station"><option value="6" ${station==='6'?'selected':''}>INIA · Vicuña</option><option value="8" ${station==='8'?'selected':''}>Pisco Elqui</option></select></div><p class="small">Última observación por sensor · ${stations[station]}</p><dl class="condition-list">${vars.map(([v,name])=>{
  const r=rs.find(r=>r.variable.startsWith(v));const valid=r&&r.calidad==='valida'&&r.prom!=null&&r.prom!==''&&Number.isFinite(Number(r.prom));
  const height=r?.altura_m==null?'':` · ${fmt(r.altura_m,1)} m`;
  return `<div><dt>${name}<small>${esc(height)}</small></dt><dd>${valid?fmt(r.prom):'—'} <small>${valid?esc(r.unidad):'Sin dato válido'}</small><span class="observation-mark">${r?mark(r.marca_original):'Sin observación'}${r?.cache?.estado==='datos_obsoletos'?' · dato antiguo':''}</span></dd></div>`;
 }).join('')}</dl><p class="chart-note">Marcas originales de observación. <a href="/metodologia#tiempos">Sobre sus horarios y alturas</a></p></section>`;
}
function percentage(value){
 if(typeof value!=='number'||!Number.isFinite(value)||value<0||value>1)return null;
 const p=value*100; // Contrato HA-3: fracción 0–1; arco siempre en escala real 0–100.
 return {p,text:p.toLocaleString('es-CL',{maximumSignificantDigits:3,useGrouping:false})};
}
function gauge(value){
 const result=percentage(value);
 if(!result)return '<p class="missing-value">Sin probabilidad disponible</p>';
 const {p,text}=result;
 // Sector anular único: bordes radiales, sin trazos discontinuos ni remates.
 // La superficie y el ángulo son proporcionales al valor, incluso cerca de cero.
 const angle=Math.PI*(p/100),sin=Math.sin(angle),shift=2*Math.sin(angle/2)**2;
 const outer=p===100?[230,120]:[10+110*shift,120-110*sin];
 const inner=p===100?[210,120]:[30+90*shift,120-90*sin];
 const progress=p===0?'':`<path class="gauge-value" d="M10 120 A110 110 0 0 1 ${outer[0]} ${outer[1]} L${inner[0]} ${inner[1]} A90 90 0 0 0 30 120 Z"/>`;
 const precision=text.length>6?' precision-'+[8,10,14,20,40,80,160,400].find(n=>text.length<=n):'';
 return `<div class="gauge"><svg viewBox="0 0 240 140" role="img" aria-label="${esc(text)} por ciento, escala de cero a cien"><path class="gauge-track" d="M20 120 A100 100 0 0 1 220 120" pathLength="100"/>${progress}<text x="8" y="139">0 %</text><text x="232" y="139" text-anchor="end">100 %</text></svg><strong class="probability${precision}">${esc(text)}<span>%</span></strong></div>`;
}
function emissionTime(value){
 // La API da emisión UTC explícita; rechazar marcas nominales sin zona.
 if(typeof value!=='string'||!/(Z|[+]00:00)$/.test(value))return 'Fecha de emisión no disponible';
 const date=new Date(value);if(!Number.isFinite(date.getTime()))return 'Fecha de emisión no disponible';
 const options={timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'};
 const full=new Intl.DateTimeFormat('es-CL',options).format(date);
 return `<time datetime="${esc(value)}" title="${esc(full)} · America/Santiago" aria-label="${esc(full)} · hora de Chile">${esc(full)}</time> <span>· hora de Chile</span>`;
}
function resultNotice(state){
 const reasons=[state.estado,...(state.motivos||[])];
 if(reasons.includes('evento_activo'))return 'Evento activo en los registros utilizados';
 if(reasons.includes('datos_obsoletos'))return 'Resultado desactualizado';
 if(reasons.some(x=>['antecedentes_incompletos_o_invalidos','sin_adquisiciones'].includes(x)))return 'Datos insuficientes';
 return 'Estimación no disponible';
}
function sensorDetails(rows,groups=null){return `<details class="sensor-details" id="sensor-details"><summary>Detalle de estaciones y sensores <span>Alturas · calidad · marcas · dirección del viento</span></summary>${stationCards(rows,groups)}<p class="small">Alturas nominales del XLS. INIA T/HR: encabezado 2 m frente a ficha 1,5 m; compatibilidad instrumental pendiente. Recepción UTC y marca de observación son tiempos distintos.</p></details>`;}
function currentView(){
 const st=data.estado||{};
 const latest=(Array.isArray(data.observaciones)?data.observaciones:[]).map(g=>g.ultima).filter(Boolean);
 const selected=data.estimacion?.[String(horizon)];
 const available=!readFailed&&st.estado==='estimacion_disponible'&&st.elegible===true&&selected&&percentage(selected.probabilidad)!==null;
 const recorded=!available?data.ultimo_resultado_registrado?.[String(horizon)]:null;
 return `<section class="estimate-card primary-estimate" aria-labelledby="estimate-title"><div class="estimate-heading"><h2 id="estimate-title">Estimación de inicio del criterio</h2><span class="experimental">Experimental</span></div><div class="estimate-layout"><div class="estimate-reading">${available?gauge(selected.probabilidad):`<div class="unavailable-icon" aria-hidden="true">≋</div><h3>${readFailed?'Estimación no disponible':esc(resultNotice(st))}</h3>`}</div><div class="estimate-controls">${horizonControls()}<a class="horizon-help" href="/metodologia#horizontes">Qué significa este horizonte</a><p class="emission-date">${available?'Actualizada '+emissionTime(selected.emision_utc):recorded?'Último resultado registrado · anterior / no vigente<br>'+emissionTime(recorded.emision_utc):'Sin estimación vigente para este horizonte.'}</p>${readFailed?'<p class="notice" role="status">No se pudo renovar la lectura. Las observaciones conservadas corresponden a la lectura anterior.</p>':''}<button class="refresh" id="refresh">↻ Leer de nuevo</button></div></div></section><div class="observations-heading"><h2>Observaciones meteorológicas</h2><a href="/metodologia#tiempos">Cómo leer las observaciones</a></div><div class="observations-grid">${graphs(data.series||[])}${conditions(latest)}</div>`;
}
function historicalView(){const out=data.salida;const t=out.hora_observacion_original;const end=targetEnd(t,horizon);const rows=data.series;const latest=rows.filter(r=>r.marca_original===t);return `<div class="toolbar"><label class="case-control" for="case"><span class="control-label">Caso histórico · validación 2022</span><select id="case"><option value="ordinario" ${caseId==='ordinario'?'selected':''}>01 · 1 enero 2022 · caso ordinario</option><option value="inicio_6h" ${caseId==='inicio_6h'?'selected':''}>02 · 6 junio 2022 · inicio dentro de 6 h</option></select></label>${horizonControls()}</div><div class="status-line historical"><span class="status-dot"></span><strong>Estimación histórica del criterio</strong><span>${mark(t)} · marca original sin zona confirmada</span></div><div class="dashboard-grid"><section class="estimate-card"><p class="eyebrow">ESTIMACIÓN HISTÓRICA · ${horizon} H</p>${gauge(out.estimaciones[String(horizon)])}<h3>Posible inicio del criterio</h3><p>Ventana acumulada de ${horizon} h<br>${mark(t)} → ${mark(end)}</p><span class="card-foot">Valor guardado · sin categoría de alerta</span></section>${graphs(rows)}${conditions(latest)}</div><details class="status-details"><summary><strong>Cómo leer esta estimación</strong><span>Ventana objetivo, independencia de modelos y trazabilidad</span></summary><div class="detail-body"><p>Valor guardado de validación. Sin calibración meteorológica certificada. Posible inicio después de ${mark(t)} hasta ${mark(end)}. No indica la hora exacta ni ${horizon} horas efectivas de anticipación.</p><p>Criterio en la emisión: inactivo · 7 horas × 10 sensores válidos. Dos ventanas aisladas de validación, sin reproducción temporal continua.</p><p>Modelo ${esc(out.modelo)} · configuración D, INIA con presión propia más Pisco. Bloque externo ${data.bloque_validacion}. Entrenamiento ${esc(data.entrenamiento)}.</p><p>Probabilidad original de API (fracción): ${esc(out.estimaciones[String(horizon)])}. El porcentaje central se redondea a tres cifras significativas; el arco utiliza el valor completo en escala 0–100 %.</p><p>SHA-256 del modelo: ${esc(out.modelo_sha256)}.</p><p>Selección: ${esc(data.seleccion)} Las probabilidades son ventanas acumuladas de modelos independientes y se conservan sin suavizar; no son una trayectoria del viento ni probabilidades horarias. El futuro observado procede del objetivo guardado de validación; no se cargan datos 2024–2025.</p></div></details>${sensorDetails(latest)}<div id="exact-values">${table(rows)}</div><div class="verification"><div><span class="label">Verificación retrospectiva</span><p>Futuro observado, separado de los antecedentes del modelo.</p></div><button class="button" id="reveal" aria-expanded="false" aria-controls="verification-result">Revelar qué ocurrió después</button><div id="verification-result"></div><details><summary>Sobre la selección de los casos</summary><p>El objetivo observado se consulta por separado y nunca alimenta los antecedentes. El nombre del segundo caso describe su selección a seis horas; no garantiza acierto del modelo.</p></details></div>`;}
function nominalShift(t,h){
const sep=t.includes('T')?'T':' ';let [y,m,d,hh,mm,ss]=t.split(/[-T :]/).map(Number);
for(let k=0;k<h;k++){hh++;if(hh===24){hh=0;d++;const leap=y%4===0&&(y%100!==0||y%400===0);const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];if(d>days[m-1]){d=1;m++;if(m===13){m=1;y++;}}}}
const pad=n=>String(n).padStart(2,'0');return `${y}-${pad(m)}-${pad(d)}${sep}${pad(hh)}:${pad(mm)}:${pad(ss)}`;
}// Aritmética de calendario nominal: ninguna etiqueta recibe UTC.
function targetEnd(t,h){return nominalShift(t,h);}
function render(){
 content.innerHTML=currentView();
 document.querySelectorAll('[data-h]').forEach(b=>b.onclick=()=>{horizon=Number(b.dataset.h);render();document.querySelector(`[data-h="${horizon}"]`).focus();});
 document.querySelector('#variable').onchange=e=>{variable=e.target.value;render();document.querySelector('#variable').focus();};
 document.querySelector('#station').onchange=e=>{station=e.target.value;render();document.querySelector('#station').focus();};
 document.querySelector('#refresh').onclick=load;
}
async function reveal(){const request=sequence, selected=caseId,h=horizon;const button=document.querySelector('#reveal');button.disabled=true;try{const result=await get(`/api/verificacion?caso=${selected}&horizonte=${h}`);if(request!==sequence||mode!=='historico'||selected!==caseId||h!==horizon)return;revealed=true;document.querySelector('#verification-result').innerHTML=`<p class="verification-result"><strong>${result.objetivo===1?'Sí hubo inicio del criterio':'No hubo inicio del criterio'} dentro de esta ventana de ${h} h.</strong></p><p class="small">Objetivo de validación guardado: ${result.objetivo}. No certifica por sí solo un evento meteorológico ni evalúa el desempeño completo.</p>`;button.setAttribute('aria-expanded','true');button.textContent='Verificación revelada';}catch(e){if(request===sequence&&selected===caseId&&h===horizon){document.querySelector('#verification-result').textContent='No se pudo leer la verificación. Vuelve a intentarlo.';button.disabled=false;}}}
load();
