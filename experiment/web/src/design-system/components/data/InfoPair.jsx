import React from 'react';
const C={default:'var(--text-primary)',link:'var(--text-link)',accent:'var(--text-accent)'};
export function InfoPair({label,value,tone='default',children,style}){
  return <div style={{display:'flex',flexDirection:'column',gap:6,minWidth:0,...style}}>
    <div style={{fontSize:'var(--font-size-base)',color:'var(--text-secondary)'}}>{label}</div>
    <div style={{fontSize:'var(--font-size-xl)',color:C[tone]||C.default,overflowWrap:'anywhere'}}>{children||value}</div></div>;
}