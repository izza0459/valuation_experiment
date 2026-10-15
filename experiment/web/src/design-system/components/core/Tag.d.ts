export interface TagProps {
  /** purple = category/lead status; blue = In Progress; green = Completed/Verified; amber = pending; red = rejected/missing; neutral = default */
  tone?: 'purple' | 'blue' | 'green' | 'amber' | 'red' | 'neutral';
  children?: React.ReactNode; style?: React.CSSProperties;
}
export declare function Tag(props: TagProps): JSX.Element;