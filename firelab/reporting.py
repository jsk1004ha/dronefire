"""Portable research reports generated from saved campaign records, never invented scores."""
import csv
import html
import json
from pathlib import Path
import zipfile
from .intake import json_write


def write_csv(path, rows, columns):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def line_png(path, records, channel, ylabel):
    from PIL import Image, ImageDraw, ImageFont
    curve_count=sum(bool(r.get('channels',{}).get(channel)) for r in records)
    image=Image.new('RGB',(1200,max(720,665+((curve_count+3)//4)*23)),'#f7fafc');d=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=16)
    curves=[r for r in records if r.get('channels',{}).get(channel)]
    d.text((55,22),f'{channel} | native unvalidated | intervention-relative time',fill='#192b38',font=font)
    if not curves:
        d.text((55,90),'No native channel available. Not zero.',fill='#8b3a3a',font=font)
        image.save(path);return
    xmin=min(min(r['time_s']) for r in curves);xmax=max(max(r['time_s']) for r in curves)
    ymin=min(0,min(min(r['channels'][channel]) for r in curves));ymax=max(max(r['channels'][channel]) for r in curves)
    if ymax==ymin:ymax=ymin+1
    colors=['#007b73','#3364b4','#985fc4','#d48627','#c34860','#677681']
    d.line((80,80,80,600,1140,600),fill='#8899a4',width=2)
    for i in range(6):
        y=600-i*104;value=ymin+(ymax-ymin)*i/5
        d.line((80,y,1140,y),fill='#e0e8ec')
        d.text((3,y-8),f'{value:.3g}',fill='#425663',font=font)
    for i,r in enumerate(curves):
        pts=[(80+1060*(t-xmin)/max(xmax-xmin,1e-9),600-520*(v-ymin)/(ymax-ymin)) for t,v in zip(r['time_s'],r['channels'][channel])]
        valid=r.get('run_status')=='completed'
        if valid:
            d.line(pts,fill=colors[i%len(colors)],width=2)
        else:
            for j in range(0,len(pts)-1,2):d.line(pts[j:j+2],fill=colors[i%len(colors)],width=2)
        label=r['condition_id'][:22]+('' if valid else ' [incomplete]')
        d.text((85+(i%4)*275,630+(i//4)*23),label,fill=colors[i%len(colors)],font=font)
    d.text((80,55),ylabel,fill='#425663',font=font)
    d.text((975,607),f'{xmin:g}..{xmax:g} seconds',fill='#425663',font=font)
    image.save(path)


def campaign_reports(destination, result):
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=True)
    rows=[]
    ext={r['condition_id']:r for r in result.get('analysis',{}).get('extinction_runs',[])}
    for case in result['cases']:
        e=ext.get(case['condition_id'],{}).get('extinction',{})
        rows.append({'condition_id':case['condition_id'],'mode':case['condition']['mode'],
                     'status':case['status'],'analysis_validity':case.get('observation_status','not_evaluated'),
                     'reason':case.get('data_error') or case.get('observation_reason') or case.get('reason',''),
                     'extinction_time_s':e.get('time_s') if e.get('event') is True else None,
                     'censor_time_s':e.get('observed_through_s',e.get('time_s')) if e.get('event') is False else None,'event':e.get('event'),
                     'evidence_type':'native_unvalidated' if case.get('native') else 'not_evaluated',
                     'case_directory':case.get('run_directory','')})
    write_csv(dest/'case_matrix.csv',rows,list(rows[0]) if rows else ['condition_id','status'])
    write_csv(dest/'single_method_summary.csv',[r for r in rows if r['mode'] in ('control','single')],list(rows[0]) if rows else ['condition_id'])
    interactions=[]
    synergy_by_id={s.get('combination_id'):s for s in result.get('analysis',{}).get('synergy',[])}
    for case in result['cases']:
        if case['condition']['mode'] not in ('simultaneous','sequential'):continue
        actual=synergy_by_id.get(case['condition_id'],{})
        additive=actual.get('additive_synergy_J_m2',{});gain=actual.get('equal_budget_gain_J_m2',{})
        interactions.append({'condition_id':case['condition_id'],'status':case['status'],
                             'additive_synergy_J_m2':additive.get('value'),'equal_budget_gain_J_m2':gain.get('value'),
                             'reason':additive.get('reason','Validated matched partial-dose/equal-budget independent blocks required'),
                             'additive_ci95':json.dumps(additive.get('ci95')),
                             'gain_ci95':json.dumps(gain.get('ci95')),
                             'native_status':case.get('native',{}).get('status')})
    write_csv(dest/'interaction_matrix.csv',interactions,['condition_id','status','additive_synergy_J_m2','equal_budget_gain_J_m2','additive_ci95','gain_ci95','reason','native_status'])
    exposures=[]
    for r in result.get('exposure',{}).get('runs',[]):
        for channel, value in r['channels'].items():
            exposures.append({'case_id':r['case_id'],'condition_id':r['condition_id'],'channel':channel,
                              'status':value['status'],'interval_s':json.dumps(value.get('interval_s'))})
    write_csv(dest/'exposure_summary.csv',exposures,['case_id','condition_id','channel','status','interval_s'])
    records=result.get('records',[])
    line_png(dest/'hrr_comparison.png',records,'hrr_kW','HRR / kW')
    line_png(dest/'heat_flux_comparison.png',records,'heat_flux_kW_m2','Heat flux / kW/m2')
    counts={s:sum(c['status']==s for c in result['cases']) for s in sorted({c['status'] for c in result['cases']})}
    common=['입력과 결과는 연구용 가정 시나리오입니다. 실제 장치의 검증 결과나 인명 생존시간이 아닙니다.',
            f"실행 ID: {result['campaign_id']}",f"조건 수: {len(rows)}; 상태: {counts}",
            'M1/M2 native 화염 입력은 기계적 송풍/펄스 노즐 근사이며 실제 음향장·와류 방출기의 보정 완료를 의미하지 않습니다.',
            'M4/M5 화학·전기–화염 반응은 근거 부족 시 needs_model입니다. 없는 성능을 0이나 임의 순위로 채우지 않습니다.']
    method=['# 연구 1 — 방법 효율과 상호보완성','',*common,'','## 계산 결과','',
            '| 조건 | 솔버 상태 | 분석 유효성 | 소화 이벤트 | 소화 시각 s | 검열 시각 s |','|---|---|---|---|---|---|']
    method.extend(f"| {r['condition_id']} | {r['status']} | {r['analysis_validity']} | {r['event']} | {r['extinction_time_s']} | {r['censor_time_s']} |" for r in rows)
    method.extend(['','관측 종료까지 소화가 없으면 소화 시각은 비워 두고 검열 시각을 별도 기록합니다. 검열 시각은 소화 시간 추정치가 아닙니다.'])
    method.extend(['','## 원자료·분석','',
                   'case_matrix.csv / single_method_summary.csv / interaction_matrix.csv / exposure_summary.csv / campaign.json',
                   'PNG는 저장된 native CSV 시계열에서 동일 축으로 생성했습니다. 결측은 선으로 연결하지 않습니다.',
                   '반복 독립 블록과 검증 근거가 없는 단일 결정론적 계산에서 성공 확률·유의한 시너지를 주장하지 않습니다.'])
    drone=['# 연구 2 — 드론 적용 실효성','',*common,'',
           'D0–D5 결과: drone_study.json, drone_feasibility.csv, drone_requirements.csv, drone_mission_series.csv.',
           'D0/D1의 화재 손실과 D2–D4의 화염 변화는 같은 조건의 native/실측 자료가 있어야 효과 유지율을 계산합니다.',
           '센서 지연·잡음·횡풍·부족한 자원·열 입력 시나리오를 분리합니다. 보정되지 않은 이상 actuator disk는 실제 후류 CFD 검증이 아닙니다.',
           '허용 열 한계나 실측 추력/전력 맵이 없으면 실증 탑재 가능성은 insufficient_evidence로 남깁니다.',
           '',json.dumps(result.get('drone_summary',{}),ensure_ascii=False,indent=2)]
    nominal=[]
    drone_csv=dest/'drone_feasibility.csv'
    if drone_csv.exists():
        with drone_csv.open(encoding='utf-8-sig',newline='') as stream:
            flight_rows=list(csv.DictReader(stream))
        nominal=[r for r in flight_rows if r['scenario_id']=='nominal']
        drone.extend(['','## 가정 기체의 계산 결과','',
                      'D2: 동일 중량 장치 OFF / D3: 작동·위치 무보정 / D4: 작동·위치 보정.',
                      'feasible_in_model은 입력한 비행 제약 판정이며 화재 진압 가능 판정이 아닙니다. 열 입력이 없는 값은 미평가입니다.','',
                      '| 방법 | 조건 | 상태 | 최대 위치 오차 m | 최대 전력 W | 잔여 에너지 Wh |',
                      '|---|---|---|---:|---:|---:|'])
        for r in nominal:
            drone.append(f"| {r['method_id']} | {r['condition_id']} | {r['status']} | {float(r['max_position_error_m']):.4f} | {float(r['peak_power_W']):.2f} | {float(r['remaining_Wh']):.2f} |")
        from PIL import Image,ImageDraw,ImageFont
        im=Image.new('RGB',(1000,530),'#f7fafc');draw=ImageDraw.Draw(im);font=ImageFont.load_default(size=17)
        draw.text((35,20),'Drone positioning | assumed model | D3 uncontrolled / D4 controlled',fill='#192b38',font=font)
        draw.text((35,48),'D3: orange     D4: teal',fill='#425663',font=font)
        bars={(r['method_id'],r['condition_id']):float(r['max_position_error_m']) for r in nominal if r['condition_id'] in ('D3','D4')}
        scale=max(bars.values(),default=1.) or 1.
        for i,method_id in enumerate(('M1','M2','M3','M4','M5')):
            y=80+i*80;draw.text((35,y+12),method_id,fill='#192b38',font=font)
            for j,condition in enumerate(('D3','D4')):
                value=bars.get((method_id,condition))
                if value is None:continue
                color=('#d48627','#007b73')[j];width=740*value/scale
                draw.rectangle((100,y+j*27,100+max(width,1),y+j*27+18),fill=color)
                draw.text((110+width,y+j*27),f'{value:.4f} m',fill=color,font=font)
        draw.text((35,500),'Maximum position error over full mission; not suppression effectiveness.',fill='#425663',font=font)
        im.save(dest/'drone_position_comparison.png')
    for name,lines in [('method_comparison',method),('drone_feasibility',drone)]:
        text='\n'.join(lines)
        (dest/(name+'.md')).write_text(text,encoding='utf-8')
        (dest/(name+'.html')).write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+name+'</title><style>body{background:#fdfcfc;color:#201d1d;font:15px/1.8 ui-monospace,Consolas,monospace;max-width:1100px;margin:40px auto;padding:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}img{max-width:100%}</style><pre>'+html.escape(text)+'</pre>'+('<img src="hrr_comparison.png"><img src="heat_flux_comparison.png">' if name=='method_comparison' else '<img src="drone_position_comparison.png">' if nominal else '')+'</html>',encoding='utf-8')
    json_write(dest/'campaign.json',result)
    with zipfile.ZipFile(dest/'research_results.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for f in sorted(dest.iterdir()):
            if f.is_file() and (f.suffix in ('.json','.csv','.md','.html','.png') or f.name in ('source_snapshot.zip','reanalysis_source_snapshot.zip')):
                archive.write(f,f.name)
