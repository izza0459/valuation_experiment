import React from 'react';
export function OptionCard({title,price,oldPrice,description,meta=[],selected=false,onSelect}){
  return <div onClick={onSelect} style={{position:'relative',border:'1px solid '+(selected?'var(--border-focus)':'var(--border-subtle)'),borderRadius:'var(--radius-xl)',padding:'16px 18px',display:'flex',flexDirection:'column',gap:4,cursor:'pointer',background:'var(--surface-card)'}}>
    <span style={{position:'absolute',top:16,right:16,width:18,height:18,borderRadius:'50%',border:'1px solid '+(selected?'var(--border-focus)':'var(--gray-400)'),display:'grid',placeItems:'center'}}>{selected&&<span style={{width:10,height:10,borderRadius:'50%',background:'var(--action-primary)'}}></span>}</span>
    <div style={{fontSize:'var(--font-size-xl)',fontWeight:500,textTransform:'uppercase',paddingRight:28}}>{title}</div>
    <div style={{fontSize:'var(--font-size-xl)'}}><b style={{color:'var(--text-accent)',fontWeight:600}}>{price}</b> {oldPrice&&<s style={{color:'var(--text-secondary)'}}>{oldPrice}</s>}</div>
    {description&&<div style={{fontSize:'var(--font-size-xl)'}}>{description}</div>}
    {meta.length>0&&<div style={{fontSize:'var(--font-size-lg)',color:'var(--text-secondary)'}}>{meta.join('  •  ')}</div>}
  </div>;
}