/**
 * @startingPoint section="Data" subtitle="Admin data table with tinted header" viewport="900x300"
 */
export interface TableColumn { key: string; label: string; align?: 'left' | 'right' | 'center'; render?: (row: any) => React.ReactNode; }
export interface TableProps { columns: TableColumn[]; rows: any[]; style?: React.CSSProperties; }
export declare function Table(props: TableProps): JSX.Element;