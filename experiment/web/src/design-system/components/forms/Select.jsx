import React from 'react';
export function Select({options=[],placeholder,value,onChange,invalid=false,style,...rest}){
  const empty=value===undefined||value==='';
  return <div style={{position:'relative',width:'100%',...style}}>
    <select value={value} onChange={onChange} {...rest} style={{appearance:'none',WebkitAppearance:'none',height:'var(--control-height-input)',width:'100%',border:'1px solid '+(invalid?'var(--border-focus)':'var(--border-default)'),borderRadius:'var(--radius-sm)',padding:'0 40px 0 14px',fontSize:'var(--font-size-xl)',color:empty?'var(--text-placeholder)':'var(--text-value)',background:'var(--surface-card)',fontFamily:'var(--font-sans)',cursor:'pointer'}}>
      {placeholder&&<option value="">{placeholder}</option>}
      {options.map(o=>typeof o==='string'?<option key={o} value={o}>{o}</option>:<option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
    <span style={{position:'absolute',right:16,top:'50%',marginTop:-3,width:0,height:0,borderLeft:'6px solid transparent',borderRight:'6px solid transparent',borderTop:'6px solid var(--text-secondary)',pointerEvents:'none'}}></span>
  </div>;
}