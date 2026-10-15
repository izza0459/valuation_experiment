import React from 'react';
export function Toast({message,style}){
  if(!message)return null;
  return <div role="status" style={{position:'fixed',bottom:24,left:'50%',transform:'translateX(-50%)',background:'var(--surface-inverse)',color:'#fff',padding:'12px 20px',borderRadius:'var(--radius-lg)',fontSize:'var(--font-size-md)',zIndex:60,maxWidth:'90vw',...style}}>{message}</div>;
}