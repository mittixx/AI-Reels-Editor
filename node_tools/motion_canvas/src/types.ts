export interface MotionJob {
  schema_version: string;
  component: string;
  duration: number;
  preset: string;
  data: Record<string, unknown>;
}

export const MOTION_COMPONENTS = new Set([
  'AnimatedStat', 'AnimatedCounter', 'Comparison', 'ProcessFlow', 'Timeline', 'Quote',
  'CodeHighlight', 'FeatureList', 'ProductFeature', 'BeforeAfter', 'Callout', 'Chart', 'Diagram',
]);

export function assertMotionJob(value: unknown): MotionJob {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('motion_input.json must be an object');
  }
  const job = value as Partial<MotionJob>;
  if (job.schema_version !== '1.3') throw new Error('motion_input.json has unsupported schema_version');
  if (typeof job.component !== 'string' || !MOTION_COMPONENTS.has(job.component)) {
    throw new Error('motion_input.json has unsupported component');
  }
  if (!Number.isFinite(job.duration) || (job.duration ?? 0) <= 0) {
    throw new Error('motion_input.json has invalid duration');
  }
  if (typeof job.preset !== 'string' || !job.preset.trim()) throw new Error('motion_input.json has invalid preset');
  if (!job.data || typeof job.data !== 'object' || Array.isArray(job.data)) {
    throw new Error('motion_input.json has invalid data');
  }
  return job as MotionJob;
}
