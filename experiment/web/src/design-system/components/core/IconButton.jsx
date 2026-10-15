import React from 'react';
import { Icon } from './Icon.jsx';
export function IconButton({icon,size=36,variant='soft',label,onClick,style}){
  const [h,setH]=React.useState(false);
  const soft=variant==='soft';
  return <button aria-label={label} title={label} onClick={onClick} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)}
    style={{width:size,height:size,borderRadius:'50%',border:soft?'none':'1px solid var(--border-default)',display:'grid',placeItems:'center',cursor:'pointer',padding:0,
      background:soft?(h?'var(--red-200)':'var(--surface-accent-strong)'):(h?'var(--surface-subtle)':'var(--surface-card)'),...style}}>
    <Icon name={icon} size={Math.round(size*0.47)} color={soft?'var(--text-accent)':'var(--text-secondary)'} /></button>;
}