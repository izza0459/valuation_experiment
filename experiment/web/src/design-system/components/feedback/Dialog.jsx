import React from 'react';
import { Icon } from '../core/Icon.jsx';
export function Dialog({open=true,title,subtitle,onClose,actions,width=560,children}){
  if(!open)return null;
  return <div style={{position:'fixed',inset:0,background:'var(--backdrop)',zIndex:50,display:'grid',placeItems:'center',padding:24}}>
    <div style={{width:'min('+width+'px,100%)',maxHeight:'calc(100vh - 48px)',background:'var(--surface-card)',borderRadius:'var(--radius-2xl)',display:'flex',flexDirection:'column',overflow:'hidden',boxShadow:'var(--shadow-popover)'}}>
      <div style={{padding:'20px 28px',borderBottom:'1px solid var(--border-subtle)',display:'flex',justifyContent:'space-between',alignItems:'center',gap:12}}>
        <div><div style={{fontSize:'var(--text-section-title)',fontWeight:500}}>{title}</div>{subtitle&&<div style={{fontSize:'var(--font-size-base)',color:'var(--text-muted)'}}>{subtitle}</div>}</div>
        {onClose&&<button onClick={onClose} aria-label="Close" style={{border:'none',background:'none',cursor:'pointer',padding:4}}><Icon name="x" size={20} color="var(--text-secondary)"/></button>}</div>
      <div style={{flex:1,overflow:'auto',padding:'22px 28px'}}>{children}</div>
      {actions&&<div style={{padding:'16px 28px',borderTop:'1px solid var(--border-subtle)',display:'flex',justifyContent:'flex-end',gap:10}}>{actions}</div>}
    </div></div>;
}