import {makeScene2D, Rect} from '@motion-canvas/2d';
import {all, createRef, easeOutCubic, waitFor} from '@motion-canvas/core';
import {buildComponent} from '../components';
import {assertMotionJob} from '../types';

const response = await fetch('/motion_input.json', {cache: 'no-store'});
if (!response.ok) throw new Error(`motion_input.json request failed: ${response.status}`);
const job = assertMotionJob(await response.json());

export default makeScene2D(function* (view) {
  view.fill('#00000000');
  const stage = createRef<Rect>();
  view.add(<Rect ref={stage} width={1080} height={1920} justifyContent={'center'} alignItems={'center'} opacity={0} scale={0.92}>{buildComponent(job)}</Rect>);
  yield* all(stage().opacity(1, 0.35, easeOutCubic), stage().scale(1, 0.45, easeOutCubic));
  yield* waitFor(Math.max(0.2, job.duration - 0.7));
  yield* stage().opacity(0, 0.25);
});
