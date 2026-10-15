import React from 'react';
export function Table({columns=[],rows=[],style}){
  return <div style={{overflowX:'auto',...style}}><table style={{width:'100%',borderCollapse:'collapse',fontSize:'var(--font-size-md)'}}>
    <thead><tr style={{background:'var(--surface-subtle)'}}>{columns.map(c=><th key={c.key} style={{textAlign:c.align||'left',fontWeight:400,color:'var(--text-muted)',fontSize:'var(--font-size-base)',padding:'12px 14px',whiteSpace:'nowrap',borderBottom:'1px solid var(--border-subtle)'}}>{c.label}</th>)}</tr></thead>
    <tbody>{rows.map((r,i)=><tr key={r.id||i}>{columns.map(c=><td key={c.key} style={{padding:'12px 14px',whiteSpace:'nowrap',textAlign:c.align||'left',borderBottom:'1px solid var(--border-divider)'}}>{c.render?c.render(r):r[c.key]}</td>)}</tr>)}</tbody>
  </table></div>;
}