export interface CardProps {
  /** plain = white panel on grey page; bordered = inner card (Service, Payment Info); active = pink outline for the open stage form */
  variant?: 'plain' | 'bordered' | 'active';
  padding?: number | string; children?: React.ReactNode; style?: React.CSSProperties;
}
export declare function Card(props: CardProps): JSX.Element;