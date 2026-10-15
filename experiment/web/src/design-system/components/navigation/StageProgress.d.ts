/**
 * @startingPoint section="Navigation" subtitle="Flow stage progress bar with Current Stage counter" viewport="1200x90"
 */
export interface StageProgressProps {
  steps: { label: string; state?: 'done' | 'current' | 'todo'; width?: number }[];
  /** label of the current step */
  current: string;
  onStepClick?: (step: { label: string }, index: number) => void;
}
export declare function StageProgress(props: StageProgressProps): JSX.Element;