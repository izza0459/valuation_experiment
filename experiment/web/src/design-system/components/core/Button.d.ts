/**
 * @startingPoint section="Core" subtitle="CRM action buttons: Proceed, Cancel, Add Task, Lost, Create Flow" viewport="700x220"
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary = solid red (Proceed); soft = pink fill (Add Task, Call); outline = white (Cancel); success = green tint (Create Flow); danger = pink (Lost); ghost = text */
  variant?: 'primary' | 'soft' | 'outline' | 'success' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
  block?: boolean;
  disabled?: boolean;
  children?: React.ReactNode;
}
export declare function Button(props: ButtonProps): JSX.Element;