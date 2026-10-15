export interface OptionGroupProps { options: string[]; value?: string; onChange?: (v: string) => void; disabled?: boolean; }
export declare function OptionGroup(props: OptionGroupProps): JSX.Element;