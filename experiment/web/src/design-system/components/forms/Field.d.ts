/**
 * @startingPoint section="Forms" subtitle="Stage form fields: label, input, select, upload, error" viewport="700x420"
 */
export interface FieldProps {
  label: string; optional?: boolean; required?: boolean;
  /** true shows "This field is required"; a string shows that message */
  error?: boolean | string;
  /** grey line under the control, e.g. "Five thousand" */
  helper?: string;
  /** stacked = label above (stage forms); inline = right-aligned label left (create-flow form) */
  layout?: 'stacked' | 'inline';
  children?: React.ReactNode; style?: React.CSSProperties;
}
export declare function Field(props: FieldProps): JSX.Element;