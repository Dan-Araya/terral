// Adaptado del contrato de portada: entradas sintéticas, sin adquisición ni datos privados.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=__dirname+'/../aplicacion_terral/g4',source=fs.readFileSync(root+'/web/app.js','utf8');
const {execFileSync}=require('node:child_process');
const payload=JSON.parse(execFileSync(process.env.PYTHON || 'python3',[__dirname+'/generar_payload.py'],{encoding:'utf8',cwd:__dirname+'/..'}));
const content={innerHTML:'',attrs:{},setAttribute(k,v){this.attrs[k]=v},focus(){}};
let pending=[];
const ctx={document:{body:{classList:{add(){}}},querySelector(s){return s.startsWith('#')?content:null},querySelectorAll(){return []}},fetch(url){assert.equal(url,'/api/actual');return new Promise((resolve,reject)=>pending.push({resolve,reject}))}};
vm.createContext(ctx);vm.runInContext(source,ctx);
const run=code=>vm.runInContext(code,ctx);
function display(input,h=6){ctx.input=input;return run(`data=input;horizon=${h};readFailed=false;currentView()`)}
for(const h of [1,3,6,8,12,24]){
 const html=display(payload,h),p=payload.estimacion[h].probabilidad*100;
 assert.doesNotMatch(html,/stroke-dasharray/);
 ctx.value=payload.estimacion[h].probabilidad;assert.ok(html.includes(run("gauge(value)")));
 assert.match(html,/Horizonte del modelo/);assert.match(html,/Actualizada/);assert.match(html,/hora de Chile/);
 assert.doesNotMatch(html,/Consulta UTC|Referencia nominal|HA-3|Calidad y disponibilidad|Historial de emisiones|Consultar valores exactos|Detalle de estaciones|actualización en curso|terral probable|riesgo alto/);
}
for(const [value,text] of [[null,null],[undefined,null],['0.2',null],[-1,null],[2,null],[0,'0'],[1,'100'],[1e-10,'0,00000001'],[1e-7,'0,00001'],[9e-7,'0,00009'],[0.00000736,'0,000736'],[0.000099,'0,0099'],[0.0001,'0,01'],[0.00010123,'0,0101'],[0.123456,'12,3'],[0.99999,'100'],[Number.MIN_VALUE,'0,'+'0'.repeat(321)+'494']]){
 ctx.value=value;const result=run('percentage(value)');assert.equal(result?.text??null,text);
 if(text===null)assert.doesNotMatch(run('gauge(value)'),/gauge-value|probability/);
}
for(const [state,label] of [['antecedentes_incompletos_o_invalidos','Datos insuficientes'],['datos_obsoletos','Resultado desactualizado'],['evento_activo','Evento activo'],['sin_adquisiciones','Datos insuficientes']]){
 const copy=structuredClone(payload);copy.estado.estado=state;copy.estado.elegible=false;
 // Incluso si una respuesta inconsistente conserva el objeto, nunca resucitarlo.
 let html=display(copy);assert.match(html,new RegExp(label));assert.doesNotMatch(html,/gauge-value|class="probability/);
 copy.estimacion=null;html=display(copy);assert.match(html,/anterior \/ no vigente/);assert.match(html,/15-06-2023, 12:15/);
}
const nulled=structuredClone(payload);nulled.estimacion['6'].probabilidad=null;
assert.doesNotMatch(display(nulled),/gauge-value|class="probability/);
for(const [utc,local] of [['2026-10-31T19:15:39Z','31-10-2026, 16:15'],['2026-07-01T02:00:00Z','30-06-2026, 22:00'],['2026-01-01T02:00:00Z','31-12-2025, 23:00']]){
 ctx.value=utc;const text=run('emissionTime(value)');assert.ok(text.includes(local),text);assert.ok(text.includes(utc));
}
ctx.value='2026-10-31T14:00:00';assert.equal(run('emissionTime(value)'),'Fecha de emisión no disponible');
for(const station of ['6','8']){
 display(payload);run(`station='${station}'`);const html=run('conditions(data.observaciones.map(g=>g.ultima).filter(Boolean))');
 for(const unit of ['°C','%','m/s','hPa','Dirección del viento','2023-06-15 16:00:00'])assert.ok(html.includes(unit));
 assert.ok(html.includes(station==='6'?'INIA · Vicuña':'Pisco Elqui'));
}
for(let i=0;i<5;i++){
 display(payload);run(`variable='${i}'`);const graph=run('graphs(data.series)');
 assert.equal((graph.match(/class="chart"/g)||[]).length,1);
 if(i>=3)assert.doesNotMatch(graph,i===3?/Pisco ·/:/INIA ·/);
}
ctx.rows=[{estacion:'6',sensor:'36',altura_m:2,calidad:'valida',marca_original:'2026-10-31 10:00:00',prom:1},{estacion:'6',sensor:'36',altura_m:2,calidad:'valida',marca_original:'2026-10-31 11:00:00',prom:null},{estacion:'6',sensor:'36',altura_m:2,calidad:'valida',marca_original:'2026-10-31 12:00:00',prom:2}];
const gaps=run("chart('Viento','m/s',rows)");assert.equal((gaps.match(/<circle/g)||[]).length,2);assert.doesNotMatch(gaps,/stroke-width="2"/);
const html=fs.readFileSync(root+'/web/index.html','utf8');assert.doesNotMatch(html,/class="hero"|mode-bar|Revelar|caso ordinario|inicio dentro/);
assert.match(html,/Cargando…/);assert.doesNotMatch(html,/Leyendo datos|Actualizando datos/);
for(const value of [0,1e-12,1e-7,9e-7,.00000736,.000099,.0001,.123456,.5,1]){
 ctx.value=value;const svg=run('gauge(value)');assert.doesNotMatch(svg,/stroke-dasharray|NaN|Infinity/);
 assert.equal((svg.match(/class="gauge-value"/g)||[]).length,value===0?0:1);
 if(value===1)assert.match(svg,/A110 110 0 0 1 230 120 L210 120/);
 assert.equal(run('percentage(value).p'),value*100);assert.equal(ctx.value,value);
}
// Las funciones históricas de validación siguen disponibles internamente.
assert.equal(run("targetEnd('2022-12-31 23:00:00',3)"),'2023-01-01 02:00:00');
(async()=>{
 // Primera lectura pendiente, después recarga lenta: el DOM anterior no desaparece.
 pending.shift().resolve({ok:true,json:async()=>payload});await new Promise(setImmediate);
 const before=content.innerHTML;
 const loading=run('load()');assert.equal(content.innerHTML,before);assert.equal(content.attrs['aria-busy'],'true');
 const next=structuredClone(payload);next.estimacion['6'].probabilidad=.5;next.series=[];
 pending.shift().resolve({ok:true,json:async()=>next});await loading;
 assert.match(content.innerHTML,/A110 110 0 0 1 119[.0-9]* 10/);assert.match(content.innerHTML,/Sin datos válidos disponibles/);
 const failed=run('load()');pending.shift().reject(Error('offline'));await failed;
 assert.doesNotMatch(content.innerHTML,/gauge-value|class="probability/);assert.match(content.innerHTML,/lectura anterior/);
 // Respuestas fuera de orden: solo se publica la última lectura solicitada.
 const first=run('load()'),p1=pending.shift(),second=run('load()'),p2=pending.shift();
 p2.resolve({ok:true,json:async()=>payload});await second;const newest=content.innerHTML;
 p1.resolve({ok:true,json:async()=>next});await first;assert.equal(content.innerHTML,newest);
 console.log('OK: 6 horizontes; fracciones/precisión/null; estados bloqueados; fechas Chile verano/invierno y cambio de día; estaciones/unidades; 5 variables; huecos; conservación y sustitución atómica; error y respuestas fuera de orden; sin navegación histórica pública.');
})().catch(e=>{console.error(e);process.exitCode=1});
