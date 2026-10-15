import React from 'react';
export function Avatar({name='',size=38,style}){
  return <span title={name} style={{width:size,height:size,borderRadius:'50%',background:'var(--avatar-bg)',color:'#fff',display:'inline-grid',placeItems:'center',fontSize:Math.round(size*0.47),flexShrink:0,...style}}>{(name[0]||'?').toUpperCase()}</span>;
}