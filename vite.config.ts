import { defineConfig } from 'vite';

export default defineConfig({
  // For GitHub Pages deployment, set base to repo name
  // Change 'depthmap-to-stl' to match your repo name
  base: process.env.NODE_ENV === 'production' ? '/depthmap-to-stl/' : '/',
  
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
