import React from 'react';
export function Card({variant='plain',padding=24,children,style}){
  const b=variant==='active'?'1px solid var(--border-active)':variant==='bordered'?'1px solid var(--border-subtle)':'none';
  return <section style={{background:'var(--surface-card)',borderRadius:'var(--radius-2xl)',border:b,boxShadow:variant==='plain'?'var(--shadow-card)':'none',padding,boxSizing:'border-box',minWidth:0,...style}}>{children}</section>;
}