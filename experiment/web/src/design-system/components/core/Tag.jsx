import React from 'react';
const T={purple:['var(--purple-50)','var(--purple-600)'],blue:['var(--blue-50)','var(--blue-600)'],green:['var(--green-50)','var(--green-600)'],amber:['var(--amber-50)','var(--amber-600)'],red:['var(--red-150)','var(--red-600)'],neutral:['var(--gray-150)','var(--gray-700)']};
export function Tag({tone='neutral',children,style}){
  const [bg,fg]=T[tone]||T.neutral;
  return <span style={{display:'inline-flex',alignItems:'center',gap:4,background:bg,color:fg,fontSize:'var(--font-size-base)',lineHeight:1.4,padding:'2px 10px',borderRadius:'var(--radius-sm)',whiteSpace:'nowrap',...style}}>{children}</span>;
}