import React from 'react';
export function Textarea({invalid=false,rows=4,style,...rest}){
  return <textarea rows={rows} {...rest} style={{width:'100%',boxSizing:'border-box',border:'1px solid '+(invalid?'var(--border-focus)':'var(--border-default)'),borderRadius:'var(--radius-sm)',padding:'12px 14px',fontSize:'var(--font-size-lg)',color:'var(--text-primary)',background:'var(--surface-card)',resize:'vertical',fontFamily:'var(--font-sans)',...style}} />;
}