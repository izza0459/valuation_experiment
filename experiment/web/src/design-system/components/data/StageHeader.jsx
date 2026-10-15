import React from 'react';
import { Tag } from '../core/Tag.jsx';
import { Avatar } from '../core/Avatar.jsx';
export function StageHeader({name,status='In Progress',tone='blue',assignee}){
  return <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12,flexWrap:'wrap'}}>
    <div style={{display:'flex',alignItems:'center',gap:10}}><span style={{fontSize:'var(--text-section-title)',fontWeight:500}}>{name}</span><Tag tone={tone}>{status}</Tag></div>
    {assignee&&<div style={{display:'flex',alignItems:'center',gap:8,background:'var(--surface-accent)',borderRadius:'var(--radius-md)',padding:'6px 14px',fontSize:'var(--font-size-xl)'}}><Avatar name={assignee} size={26}/>{assignee}</div>}
  </div>;
}