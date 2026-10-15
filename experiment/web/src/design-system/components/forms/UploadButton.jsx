import React from 'react';
import { Icon } from '../core/Icon.jsx';
export function UploadButton({label='Upload',onClick,disabled=false}){
  return <button onClick={onClick} disabled={disabled} style={{display:'inline-flex',alignItems:'center',gap:12,border:'none',background:'none',padding:0,cursor:'pointer',fontSize:'var(--font-size-lg)',color:'var(--text-primary)',fontFamily:'var(--font-sans)',opacity:disabled?.45:1}}>
    <span style={{width:32,height:32,borderRadius:'50%',border:'1px solid var(--gray-400)',display:'grid',placeItems:'center'}}><Icon name="plus" size={16} color="var(--text-muted)" /></span>{label}</button>;
}