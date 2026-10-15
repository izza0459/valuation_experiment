import React from 'react';
export function Field({label,optional=false,required=false,error,helper,layout='stacked',children,style}){
  const lab=<div style={{fontSize:'var(--text-label)',color:layout==='inline'?'var(--text-secondary)':'var(--text-primary)',textAlign:layout==='inline'?'right':'left',paddingTop:layout==='inline'?12:0}}>
    {label}{required&&<span style={{color:'var(--text-accent)'}}> *</span>}{optional&&<span style={{color:'var(--text-muted)'}}> (optional)</span>}</div>;
  const body=<div style={{display:'flex',flexDirection:'column',gap:6,minWidth:0}}>{children}
    {error&&<div style={{color:'var(--text-error)',fontSize:'var(--font-size-base)',letterSpacing:.2}}>{error===true?'This field is required':error}</div>}
    {helper&&!error&&<div style={{color:'var(--text-secondary)',fontSize:'var(--font-size-base)'}}>{helper}</div>}</div>;
  if(layout==='inline')return <div style={{display:'grid',gridTemplateColumns:'minmax(140px,300px) minmax(0,1fr)',gap:36,alignItems:'start',...style}}>{lab}{body}</div>;
  return <div style={{display:'flex',flexDirection:'column',gap:10,minWidth:0,...style}}>{lab}{body}</div>;
}