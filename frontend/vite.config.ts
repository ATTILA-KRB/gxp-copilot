import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		// En dev, l'API FastAPI tourne sur :8001 (8000 est occupe par un
		// service d'entreprise sur certaines machines).
		proxy: {
			'/ask': 'http://127.0.0.1:8001',
			'/health': 'http://127.0.0.1:8001'
		}
	}
});
