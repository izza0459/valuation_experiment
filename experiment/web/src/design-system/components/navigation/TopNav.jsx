import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { IconButton } from '../core/IconButton.jsx';
import { Avatar } from '../core/Avatar.jsx';
export function TopNav({items=[],active,onNavigate,user='Admin',logo}){
  return <header style={{background:'var(--surface-card)',height:'var(--header-height)',display:'flex',alignItems:'center',padding:'0 20px',gap:28,boxShadow:'var(--shadow-header)',position:'sticky',top:0,zIndex:20}}>
    <div style={{display:'flex',alignItems:'center',gap:16,flexShrink:0}}>
      {logo||<span style={{fontSize:30,fontWeight:700,letterSpacing:-1,lineHeight:1}}>dubizzle <span style={{color:'var(--brand-red)'}}>cars</span></span>}
      <span style={{width:1,height:40,background:'var(--border-subtle)'}}></span>
      <span style={{display:'flex',alignItems:'center',gap:12}}><span style={{textAlign:'center',lineHeight:1.1}}><span style={{display:'block',fontSize:24,fontWeight:500,letterSpacing:1}}>crm</span><span style={{fontSize:'var(--font-size-md)'}}>CRM</span></span><Icon name="chevron-down" size={18}/></span>
    </div>
    <nav style={{display:'flex',alignItems:'center',gap:30,flex:1,minWidth:0,overflow:'hidden',whiteSpace:'nowrap',fontSize:'var(--text-nav)',fontWeight:500}}>
      {items.map(it=>{const on=it.label===active;return <span key={it.label} onClick={()=>onNavigate&&onNavigate(it.label)} style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',height:'var(--header-height)',boxSizing:'border-box',color:on?'var(--text-accent)':'var(--text-primary)',borderBottom:'2px solid '+(on?'var(--action-primary)':'transparent')}}>{it.label}{it.menu&&<Icon name="chevron-down" size={16}/>}</span>;})}
    </nav>
    <div style={{display:'flex',gap:18,alignItems:'center',flexShrink:0}}>
      <IconButton icon="calendar-days" label="Calendar"/><IconButton icon="message-circle" label="WhatsApp"/><IconButton icon="bell" label="Notifications"/><Avatar name={user}/>
    </div>
  </header>;
}