export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>,'children'> {
  options: (string | { value: string; label: string })[];
  placeholder?: string; invalid?: boolean;
}
export declare function Select(props: SelectProps): JSX.Element;