/**
 * @startingPoint section="Navigation" subtitle="CRM header bar with module nav" viewport="1440x80"
 */
export interface TopNavProps {
  items: { label: string; menu?: boolean }[];
  active?: string; onNavigate?: (label: string) => void; user?: string;
  /** Pass the real dubizzle cars logo here; defaults to the name in plain type */
  logo?: React.ReactNode;
}
export declare function TopNav(props: TopNavProps): JSX.Element;