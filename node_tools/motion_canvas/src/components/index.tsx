import {Layout, Line, Node, Rect, Txt} from '@motion-canvas/2d';
import type {MotionJob} from '../types';

const palette = {bg: '#0B0B0D', card: '#202026', text: '#FFFFFF', accent: '#B8FF5A'};

function title(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function value(value: unknown, fallback = '100'): string {
  return typeof value === 'number' || typeof value === 'string' ? String(value) : fallback;
}

function card(heading: string, body: string, accent = palette.accent): Node {
  return <Rect width={920} minHeight={480} radius={48} fill={palette.card} padding={70} layout direction={'column'} gap={34}>
    <Txt text={heading} fill={accent} fontFamily={'Arial'} fontWeight={900} fontSize={54}/>
    <Txt text={body} fill={palette.text} fontFamily={'Arial'} fontWeight={800} fontSize={108}/>
  </Rect>;
}

export function AnimatedStat(data: Record<string, unknown>): Node { return card(title(data.title, 'STAT'), value(data.value)); }
export function AnimatedCounter(data: Record<string, unknown>): Node { return card(title(data.title, 'COUNT'), value(data.value, '1 000')); }
export function Quote(data: Record<string, unknown>): Node { return card('“', title(data.quote, 'Сильная цитата'), '#F4B7C9'); }
export function Callout(data: Record<string, unknown>): Node { return card(title(data.label, 'ВАЖНО'), title(data.text, 'Главная мысль'), '#FFCB45'); }
export function ProductFeature(data: Record<string, unknown>): Node { return card(title(data.product, 'PRODUCT'), title(data.feature, 'Ключевая функция')); }
export function BeforeAfter(data: Record<string, unknown>): Node {
  return <Layout layout direction={'row'} gap={28}>{card('ДО', title(data.before, 'До'))}{card('ПОСЛЕ', title(data.after, 'После'), '#FFCB45')}</Layout>;
}
export function Comparison(data: Record<string, unknown>): Node {
  return <Layout layout direction={'row'} gap={28}>{card('A', title(data.left, 'Вариант A'))}{card('B', title(data.right, 'Вариант B'), '#FFCB45')}</Layout>;
}
export function FeatureList(data: Record<string, unknown>): Node {
  const items = Array.isArray(data.items) ? data.items.map(String) : ['Пункт 1', 'Пункт 2', 'Пункт 3'];
  return <Rect width={940} radius={48} fill={palette.card} padding={60} layout direction={'column'} gap={24}>
    {items.map((item, index) => <Txt key={String(index)} text={`✓ ${item}`} fill={palette.text} fontFamily={'Arial'} fontWeight={700} fontSize={50}/>)}
  </Rect>;
}
export function ProcessFlow(data: Record<string, unknown>): Node {
  const steps = Array.isArray(data.steps) ? data.steps.map(String) : ['Шаг 1', 'Шаг 2', 'Результат'];
  return <Layout layout direction={'column'} gap={28}>{steps.map((step, index) => <Rect key={String(index)} width={860} height={150} radius={34} fill={index === steps.length - 1 ? palette.accent : palette.card}><Txt text={step} fill={index === steps.length - 1 ? palette.bg : palette.text} fontFamily={'Arial'} fontWeight={800} fontSize={48}/></Rect>)}</Layout>;
}
export function Timeline(data: Record<string, unknown>): Node { return ProcessFlow({steps: data.events}); }
export function CodeHighlight(data: Record<string, unknown>): Node { return card(title(data.language, 'CODE'), title(data.code, 'print("Hello")'), '#73D2FF'); }
export function Chart(data: Record<string, unknown>): Node {
  const values = Array.isArray(data.values) ? data.values.map(Number) : [30, 58, 86];
  return <Layout layout direction={'row'} alignItems={'end'} gap={40}>{values.map((item, index) => <Rect key={String(index)} width={180} height={Math.max(80, item * 8)} radius={28} fill={index === values.length - 1 ? palette.accent : '#4C4C58'}><Txt text={String(item)} fill={palette.text} fontFamily={'Arial'} fontWeight={800} fontSize={42}/></Rect>)}</Layout>;
}
export function Diagram(data: Record<string, unknown>): Node {
  return <Layout layout direction={'column'} alignItems={'center'} gap={28}>{card(title(data.title, 'ИДЕЯ'), title(data.center, 'Центр'))}<Line points={[[0, 0], [0, 140]]} stroke={palette.accent} lineWidth={14}/>{FeatureList(data)}</Layout>;
}

export function buildComponent(job: MotionJob): Node {
  const components: Record<string, (data: Record<string, unknown>) => Node> = {
    AnimatedStat, AnimatedCounter, Comparison, ProcessFlow, Timeline, Quote, CodeHighlight,
    FeatureList, ProductFeature, BeforeAfter, Callout, Chart, Diagram,
  };
  const component = components[job.component];
  if (!component) throw new Error(`Unsupported Motion Canvas component: ${job.component}`);
  return component(job.data);
}
