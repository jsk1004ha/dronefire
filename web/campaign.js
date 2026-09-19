'use strict';
(() => {
  labels.program=['전체 연구 실행','케이스 생성, native 계산, 분석, 보고서 상태를 함께 추적합니다.'];
  labels.nativefields=['native 격자·시간 탐색','FDS·OpenFOAM 원본 격자 좌표와 저장 시점의 물리량을 표시합니다.'];
  let currentStudy=null, job=null, collection=null, angle=-.65, elevation=.4;
  const status=text=>$('study-status').textContent=text;
  function renderStudy(result){
    currentStudy=result;if(!result)return;
    $('study-count').textContent=`${result.cases.length}/${result.design.length} 조건 · ${result.status}`;
    $('study-cases').replaceChildren(...result.cases.map(c=>{const r=el('tr');for(const v of [c.condition_id,c.status,c.observation_status??'미평가',c.data_error??c.observation_reason??c.reason??'—'])r.append(el('td',typeof v==='string'?v:JSON.stringify(v)));return r;}));
    const base=`/api/campaign/${result.campaign_id}/`;
    const finished=!!result.finished_utc;$('study-zip').hidden=!finished;$('study-zip').href=base+'research_results.zip';
    $('study-reports').replaceChildren();
    if(finished){for(const [file,name]of [['method_comparison.html','연구 1 보고서'],['drone_feasibility.html','연구 2 보고서'],['campaign.json','전체 원자료 JSON']]){const a=el('a',name,'button secondary small');a.href=base+file;a.target='_blank';a.rel='noopener';$('study-reports').append(a,document.createTextNode(' '));}$('study-hrr').src=base+'hrr_comparison.png';$('study-hrr').hidden=false;}
  }
  async function refresh(){try{renderStudy(await api('/api/campaign/latest'));}catch(e){status(e.message);}}
  $('study-refresh').onclick=refresh;
  $('study-run').onclick=async()=>{
    try{const cfg=JSON.parse($('study-config').value);const reply=await api('/api/campaign/run',cfg);job=reply.job_id;$('study-run').disabled=true;$('study-stop').disabled=false;
      for(;;){const j=await api(`/api/jobs/${job}`);status(`${Math.round(j.progress*100)}% · ${j.message}`);await refresh();if(j.status==='failed')throw new Error(j.message);if(j.status==='completed')break;await new Promise(r=>setTimeout(r,1500));}
    }catch(e){status(`실행 중단: ${e.message}`);}finally{$('study-run').disabled=false;$('study-stop').disabled=true;job=null;}
  };
  $('study-stop').onclick=async()=>{if(job){await api('/api/campaign/cancel',{job_id:job});status('현재 native 케이스가 끝나면 다음 케이스 실행을 중단합니다.');}};
  function currentField(){return collection?.fields[Number($('native-quantity').value)||0];}
  function scalarColor(value){const stops=[[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]],x=Math.max(0,Math.min(1,value))*(stops.length-1),i=Math.min(stops.length-2,Math.floor(x)),u=x-i;return `rgb(${stops[i].map((v,k)=>Math.round(v+(stops[i+1][k]-v)*u)).join(' ')})`;}
  function setField(){const f=currentField();if(!f)return;$('native-time').max=Math.max(0,f.frames.length-1);$('native-time').value=0;drawNative();}
  async function loadFieldset(){try{collection=await api('/api/fieldsets/'+$('native-dataset').value);$('native-quantity').replaceChildren(...collection.fields.map((f,i)=>{const o=el('option',`${f.quantity} · ${f.units}`);o.value=i;return o;}));setField();}catch(e){$('native-info').textContent=e.message;}}
  function drawNative(){
    const canvas=$('native-canvas'),w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;
    const dpr=window.devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.fillStyle='#0f172a';ctx.fillRect(0,0,w,h);
    const f=currentField();if(!f)return;const frame=f.frames[Number($('native-time').value)||0],axes=f.geometry.axes_m;if(!axes){$('native-info').textContent='좌표 메타데이터 없음';return;}
    $('native-time-label').textContent=`${format(frame.time_s,4)} s`;
    $('native-info').textContent=`${f.geometry.topology} · ${f.geometry.shape_kji.slice().reverse().join(' × ')} · ${f.frames.length} 저장 시점 · ${collection.run_status??'native 계산 / 실증 미검증'}`;
    $('native-provenance').textContent=`${f.provenance.source_path} · SHA-256 ${f.provenance.source_sha256}`;
    const lo=Math.min(...f.frames.map(x=>x.minimum)),hi=Math.max(...f.frames.map(x=>x.maximum));
    $('native-legend').textContent=`고정 범례 ${format(lo)} → ${format(hi)} ${f.units} · 원본 좌표 m · 표시시간 ${format(frame.time_s,4)} s`;
    const center=['x','y','z'].map(k=>(axes[k][0]+axes[k][axes[k].length-1])/2),span=Math.max(...['x','y','z'].map(k=>axes[k][axes[k].length-1]-axes[k][0]),.01),scale=Math.min(w*.65,h*.72)/span;
    const project=(x,y,z)=>{x-=center[0];y-=center[1];z-=center[2];const a=Math.cos(angle)*x-Math.sin(angle)*y,b=Math.sin(angle)*x+Math.cos(angle)*y;return [w/2+a*scale,h/2-(z*Math.cos(elevation)+b*Math.sin(elevation))*scale,b*Math.cos(elevation)-z*Math.sin(elevation)];};
    const vals=frame.values.flat(Infinity),pts=[];let n=0;
    for(const z of axes.z)for(const y of axes.y)for(const x of axes.x){const value=vals[n++];if(!Number.isFinite(value))continue;pts.push([...project(x,y,z),value]);}
    pts.sort((a,b)=>a[2]-b[2]);const size=Math.max(2,Math.min(9,scale*span/Math.max(axes.x.length,axes.y.length,axes.z.length)*1.12));
    for(const p of pts){const a=Math.max(0,Math.min(1,(p[3]-lo)/Math.max(hi-lo,1e-12)));ctx.fillStyle=scalarColor(a);ctx.fillRect(p[0]-size/2,p[1]-size/2,size,size);}
    ctx.fillStyle='#fdfcfc';ctx.font='12px "Berkeley Mono", "JetBrains Mono", "Noto Sans Mono CJK KR", "NanumGothicCoding", D2Coding, GulimChe, Consolas, monospace';ctx.fillText(`${f.quantity} [${f.units}] · ${f.geometry.topology} · native / unvalidated`,20,30);
  }
  $('native-dataset').onchange=loadFieldset;$('native-quantity').onchange=setField;$('native-time').oninput=drawNative;$('native-reset').onclick=()=>{angle=-.65;elevation=.4;drawNative();};
  const canvas=$('native-canvas');let drag=null;canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};canvas.onpointermove=e=>{if(drag){angle+=(e.clientX-drag[0])*.01;elevation=Math.max(-1.5,Math.min(1.5,elevation+(e.clientY-drag[1])*.01));drag=[e.clientX,e.clientY];drawNative();}};canvas.onpointerup=canvas.onpointercancel=()=>drag=null;new ResizeObserver(drawNative).observe(canvas);
  (async()=>{try{$('study-config').value=JSON.stringify(await api('/api/campaign/defaults'),null,2);status('준비됨 · native 실행은 계산 자원과 조건 수에 따라 오래 걸릴 수 있습니다.');await refresh();const sets=await api('/api/fieldsets');$('native-dataset').replaceChildren(...sets.map(s=>{const o=el('option',s.id);o.value=s.id;return o;}));if(sets.some(s=>s.id==='fds_reactive_C0'))$('native-dataset').value='fds_reactive_C0';if(sets.length)await loadFieldset();}catch(e){status(e.message);}})();
})();
