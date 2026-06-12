import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// SPA statique : l'API FastAPI vit a part (proxy en dev, meme origine en prod).
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
