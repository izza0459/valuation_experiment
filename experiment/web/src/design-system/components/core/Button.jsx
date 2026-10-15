import React from 'react';
const V={
  primary:{background:'var(--action-primary)',color:'var(--text-on-primary)',borderColor:'var(--action-primary)'},
  soft:{background:'var(--surface-accent-strong)',color:'var(--text-accent)',borderColor:'transparent'},
  outline:{background:'var(--surface-card)',color:'var(--text-primary)',borderColor:'var(--border-default)'},
  success:{background:'var(--green-50)',color:'var(--green-600)',borderColor:'transparent'},
  danger:{background:'var(--surface-accent-strong)',color:'var(--text-accent)',borderColor:'transparent'},
  ghost:{background:'transparent',color:'var(--text-accent)',borderColor:'transparent'}};
const HOV={primary:'var(--action-primary-hover)',soft:'var(--red-200)',outline:'var(--surface-subtle)',success:'var(--green-100)',danger:'var(--red-200)',ghost:'var(--surface-accent)'};
const SZ={sm:{height:'var(--control-height-sm)',padding:'0 14px',fontSize:'var(--font-size-base)'},md:{height:'var(--control-height-md)',padding:'0 18px',fontSize:'var(--font-size-lg)'},lg:{height:'var(--control-height-lg)',padding:'0 22px',fontSize:'var(--font-size-xl)'}};
export function Button({variant='primary',size='md',icon,block=false,disabled=false,children,style,...rest}){
  const [h,setH]=React.useState(false);
  return <button disabled={disabled} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)}
    style={{display:block?'flex':'inline-flex',width:block?'100%':undefined,alignItems:'center',justifyContent:'center',gap:8,border:'1px solid',borderRadius:'var(--radius-sm)',fontFamily:'var(--font-sans)',fontWeight:400,cursor:disabled?'not-allowed':'pointer',opacity:disabled?.45:1,whiteSpace:'nowrap',transition:'background var(--duration-fast)',...(V[variant]||V.primary),...(SZ[size]||SZ.md),...(h&&!disabled?{background:HOV[variant]}:{}),...style}} {...rest}>{icon}{children}</button>;
}