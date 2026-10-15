import React from 'react';
export function Icon({name,size=18,color='currentColor',style,...rest}){
  const url='url(https://unpkg.com/lucide-static@0.453.0/icons/'+name+'.svg)';
  return <span aria-hidden="true" style={{display:'inline-block',flexShrink:0,width:size,height:size,background:color,WebkitMaskImage:url,maskImage:url,WebkitMaskSize:'contain',maskSize:'contain',WebkitMaskRepeat:'no-repeat',maskRepeat:'no-repeat',WebkitMaskPosition:'center',maskPosition:'center',...style}} {...rest}></span>;
}