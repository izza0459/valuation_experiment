import React from 'react';
export function StageProgress({steps=[],current,onStepClick}){
  const idx=steps.findIndex(s=>s.label===current);
  return <div style={{display:'flex',gap:12,alignItems:'stretch'}}>
    <div style={{flex:1,minWidth:0,overflowX:'auto'}}><div style={{display:'flex',gap:10,minWidth:'max-content'}}>
      {steps.map((s,i)=>{const done=s.state?s.state==='done':i<idx;const cur=i===idx;
        return <div key={s.label} onClick={()=>onStepClick&&onStepClick(s,i)} style={{width:s.width||160,display:'flex',flexDirection:'column',gap:8,cursor:onStepClick?'pointer':'default'}}>
          <div style={{fontSize:'var(--font-size-md)',textAlign:'center',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis',color:cur?'var(--text-accent)':done?'#d45a5a':'var(--text-secondary)',fontWeight:cur?500:400}}>{s.label}</div>
          <div style={{height:4,borderRadius:2,background:cur?'var(--action-primary)':done?'#e27d7d':'var(--gray-400)'}}></div></div>;})}
    </div></div>
    <div style={{flexShrink:0,background:'var(--surface-accent)',borderRadius:'var(--radius-lg)',padding:'10px 16px',textAlign:'center',display:'flex',flexDirection:'column',justifyContent:'center'}}>
      <div style={{fontSize:'var(--font-size-base)'}}>Current Stage</div><div style={{fontSize:'var(--font-size-2xl)',fontWeight:600,color:'var(--text-accent)'}}>{idx+1}/{steps.length}</div></div>
  </div>;
}