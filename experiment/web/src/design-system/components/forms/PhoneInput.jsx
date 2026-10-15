import React from 'react';
export function PhoneInput({code='+971',country='ae',value,onChange,placeholder,style}){
  return <div style={{display:'flex',height:'var(--control-height-input)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-sm)',background:'var(--surface-card)',overflow:'hidden',...style}}>
    <div style={{display:'flex',alignItems:'center',gap:6,padding:'0 10px',borderRight:'1px solid var(--border-default)'}}>
      <img src={'https://flagcdn.com/'+country+'.svg'} alt="" style={{width:28,height:18,objectFit:'cover',borderRadius:2}} />
      <span style={{width:0,height:0,borderLeft:'4px solid transparent',borderRight:'4px solid transparent',borderTop:'5px solid var(--text-secondary)'}}></span></div>
    <span style={{display:'flex',alignItems:'center',paddingLeft:10,color:'var(--text-value)',fontSize:'var(--font-size-lg)'}}>{code}</span>
    <input value={value} onChange={onChange} placeholder={placeholder} style={{flex:1,minWidth:0,border:'none',padding:'0 10px',fontSize:'var(--font-size-lg)',color:'var(--text-value)',outline:'none',fontFamily:'var(--font-sans)'}} />
  </div>;
}