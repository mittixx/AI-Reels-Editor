import {defineConfig} from 'vite';
import path from 'node:path';
import motionCanvas from '@motion-canvas/vite-plugin';
import ffmpeg from '@motion-canvas/ffmpeg';

export default defineConfig({
  root: process.env.MOTION_CANVAS_VITE_ROOT || process.cwd(),
  plugins: [motionCanvas(), ffmpeg()],
  build: {rollupOptions: {input: path.resolve(process.env.MOTION_CANVAS_VITE_ROOT || process.cwd(), 'index.html')}},
});
