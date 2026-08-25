import {defineConfig} from 'vite';
import path from 'node:path';
import motionCanvasModule from '@motion-canvas/vite-plugin';
import ffmpegModule from '@motion-canvas/ffmpeg';

const unwrapDefault = <T>(module: T): T => {
  const candidate = module as T & {default?: T};
  return candidate.default ?? module;
};

const motionCanvas = unwrapDefault(motionCanvasModule);
const ffmpeg = unwrapDefault(ffmpegModule);

export default defineConfig({
  root: process.env.MOTION_CANVAS_VITE_ROOT || process.cwd(),
  plugins: [motionCanvas(), ffmpeg()],
  build: {rollupOptions: {input: path.resolve(process.env.MOTION_CANVAS_VITE_ROOT || process.cwd(), 'index.html')}},
});
