import React from 'react';
export function OptionGroup({options=[],value,onChange,disabled=false}){
  return <div style={{display:'flex',flexWrap:'wrap',gap:8}}>{options.map(o=>{const on=value===o;
    return <button key={o} disabled={disabled} onClick={()=>onChange&&onChange(o)} style={{height:'var(--control-height-md)',padding:'0 16px',borderRadius:'var(--radius-sm)',fontSize:'var(--font-size-md)',cursor:'pointer',fontFamily:'var(--font-sans)',border:'1px solid '+(on?'var(--border-focus)':'var(--border-default)'),background:on?'var(--surface-accent)':'var(--surface-card)',color:on?'var(--text-accent)':'var(--text-primary)'}}>{o}</button>;})}</div>;
}