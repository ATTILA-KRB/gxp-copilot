/**
 * Client SSE pour POST /ask.
 *
 * EventSource ne supporte pas POST : on lit le flux fetch et on parse les
 * blocs SSE (`event: ...` / `data: ...`) separes par une ligne vide.
 */

export interface Citation {
	chunk_id: number;
	titre: string;
	agence: string;
	numero_page: number | null;
	section: string | null;
	url_source: string;
}

export interface Done {
	interaction_id: number;
	score_confiance: number;
	latence_ms: number;
}

export interface AskCallbacks {
	onSources: (citations: Citation[]) => void;
	onToken: (token: string) => void;
	onDone: (done: Done) => void;
	onError: (message: string) => void;
}

// Garde-fou client : au-dela, on abandonne au lieu de rester sur le spinner.
const TIMEOUT_MS = 120_000;

export async function askStream(question: string, callbacks: AskCallbacks): Promise<void> {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

	let response: Response;
	try {
		response = await fetch('/ask', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ question }),
			signal: controller.signal
		});
	} catch (cause) {
		clearTimeout(timer);
		callbacks.onError(
			cause instanceof DOMException && cause.name === 'AbortError'
				? `Aucune réponse après ${TIMEOUT_MS / 1000} s — API lancée ? Proxy correct ?`
				: "API injoignable — lancer l'API (start-api.cmd) puis réessayer."
		);
		return;
	}
	if (!response.ok || !response.body) {
		clearTimeout(timer);
		callbacks.onError(`Erreur API (${response.status}).`);
		return;
	}

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	const dispatch = (block: string) => {
		let event = 'message';
		const dataLines: string[] = [];
		for (const line of block.split('\n')) {
			if (line.startsWith('event: ')) event = line.slice(7).trim();
			else if (line.startsWith('data: ')) dataLines.push(line.slice(6));
		}
		const data = dataLines.join('\n');
		if (event === 'sources') callbacks.onSources(JSON.parse(data) as Citation[]);
		else if (event === 'token') callbacks.onToken(JSON.parse(data) as string);
		else if (event === 'done') callbacks.onDone(JSON.parse(data) as Done);
	};

	try {
		for (;;) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			let sep: number;
			while ((sep = buffer.indexOf('\n\n')) !== -1) {
				const block = buffer.slice(0, sep);
				buffer = buffer.slice(sep + 2);
				if (block.trim()) dispatch(block);
			}
		}
	} catch {
		callbacks.onError('Flux interrompu.');
	} finally {
		clearTimeout(timer);
	}
}
