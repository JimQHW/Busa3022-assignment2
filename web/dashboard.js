/* Offline SVG dashboard. No external libraries, requests or hidden refresh. */
(()=>{'use strict';
const P=window.MARKET_DATA,R=P.rows,S=P.signal,last=R[R.length-1],$=id=>document.getElementById(id);
const num=(v,d=2)=>v==null?'Unavailable':Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=v=>v==null?'Unavailable':num(v*100,2)+'%';
const utc=d=>Date.parse(d+'T00:00:00Z');
const fmt=d=>new Date(utc(d)).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
$('asof').textContent=fmt(P.summary.snapshot_end);
$('headline').textContent=P.message.detail;
$('close').textContent=num(last.nasdaq_close);$('ret').textContent=(last.nasdaq_return_1d>=0?'+':'')+pct(last.nasdaq_return_1d);$('yield').textContent=last.treasury_yield_pct==null?'Unavailable':num(last.treasury_yield_pct)+'%';
function showDailyChange(id,value,unit){
 const el=$(id),direction=value==null?'unavailable':value>0?'up':value<0?'down':'flat';
 el.classList.add(direction);
 el.textContent=value==null?'—':`${value>0?'▲':value<0?'▼':'▶'} ${num(Math.abs(value),2)} ${unit}`;
 el.title=`Change from previous trading session (${P.daily_changes.previous_date}). Green = increase; red = decrease; grey = unchanged or unavailable.`;
 el.setAttribute('aria-label',value==null?'Previous-session change unavailable':`${direction}: ${num(Math.abs(value),2)} ${unit} versus ${P.daily_changes.previous_date}`);
}
showDailyChange('close-change',P.daily_changes.nasdaq_points,'');
showDailyChange('yield-change',P.daily_changes.treasury_bps,'bp');
$('rag').textContent=S.latest;$('signal-card').classList.add(S.latest);
const active=[last.price_below_ma20,last.yield_rise_triggered].filter(x=>x===true).length;
const reasons={GREEN:['Neither condition triggered','Routine monitoring'],AMBER:['One condition triggered','Review the flagged condition'],RED:['Both conditions triggered','Escalate for analyst review'],UNAVAILABLE:['Incomplete signal inputs','Check missing observations']};
$('vol').textContent=S.latest==='UNAVAILABLE'?'Signal unavailable':`${active} of 2 conditions triggered`;
$('watch-copy').textContent=reasons[S.latest][0];$('watch-title').textContent=reasons[S.latest][1];
const flag=v=>v==null?'UNAVAILABLE':v?'TRIGGERED':'NOT TRIGGERED';
const bp=v=>v==null?'Unavailable':`${v>=0?'+':''}${num(v,1)} bp`;
const conditionClass=v=>v==null?'unknown':v?'triggered':'clear';
$('conditions').innerHTML=`<div class="condition ${conditionClass(last.price_below_ma20)}"><strong>Nasdaq below its 20-session average</strong><span>${num(last.nasdaq_close)} vs. ${num(last.nasdaq_ma20)} <em>${flag(last.price_below_ma20)}</em></span></div><div class="condition ${conditionClass(last.yield_rise_triggered)}"><strong>Significant Treasury yield rise</strong><span>${bp(last.yield_change_20_bps)} over 20 sessions · threshold +${num(S.yield_threshold_bps,1)} bp <em>${flag(last.yield_rise_triggered)}</em></span></div>`;
$('signal-rules').innerHTML=[['GREEN','0 conditions triggered','Neither equity weakness nor a significant yield rise.','Continue monitoring.'],['AMBER','1 condition triggered','Equity weakness or a significant yield rise.','Review the flagged condition.'],['RED','2 conditions triggered','Equity weakness and a significant yield rise.','Escalate for analyst review.']].map(([band,rule,description,action])=>`<div class="rule ${band} ${S.latest===band?'current':''}"><strong>${band===S.latest?'● ':''}${band}</strong><span>${rule}</span><p>${description}</p><b>${action}</b></div>`).join('');
$('thresholds').textContent=S.rule;
$('calibration').textContent=`Yield-rise threshold: ${num(S.yield_threshold_bps,4)} bp, based on the 80th percentile of ${S.calibration_observations} pre-display 20-session changes (${fmt(S.calibration_start)} – ${fmt(S.calibration_end)}), floored at zero; a strictly positive rise is required. Both endpoints must be observed. This is a monitoring choice, not a validated risk model. Displayed values are rounded; full precision determines flags. Latest comparison date: ${last.yield_comparison_date}; prior yield: ${last.yield_comparison_pct==null?'unavailable':num(last.yield_comparison_pct)+'%'}.`;
$('counts').innerHTML=['GREEN','AMBER','RED','UNAVAILABLE'].map(c=>`<div><strong>${S.counts[c]||0}</strong><span>${c} sessions</span></div>`).join('');
$('quality-copy').textContent=`${P.summary.scheduled_sessions} scheduled sessions were checked for the calculation period. Missing Treasury yields remain blank; index records are retained. No price or yield values are imputed.`;
document.querySelector('.quality h2').textContent=`${P.summary.display_missing_yield} macro gap${P.summary.display_missing_yield===1?'':'s'} in the full snapshot`;
$('coverage').textContent=P.summary.scheduled_sessions;
$('build-info').textContent=`Observation cut-off: ${fmt(P.summary.snapshot_end)}. Built ${P.built_at_utc.slice(0,19).replace('T',' ')} UTC. Ingestion time is not source publication time.`;
const start=$('start-range'),end=$('end-range');start.max=R.length-2;end.max=R.length-1;end.value=R.length-1;
let selected=R;
function svgChart(id,series,dual=false){
 const svg=$(id),width=Math.max(360,svg.clientWidth),height=Math.max(165,svg.clientHeight);
 const pad={l:66,r:dual?76:25,t:25,b:34},w=width-pad.l-pad.r,h=height-pad.t-pad.b;
 const t0=utc(selected[0].date),t1=utc(selected[selected.length-1].date),X=d=>pad.l+(utc(d)-t0)/(t1-t0||1)*w;
 const scales=series.map((s,i)=>{const vals=(dual?selected.map(r=>r[s.key]):selected.flatMap(r=>series.map(q=>r[q.key]))).filter(v=>v!=null);let lo=Math.min(...vals),hi=Math.max(...vals);if(!vals.length){lo=0;hi=1}const m=(hi-lo)*.12||Math.abs(lo)*.01||1;lo-=m;hi+=m;return{lo,hi,y:v=>pad.t+(hi-v)/(hi-lo)*h}});
 let html=`<title>${id==='trend'?'Nasdaq close and moving average':'Treasury yield and Nasdaq close'} from ${selected[0].date} to ${selected[selected.length-1].date}</title>`;
 for(let k=0;k<4;k++){const y=pad.t+k*h/3,scale=scales[0],v=scale.hi-k*(scale.hi-scale.lo)/3;html+=`<line x1="${pad.l}" x2="${width-pad.r}" y1="${y}" y2="${y}" stroke="#e8edf3"/><text x="${pad.l-10}" y="${y+4}" text-anchor="end" font-size="12" fill="#65738a">${num(v,dual?2:0)}</text>`;if(dual){const z=scales[1].hi-k*(scales[1].hi-scales[1].lo)/3;html+=`<text x="${width-pad.r+10}" y="${y+4}" font-size="12" fill="#8495aa">${num(z,0)}</text>`}}
 const axisLabels=dual?['Yield %','Index points']:['Index points',''];html+=`<text x="${pad.l}" y="12" font-size="12" fill="#65738a">${axisLabels[0]}</text>`;if(dual)html+=`<text x="${width-pad.r}" y="12" text-anchor="end" font-size="12" fill="#65738a">${axisLabels[1]}</text>`;
 const indices=[...new Set([0,Math.floor((selected.length-1)/3),Math.floor(2*(selected.length-1)/3),selected.length-1])];
 indices.forEach(i=>{const r=selected[i],label=new Date(utc(r.date)).toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'});html+=`<text x="${X(r.date)}" y="${height-8}" text-anchor="middle" font-size="12" fill="#65738a">${label}</text>`});
 series.forEach((s,j)=>{let d='',pen=false;selected.forEach(r=>{const v=r[s.key];if(v==null){pen=false;return}d+=`${pen?'L':'M'}${X(r.date).toFixed(2)},${scales[j].y(v).toFixed(2)} `;pen=true});html+=`<path data-series="${s.key}" d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width||2.5}" stroke-linejoin="round" stroke-linecap="round"${s.dash?' stroke-dasharray="5 4"':''}/>`});
 if(dual)selected.filter(r=>r.treasury_yield_pct==null).forEach(r=>{const x=X(r.date);html+=`<line x1="${x}" x2="${x}" y1="${pad.t}" y2="${pad.t+h}" stroke="#d7a64b" stroke-dasharray="3 5"/><text x="${Math.min(x+5,width-pad.r-68)}" y="${pad.t+12}" font-size="11" fill="#98690e">Yield missing</text>`});
 html+=`<line id="${id}-cross" y1="${pad.t}" y2="${pad.t+h}" stroke="#71839a" stroke-dasharray="3 3" visibility="hidden"/>`;
 svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.innerHTML=html;
 const tip=$(id+'-tip');svg.onpointermove=e=>{const box=svg.getBoundingClientRect(),x=(e.clientX-box.left)*width/box.width;let row=selected.reduce((best,r)=>Math.abs(X(r.date)-x)<Math.abs(X(best.date)-x)?r:best,selected[0]);const cross=$(id+'-cross');cross.setAttribute('x1',X(row.date));cross.setAttribute('x2',X(row.date));cross.setAttribute('visibility','visible');tip.innerHTML=`<strong>${fmt(row.date)}</strong><br>`+series.map(s=>`${s.label}: ${row[s.key]==null?'Missing':num(row[s.key],s.key==='treasury_yield_pct'?2:2)}`).join('<br>');tip.style.display='block';tip.style.left=Math.max(0,Math.min((e.clientX-box.left)+12,box.width-215))+'px';tip.style.top='34px'};
 svg.onpointerleave=()=>{tip.style.display='none';$(id+'-cross').setAttribute('visibility','hidden')};
}
function update(){let a=Number(start.value),b=Number(end.value);if(a>=b){if(document.activeElement===start)a=b-1;else b=a+1;start.value=a;end.value=b}selected=R.slice(a,b+1);$('range-label').textContent=`${fmt(selected[0].date)} – ${fmt(selected[selected.length-1].date)} · ${selected.length} sessions`;
 svgChart('trend',[{key:'nasdaq_close',label:'Nasdaq',color:'#244b82'},{key:'nasdaq_ma20',label:'20-session average',color:'#c08d28'}]);
 svgChart('macro',[{key:'treasury_yield_pct',label:'Treasury yield %',color:'#237e7a'},{key:'nasdaq_close',label:'Nasdaq points',color:'#244b82',width:2.5,dash:true}],true);
 $('missing-count').textContent=selected.filter(r=>r.yield_missing).length;
 $('table-body').innerHTML=selected.map(r=>`<tr><td>${r.date}</td><td>${num(r.nasdaq_close)}</td><td>${num(r.nasdaq_ma20)}</td><td>${num(r.nasdaq_return_1d==null?null:r.nasdaq_return_1d*100,4)}</td><td>${num(r.yield_change_20_bps,1)}</td><td class="${r.yield_missing?'null':''}">${r.yield_missing?'Missing':num(r.treasury_yield_pct)}</td><td>${r.rag}</td></tr>`).join('');
 window.dashboardState={visibleRows:selected.length,firstDate:selected[0].date,lastDate:selected[selected.length-1].date,latestSignal:S.latest};}
[start,end].forEach(el=>el.addEventListener('input',()=>{document.querySelectorAll('[data-days]').forEach(b=>b.classList.remove('active'));update()}));
document.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',()=>{const days=Number(button.dataset.days),cut=utc(last.date)-(days-1)*86400000;start.value=Math.max(0,R.findIndex(r=>utc(r.date)>=cut));end.value=R.length-1;document.querySelectorAll('[data-days]').forEach(b=>b.classList.toggle('active',b===button));update()}));
$('download').addEventListener('click',()=>{const fields=['date','nasdaq_close','nasdaq_ma20','nasdaq_return_1d','treasury_yield_pct','yield_missing','yield_change_20_bps','yield_comparison_date','yield_comparison_pct','price_below_ma20','yield_rise_triggered','rag'];const csv=fields.join(',')+'\n'+selected.map(r=>fields.map(k=>r[k]==null?'':r[k]).join(',')).join('\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));const a=document.createElement('a');a.href=url;a.download='market_view.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
$('open-details').addEventListener('click',()=>$('details-dialog').showModal());
$('close-details').addEventListener('click',()=>$('details-dialog').close());
window.addEventListener('resize',update);update();
})();
