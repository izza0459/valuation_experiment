import React from 'react';
export function Input({invalid=false,style,...rest}){
  return <input {...rest} style={{height:'var(--control-height-input)',width:'100%',boxSizing:'border-box',border:'1px solid '+(invalid?'var(--border-focus)':'var(--border-default)'),borderRadius:'var(--radius-sm)',padding:'0 14px',fontSize:'var(--font-size-lg)',color:'var(--text-value)',background:'var(--surface-card)',fontFamily:'var(--font-sans)',...style}} />;
}