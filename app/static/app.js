const app = {catalog:null, state:null, sources:[], result:null, mode:'live_inputs', demo:null};

const DEMO_PRESETS = {
  tehri_breach: {event_type:'dam_breach', width:60, depth:30, formation:1.5, rain:1.0},
  extreme_monsoon: {event_type:'dam_breach', width:80, depth:35, formation:0.75, rain:1.3},
  lake_outburst: {event_type:'lake_burst', width:42, depth:24, formation:0.6, rain:1.15},
  blockage_failure: {event_type:'blockage_failure', width:55, depth:22, formation:1.0, rain:1.2},
  sudden_release: {event_type:'sudden_release', width:28, depth:14, formation:4.0, rain:0.9},
};

const EVENT_COPY = {
  dam_breach: {width:'Breach width', depth:'Breach depth', formation:'Formation time', hint:'Rapid hypothetical breach at Tehri, routed through Koteshwar and downstream settlements.'},
  sudden_release: {width:'Release opening', depth:'Effective head', formation:'Release ramp time', hint:'Emergency gate-release hydrograph routed through the same downstream cascade.'},
  lake_burst: {width:'Outlet width', depth:'Effective lake depth', formation:'Drainage time', hint:'Sudden drainage of an upstream natural lake entering the Bhagirathi cascade.'},
  blockage_failure: {width:'Failure width', depth:'Impounded depth', formation:'Erosion time', hint:'Failure of a temporary river blockage and release of the impounded water volume.'},
};

const $ = (id) => document.getElementById(id);
const fmt = (n, digits=1) => Number(n).toLocaleString('en-IN',{maximumFractionDigits:digits});
const exactMoney = (n) => `₹${Number(n).toLocaleString('en-IN',{maximumFractionDigits:0})}`;
const money = (n) => {
  const value=Number(n)||0, absolute=Math.abs(value);
  if(absolute>=1_00_00_000)return `₹${fmt(value/1_00_00_000,2)} crore`;
  if(absolute>=1_00_000)return `₹${fmt(value/1_00_000,2)} lakh`;
  return exactMoney(value);
};
const moneyHTML = (n) => `<span title="Exact: ${exactMoney(n)}">${money(n)}</span>`;
const storage = (mcm) => Number(mcm)>=1000?`${fmt(Number(mcm)/1000,3)} BCM`:`${fmt(mcm,2)} MCM`;
const niceCeiling = (value) => {
  if(!Number.isFinite(value)||value<=0)return 1;
  const magnitude=10**Math.floor(Math.log10(value)), normalized=value/magnitude;
  return (normalized<=1?1:normalized<=2?2:normalized<=5?5:10)*magnitude;
};
const INDIA_TIME_ZONE = 'Asia/Kolkata';
const timeLabel = (value) => value ? new Date(value).toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:INDIA_TIME_ZONE,timeZoneName:'short'}) : 'Not triggered';
const clockTime = (value) => new Date(value).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',timeZone:INDIA_TIME_ZONE});

async function api(path, options={}) {
  if(window.HYDRA_STATIC_API)return window.HYDRA_STATIC_API(path,options);
  const response = await fetch(path,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
  const payload = await response.json();
  if(!response.ok){const error=new Error(payload.error||`Request failed (${response.status})`);error.payload=payload;throw error;}
  return payload;
}

async function boot(){
  [app.catalog,app.state] = await Promise.all([api('/api/catalog'),api('/api/state')]);
  const sourcePayload=await api('/api/sources'); app.sources=sourcePayload.sources;
  renderCatalog(); renderState(); renderSources(); drawNetwork(); bindEvents(); drawEmptyChart();
  const query=new URLSearchParams(location.search);
  if(window.HYDRA_STATIC_API||query.get('demo')==='1'){
    await toggleOfflineDemo();
    if(app.mode==='offline_demo'&&query.get('autorun')==='1') await runScenario();
  }
}

function renderCatalog(){
  const staticSite=Boolean(window.HYDRA_STATIC_API);
  $('basinName').textContent=app.catalog.basin.name;
  $('basinDescription').textContent=app.mode==='offline_demo'?app.demo.description:app.catalog.basin.description;
  $('basinState').textContent=app.catalog.basin.state;
  $('modeLabel').textContent=app.mode==='offline_demo'?'Synthetic demonstration':'Live inputs';
  $('warningStrip').innerHTML=app.mode==='offline_demo'
    ?'<strong>SYNTHETIC DEMONSTRATION.</strong> Rain, water storage, assets and costs are invented. This is not a real flood forecast or official warning.'
    :'<strong>Not an official warning service.</strong> Live observations and model assumptions are shown separately. Conditional failure is a what-if branch.';
  $('offlineDemo').textContent=staticSite?'GitHub Pages demonstration':app.mode==='offline_demo'?'Return to live inputs':'Launch demonstration';
  $('offlineDemo').disabled=staticSite&&app.mode==='offline_demo';
  $('refreshSources').classList.toggle('hidden',app.mode==='offline_demo');
  $('uploadPanel').classList.toggle('hidden',app.mode==='offline_demo');
  $('presetRow').classList.toggle('hidden',app.mode!=='offline_demo');
  $('sourceTitle').textContent=app.mode==='offline_demo'?'Scenario input dataset':'Online sources';
}

function renderState(){
  const gate=app.state.gate;
  $('gateBadge').textContent=gate.ready?'Ready':'Blocked';
  $('gateBadge').className=`tag ${gate.ready?'ready':'bad'}`;
  $('systemStatus').className=`status-pill ${app.mode==='offline_demo'?'demo':gate.ready?'ready':'blocked'}`;
  $('systemStatus').innerHTML=`<i></i>${app.mode==='offline_demo'?'SYNTHETIC DEMO':gate.ready?'Inputs current':'Inputs missing or stale'}`;
  $('runScenario').disabled=!gate.ready;
  $('gateChecks').innerHTML=Object.entries(gate.checks).map(([key,item])=>{
    const detail=key==='reservoir_state'?`${item.sites.length}/${item.required.length} sites ${app.mode==='offline_demo'?'synthetic':'current'}`:key==='rainfall'?`${item.records}/${item.minimum_records} records ${app.mode==='offline_demo'?'synthetic':'current'}`:`${item.records} ${app.mode==='offline_demo'?'synthetic':'costed'} assets`;
    return `<div class="gate-item ${item.ready?'ready':''}"><i></i><div><strong>${key.replaceAll('_',' ')}</strong><span>${detail}</span></div></div>`;
  }).join('');
  const rain=app.state.rainfall||[], obs=app.state.observations||[];
  const tehri=latest(obs.filter(r=>r.site_id==='tehri'&&r.variable==='reservoir_storage'));
  const kote=latest(obs.filter(r=>r.site_id==='koteshwar'&&r.variable==='reservoir_storage'));
  const totalRain=rain.slice(-24).reduce((sum,r)=>sum+Number(r.value||0),0);
  $('kpiRow').innerHTML=`
    <div class="kpi"><span>Upstream rainfall · mm</span><strong>${rain.length?fmt(totalRain,1)+' mm':'—'}</strong><small>${rain.length?`${app.mode==='offline_demo'?'Synthetic dataset':'Last'} ${Math.min(24,rain.length)} hourly records`:'Waiting for timestamped data'}</small></div>
    <div class="kpi"><span>Tehri storage · BCM</span><strong>${tehri?storage(tehri.value):'—'}</strong><small>${tehri?`${app.mode==='offline_demo'?'Synthetic · ':''}${fmt(tehri.value,2)} MCM · ${timeLabel(tehri.observed_at||tehri.time)}`:'Waiting for official/operator data'}</small></div>
    <div class="kpi"><span>Koteshwar storage · MCM</span><strong>${kote?storage(kote.value):'—'}</strong><small>${kote?`${app.mode==='offline_demo'?'Synthetic · ':''}${timeLabel(kote.observed_at||kote.time)}`:'Waiting for official/operator data'}</small></div>
    <div class="kpi accent"><span>Scenario state</span><strong>${app.mode==='offline_demo'?'Scenario ready':gate.ready?'Ready':'Blocked'}</strong><small>${gate.message}</small></div>`;
}

function latest(rows){return rows.sort((a,b)=>String(a.observed_at||a.time).localeCompare(String(b.observed_at||b.time))).at(-1);}

function renderSources(){
  $('sourceList').innerHTML=app.sources.map(source=>`<article class="source-item"><header><strong>${source.name}</strong><i class="source-state ${source.status}"></i></header><p>${source.status.replaceAll('_',' ')} · ${source.message||'No message'}</p>${source.observed_at?`<p>Observed ${timeLabel(source.observed_at)}</p>`:''}</article>`).join('');
}

async function toggleOfflineDemo(){
  if(app.mode==='offline_demo'){if(!window.HYDRA_STATIC_API)location.reload();return;}
  const button=$('offlineDemo');button.disabled=true;button.textContent='Loading demo…';
  try{
    const demo=await api('/api/demo');
    app.mode='offline_demo';app.demo=demo;app.state=demo;app.sources=demo.sources;app.result=null;
    renderCatalog();renderState();renderSources();drawNetwork();drawEmptyChart();
    $('lastRefresh').textContent='No network required';
    $('runMessage').textContent='Run a synthetic cascade; results are not a real flood prediction.';
    $('timeline').className='timeline empty-state';$('timeline').textContent='Run the demonstration to see the conditional cascade.';
    $('branchCards').innerHTML='<div class="empty-state">Two synthetic cascade branches will appear here.</div>';
    $('damageRows').innerHTML='<tr><td colspan="6" class="empty-state">No scenario results.</td></tr>';
    $('avulsionResult').textContent='Run the demonstration to see a synthetic alternative-path screening.';
    $('cascadeSummary').innerHTML='<div class="empty-state">Run a scenario to compare the contained and secondary-breach pathways.</div>';
    $('cascadeBranchBadge').textContent='Awaiting scenario';
    $('exportButtons').innerHTML='';
    $('missionSummary').classList.add('hidden');
    window.Simulation3D?.clear();
  }catch(error){$('runMessage').textContent=`Demonstration could not load: ${error.message}`;}
  finally{button.disabled=Boolean(window.HYDRA_STATIC_API&&app.mode==='offline_demo');if(app.mode!=='offline_demo')button.textContent='Launch demonstration';}
}

function drawNetwork(branchName=$('simulationBranch')?.value||'conditional_secondary_failure'){
  const svg=$('networkMap');
  const positions={tehri:[92,66],koteshwar:[254,183],devprayag:[126,337],rishikesh:[284,493]};
  const path='M92 66 C112 116 205 122 254 183 S226 276 126 337 S175 438 284 493';
  const branch=app.result?.cascade?.branches?.[branchName];
  const timeByNode={};
  (branch?.timeline||[]).forEach(item=>{
    if(!timeByNode[item.node])timeByNode[item.node]=clockTime(item.time);
  });
  let zones='';
  if(app.result){
    const baseline=app.result.cascade.branches.no_secondary_failure.rishikesh_hazard.maximum_depth_m;
    const selected=branch.rishikesh_hazard.maximum_depth_m;
    zones=`<ellipse class="flood-zone" cx="284" cy="493" rx="${34+baseline*4}" ry="${18+baseline*2}"/><ellipse class="flood-zone failure" cx="284" cy="493" rx="${39+selected*5}" ry="${22+selected*2.5}"/>`;
  }
  const danger=branch?.koteshwar?.failure_triggered?' danger':'';
  svg.innerHTML=`<defs><linearGradient id="terrain" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#eff7f3"/><stop offset="1" stop-color="#f7faf9"/></linearGradient><filter id="waveGlow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><rect x="0" y="0" width="430" height="560" rx="16" fill="url(#terrain)"/>${zones}<path class="river" d="${path}"/><path class="flow-path${danger}" d="${path}"/><circle class="wave-marker${danger}" r="7"><animateMotion dur="5.5s" repeatCount="indefinite" path="${path}"/></circle>`+
    app.catalog.nodes.map(node=>{const [x,y]=positions[node.id];const cls=node.kind==='settlement'?'node settlement':'node';const arrival=timeByNode[node.name]||'not routed';return `<g class="${cls}" data-node="${node.id}" transform="translate(${x} ${y})"><circle r="12"/><text x="18" y="-5">${node.name}</text><text class="sub" x="18" y="11">${node.kind}</text><text class="arrival" x="18" y="27">${arrival}</text></g>`}).join('');
  svg.querySelectorAll('.node').forEach(node=>node.addEventListener('click',(event)=>showNode(event,node.dataset.node)));
}

function showNode(event,id){
  const node=app.catalog.nodes.find(n=>n.id===id),tip=$('mapTooltip');
  tip.innerHTML=`<strong>${node.name}</strong><br>${node.structure_status}<br><span style="opacity:.7">${node.structure_source}</span>`;
  const panel=$('cascadeSection').getBoundingClientRect();
  tip.style.left=`${Math.max(12,Math.min(event.clientX-panel.left+18,panel.width-245))}px`;
  tip.style.top=`${Math.max(70,Math.min(event.clientY-panel.top+18,panel.height-130))}px`;tip.classList.remove('hidden');
  setTimeout(()=>tip.classList.add('hidden'),4500);
}

async function refreshSources(){
  const btn=$('refreshSources');btn.disabled=true;btn.textContent='Refreshing…';
  try{const payload=await api('/api/sources?refresh=1');app.sources=payload.sources;app.state=await api('/api/state');renderSources();renderState();const count=(payload.auto_ingested?.observations||0)+(payload.auto_ingested?.rainfall||0);$('lastRefresh').textContent=count?`${count} records added`:clockTime(new Date());}
  catch(error){$('lastRefresh').textContent='Refresh failed';}
  finally{btn.disabled=false;btn.textContent='Refresh sources';}
}

function bindEvents(){
  $('refreshSources').addEventListener('click',refreshSources);
  $('offlineDemo').addEventListener('click',toggleOfflineDemo);
  $('demoPreset').addEventListener('change',e=>applyPreset(e.target.value));
  $('eventType').addEventListener('change',updateEventControls);
  $('simulationBranch').addEventListener('change',e=>{drawNetwork(e.target.value);renderCascadePanel(e.target.value);renderMissionSummary(e.target.value);});
  $('rainMultiplier').addEventListener('input',e=>$('rainValue').textContent=`${Number(e.target.value).toFixed(2)}×`);
  $('runScenario').addEventListener('click',runScenario);
  $('jumpToSimulation').addEventListener('click',()=>$('simulationSection').scrollIntoView({behavior:'smooth',block:'start'}));
  $('jumpToDamage').addEventListener('click',()=>$('damageSection').scrollIntoView({behavior:'smooth',block:'start'}));
  document.querySelectorAll('[data-import]').forEach(button=>button.addEventListener('click',e=>{e.preventDefault();importFile(button.dataset.import)}));
  updateEventControls();
}

function updateEventControls(){
  const copy=EVENT_COPY[$('eventType').value]||EVENT_COPY.dam_breach;
  $('breachWidthLabel').textContent=copy.width;
  $('breachDepthLabel').textContent=copy.depth;
  $('formationLabel').textContent=copy.formation;
  $('eventHint').textContent=copy.hint;
}

function applyPreset(name){
  const preset=DEMO_PRESETS[name];
  if(!preset)return;
  $('eventType').value=preset.event_type;
  $('breachWidth').value=String(preset.width);
  $('breachDepth').value=String(preset.depth);
  $('formationHours').value=String(preset.formation);
  $('rainMultiplier').value=String(preset.rain);
  $('rainValue').textContent=`${preset.rain.toFixed(2)}×`;
  updateEventControls();
  $('runMessage').textContent='Preset loaded. Run it to compare both downstream cascade branches.';
}

async function importFile(kind){
  const input=kind==='observations'?$('observationFile'):kind==='rainfall'?$('rainfallFile'):kind==='assets'?$('assetFile'):$('avulsionFile');
  if(!input.files[0]){$('importMessage').textContent='Choose a file first.';return;}
  const file=input.files[0], content=await toBase64(file);
  try{
    const endpoint=kind==='assets'?'/api/import/assets':kind==='avulsion'?'/api/import/avulsion':'/api/import/timeseries';
    const payload={filename:file.name,content_base64:content,...(['observations','rainfall'].includes(kind)?{kind}:{})};
    const result=await api(endpoint,{method:'POST',body:JSON.stringify(payload)});
    $('importMessage').textContent=`Imported ${result.imported} format-validated records from ${file.name}; source accuracy is not independently verified.`;
    app.state=await api('/api/state');renderState();
  }catch(error){$('importMessage').textContent=`Import rejected: ${error.message}`;}
}

function toBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});}

async function runScenario(){
  const btn=$('runScenario');btn.disabled=true;btn.textContent='Simulating water…';$('runMessage').textContent='1/3 Routing rainfall and the source hydrograph…';
  const payload={event_type:$('eventType').value,breach_width_m:Number($('breachWidth').value),breach_depth_m:Number($('breachDepth').value),formation_hours:Number($('formationHours').value),rainfall_multiplier:Number($('rainMultiplier').value)};
  try{app.result=await api(app.mode==='offline_demo'?'/api/demo/scenarios':'/api/scenarios',{method:'POST',body:JSON.stringify(payload)});$('runMessage').textContent='2/3 Building inundation, cascade and damage layers…';renderResult();$('runMessage').textContent=`${app.mode==='offline_demo'?'SYNTHETIC DEMO · ':''}Scenario ${app.result.id}: both branches simulated and export packages prepared.`;}
  catch(error){$('runMessage').textContent=error.payload?.gate?.message||error.message;}
  finally{btn.disabled=!app.state.gate.ready;btn.textContent='Run cascade + 2-D simulation';}
}

function renderResult(){
  drawNetwork(); drawChart(app.result.hydrology,app.result.cascade.branches.conditional_secondary_failure.rishikesh_hydrograph.points);
  const branches=app.result.cascade.branches;
  $('timeline').classList.remove('empty-state');
  $('timeline').innerHTML=branches.conditional_secondary_failure.timeline.map(item=>`<div class="timeline-item"><strong>${item.node} · ${item.event}</strong><span>${timeLabel(item.time)}</span></div>`).join('');
  $('branchCards').innerHTML=Object.entries(branches).map(([name,branch])=>{const h=branch.rishikesh_hazard,s=app.result.spatial_simulation[name],d=app.result.spatial_damage[name];return `<article class="branch-card ${name.includes('conditional')?'alert':''}"><h3>${name.replaceAll('_',' ')}<span class="tag ${branch.koteshwar.failure_triggered?'warning':'ready'}">${branch.koteshwar.failure_triggered?'Triggered':'No breach'}</span></h3><div class="metric-grid"><div class="metric"><span>Wave arrival · IST</span><strong>${timeLabel(h.arrival_time)}</strong></div><div class="metric"><span>Peak discharge · m³/s</span><strong>${fmt(h.peak_flow_cumecs)} m³/s</strong></div><div class="metric"><span>Maximum grid depth · m</span><strong>${fmt(s.peak_depth_m,2)} m</strong></div><div class="metric"><span>Direct loss · ₹</span><strong>${moneyHTML(d.totals.central_inr)}</strong></div></div><p class="microcopy">${fmt(s.wet_cell_count,0)} wet 50 m × 50 m cells · ${s.solver_family}. Uncalibrated.</p></article>`}).join('');
  const damage=app.result.spatial_damage.conditional_secondary_failure;
  $('damageRows').innerHTML=damage.items.map(item=>`<tr><td>${item.name}</td><td>${item.type}</td><td>${fmt(item.depth_m,2)} m</td><td>${fmt(item.damage_fraction*100,1)}%</td><td>${moneyHTML(item.loss_central_inr)}</td><td>${item.confidence}</td></tr>`).join('')||'<tr><td colspan="6" class="empty-state">No costed assets intersected.</td></tr>';
  const avulsion=app.result.avulsion.conditional_secondary_failure;
  $('avulsionResult').classList.toggle('empty-state',avulsion.status!=='screened');
  $('avulsionResult').innerHTML=avulsion.status==='screened'?`<div class="branch-cards">${avulsion.candidates.map(item=>`<article class="branch-card ${item.category==='high'?'alert':''}"><h3>${item.name}<span class="tag ${item.category==='low'?'ready':'warning'}">${item.category}</span></h3><div class="metric-grid"><div class="metric"><span>Score</span><strong>${fmt(item.score,1)}/100</strong></div><div class="metric"><span>Relief advantage</span><strong>${fmt(item.relief_advantage_m,2)} m</strong></div></div><p class="microcopy">Slope ratio ${fmt(item.slope_ratio,2)} · ${item.evidence_source}</p></article>`).join('')}</div><p class="microcopy">${avulsion.warning}</p>`:avulsion.reason;
  $('exportButtons').innerHTML=Object.entries(app.result.exports).map(([name,url])=>`<a href="${url}" download>${name.toUpperCase()}</a>`).join('');
  renderMissionSummary($('simulationBranch').value);
  renderCascadePanel($('simulationBranch').value);
  window.Simulation3D?.load(app.result);
}

function renderMissionSummary(branchName='conditional_secondary_failure'){
  const branches=app.result.cascade.branches;
  const baseline=branches.no_secondary_failure;
  const selected=branches[branchName];
  const hazard=selected.rishikesh_hazard;
  const sim=app.result.spatial_simulation[branchName];
  const damage=app.result.spatial_damage[branchName];
  const affected=damage.items.filter(item=>Number(item.loss_central_inr)>0).length;
  const rise=baseline.rishikesh_hazard.peak_flow_cumecs>0
    ?(hazard.peak_flow_cumecs/baseline.rishikesh_hazard.peak_flow_cumecs-1)*100:0;
  const timeline=selected.timeline||[];
  const first=timeline[0]?.time, last=hazard.arrival_time;
  const leadHours=first&&last?Math.max(0,(new Date(last)-new Date(first))/3600000):null;
  const eventName=$('eventType').selectedOptions[0]?.textContent||app.result.config.event_type.replaceAll('_',' ');
  $('missionTitle').textContent=`${eventName}: ${selected.koteshwar.failure_triggered?'secondary-breach':'contained'} pathway`;
  $('missionNarrative').textContent=selected.koteshwar.failure_triggered
    ?`The routed wave reaches Rishikesh ${leadHours===null?'at the modelled arrival time':`about ${fmt(leadHours,1)} h after the source event`}. A hypothetical Koteshwar failure raises peak discharge by ${fmt(rise,0)}% versus the contained pathway. This comparison is a scenario, not a failure probability.`
    :`This reference pathway routes the upstream wave through Koteshwar without a secondary breach. It reaches Rishikesh ${leadHours===null?'at the modelled arrival time':`about ${fmt(leadHours,1)} h after the source event`} and provides the baseline for cascade comparison.`;
  $('missionMetrics').innerHTML=`
    <div><span>Cascade branch</span><strong>${selected.koteshwar.failure_triggered?'Secondary breach triggered':'No secondary breach'}</strong><small>Conditional rule outcome</small></div>
    <div><span>Rishikesh arrival · IST</span><strong>${timeLabel(hazard.arrival_time)}</strong><small>${leadHours===null?'Modelled time':fmt(leadHours,1)+' h response window'}</small></div>
    <div><span>Peak discharge · m³/s</span><strong>${fmt(hazard.peak_flow_cumecs)} m³/s</strong><small>${rise>0?'+'+fmt(rise,0)+'% against baseline':'Reference pathway'}</small></div>
    <div><span>Maximum grid depth · m</span><strong>${fmt(sim.peak_depth_m,2)} m</strong><small>${fmt(sim.wet_cell_count,0)} wet cells</small></div>
    <div><span>Screened direct loss · ₹</span><strong>${moneyHTML(damage.totals.central_inr)}</strong><small>${affected} affected synthetic assets · ${app.result.config.price_year} prices</small></div>`;
  $('cascadeRibbon').innerHTML=timeline.map((item,index)=>`<div class="cascade-step ${index===timeline.length-1?'impact':''}"><i>${index+1}</i><span>${item.node}</span><strong>${clockTime(item.time)} IST</strong><small>${item.event}</small></div>`).join('');
  $('missionSummary').classList.remove('hidden');
}

function renderCascadePanel(branchName='conditional_secondary_failure'){
  if(!app.result)return;
  const branches=app.result.cascade.branches;
  const branch=branches[branchName];
  const hazard=branch.rishikesh_hazard;
  const damage=app.result.spatial_damage[branchName];
  const baselineFlow=branches.no_secondary_failure.rishikesh_hazard.peak_flow_cumecs;
  const conditionalFlow=branches.conditional_secondary_failure.rishikesh_hazard.peak_flow_cumecs;
  const maximum=Math.max(baselineFlow,conditionalFlow,1);
  const badge=$('cascadeBranchBadge');
  badge.textContent=branch.koteshwar.failure_triggered?'Secondary breach pathway':'Contained pathway';
  badge.className=`tag ${branch.koteshwar.failure_triggered?'warning':'ready'}`;
  $('cascadeSummary').innerHTML=`
    <div class="cascade-outcome ${branch.koteshwar.failure_triggered?'alert':''}">
      <span>Koteshwar response</span><strong>${branch.koteshwar.failure_triggered?'Conditional failure triggered':'Storage attenuates the wave'}</strong>
      <small>${branch.koteshwar.failure_triggered?'Additional breach hydrograph joins the routed event.':'No secondary breach hydrograph is added.'}</small>
    </div>
    <div class="cascade-key-metrics">
      <div><span>Arrival · IST</span><strong>${clockTime(hazard.arrival_time)}</strong></div>
      <div><span>Peak discharge · m³/s</span><strong>${fmt(hazard.peak_flow_cumecs)} m³/s</strong></div>
      <div><span>Direct loss · ₹</span><strong>${moneyHTML(damage.totals.central_inr)}</strong></div>
    </div>
    <div class="cascade-compare">
      <p><strong>Peak-flow amplification</strong><span>Same upstream event, two downstream pathways</span></p>
      <label>Contained <i><b style="width:${baselineFlow/maximum*100}%"></b></i><em>${fmt(baselineFlow)} m³/s</em></label>
      <label>Secondary breach <i><b class="alert" style="width:${conditionalFlow/maximum*100}%"></b></i><em>${fmt(conditionalFlow)} m³/s</em></label>
    </div>`;
}

function drawEmptyChart(){
  const canvas=$('hydroChart'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#edf4f5';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#6c818b';ctx.font='14px system-ui';ctx.textAlign='center';ctx.fillText('Rainfall (mm) and discharge (m³/s) will appear after an eligible run.',canvas.width/2,canvas.height/2);
}

function drawChart(hydrology,flow){
  const canvas=$('hydroChart'),ctx=canvas.getContext('2d');
  const rain=(app.state.rainfall||[]).slice(-24).map(point=>({value:Number(point.value||point.mm||0),time:point.time||point.observed_at}));
  const left=72,right=72,top=34,bottom=42,w=canvas.width-left-right,h=canvas.height-top-bottom;
  const maxFlow=niceCeiling(Math.max(...flow.map(point=>Number(point.flow_cumecs)),1));
  const maxRain=niceCeiling(Math.max(...rain.map(point=>point.value),1));
  const timestamps=[...flow.map(point=>Date.parse(point.time)),...rain.map(point=>Date.parse(point.time))].filter(Number.isFinite);
  const minTime=Math.min(...timestamps), maxTime=Math.max(...timestamps);
  const timeSpan=Math.max(1,maxTime-minTime);
  const timeX=(value,index,total)=>Number.isFinite(Date.parse(value))?left+(Date.parse(value)-minTime)/timeSpan*w:left+index/Math.max(1,total-1)*w;
  ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#fbfdfd';ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.font='11px system-ui';ctx.lineWidth=1;
  for(let tick=0;tick<=4;tick++){
    const y=top+h-tick*h/4;
    ctx.strokeStyle='#dce8ea';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(left+w,y);ctx.stroke();
    ctx.fillStyle='#526d78';ctx.textBaseline='middle';ctx.textAlign='right';ctx.fillText(fmt(maxFlow*tick/4,0),left-9,y);
    ctx.textAlign='left';ctx.fillText(fmt(maxRain*tick/4,1),left+w+9,y);
  }
  ctx.fillStyle='#102a38';ctx.textBaseline='alphabetic';ctx.textAlign='left';ctx.fillText('Discharge (m³/s)',left,18);
  ctx.textAlign='right';ctx.fillText('Rainfall (mm)',left+w,18);
  ctx.fillStyle='rgba(71,166,226,.48)';
  rain.forEach((point,index)=>{const x=timeX(point.time,index,rain.length),bar=point.value/maxRain*h;ctx.fillRect(x-5,top+h-bar,10,bar)});
  ctx.strokeStyle='#007f78';ctx.lineWidth=3;ctx.beginPath();
  flow.forEach((point,index)=>{const x=timeX(point.time,index,flow.length),y=top+h-Number(point.flow_cumecs)/maxFlow*h;index?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
  const timeTicks=[minTime,minTime+timeSpan/2,maxTime];
  ctx.fillStyle='#526d78';ctx.font='10px system-ui';ctx.textBaseline='top';
  timeTicks.forEach((time,position)=>{const x=left+position*w/2;ctx.textAlign=position===0?'left':position===timeTicks.length-1?'right':'center';ctx.fillText(clockTime(time),x,top+h+10)});
  ctx.textAlign='center';ctx.fillText('Time (IST)',left+w/2,canvas.height-12);
  $('chartNote').textContent=`SI scale: rainfall 0–${fmt(maxRain,1)} mm; discharge 0–${fmt(maxFlow,0)} m³/s. Rainfall-runoff method: ${hydrology.method}. Estimated peak inflow ${fmt(hydrology.peak_flow_cumecs)} m³/s. ${hydrology.assumption}`;
}

boot().catch(error=>{console.error(error);$('systemStatus').textContent=`Startup failed: ${error.message}`});
