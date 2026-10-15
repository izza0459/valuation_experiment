import React from 'react';
export function Tabs({items=[],active,onChange,size='md',style}){
  const fs=size==='sm'?'var(--font-size-md)':'var(--font-size-xl)';
  return <div style={{display:'flex',gap:40,padding:'0 24px',borderBottom:'1px solid var(--border-subtle)',overflowX:'auto',...style}}>
    {items.map(it=>{const label=typeof it==='string'?it:it.label;const count=typeof it==='string'?null:it.count;const on=label===active;
      return <span key={label} onClick={()=>onChange&&onChange(label)} style={{padding:'18px 0 14px',fontSize:fs,whiteSpace:'nowrap',cursor:'pointer',color:on?'var(--text-accent)':'var(--text-secondary)',borderBottom:'2px solid '+(on?'var(--action-primary)':'transparent'),marginBottom:-1}}>{label}{count!=null&&<span style={{fontSize:'var(--font-size-base)',marginLeft:6,opacity:.7}}>{count}</span>}</span>;})}
  </div>;
}