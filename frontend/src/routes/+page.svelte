<script lang="ts">
	import { tick } from 'svelte';
	import { askStream, type Citation, type Done } from '$lib/api';

	const REFUSAL = 'Information non trouvée dans le corpus.';
	const AGENCY_COLORS: Record<string, string> = {
		EU: 'bg-sky/15 text-sky',
		EMA: 'bg-sky/15 text-sky',
		MHRA: 'bg-clay/15 text-clay',
		FDA: 'bg-moss/15 text-moss',
		PICS: 'bg-clay/15 text-clay',
		WHO: 'bg-moss/15 text-moss',
		ANSM: 'bg-sky/15 text-sky',
		ICH: 'bg-clay/15 text-clay'
	};

	interface Exchange {
		question: string;
		answer: string;
		sources: Citation[];
		done: Done | null;
		error: string | null;
		streaming: boolean;
	}

	let question = $state('');
	let exchanges = $state<Exchange[]>([]);
	let busy = $state(false);
	let feed: HTMLElement | undefined = $state();

	const isRefusal = (e: Exchange) => e.answer.trim() === REFUSAL;

	async function scrollToEnd() {
		await tick();
		feed?.scrollTo({ top: feed.scrollHeight, behavior: 'smooth' });
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		const q = question.trim();
		if (q.length < 3 || busy) return;

		question = '';
		busy = true;
		exchanges.push({
			question: q,
			answer: '',
			sources: [],
			done: null,
			error: null,
			streaming: true
		});
		// IMPORTANT : recuperer le PROXY reactif depuis le tableau $state —
		// muter l'objet brut d'origine ne declencherait aucun re-rendu.
		const exchange = exchanges[exchanges.length - 1];
		scrollToEnd();

		await askStream(q, {
			onSources: (citations) => {
				exchange.sources = citations;
				scrollToEnd();
			},
			onToken: (token) => {
				exchange.answer += token;
				scrollToEnd();
			},
			onDone: (done) => {
				exchange.done = done;
			},
			onError: (message) => {
				exchange.error = message;
			}
		});
		exchange.streaming = false;
		busy = false;
		scrollToEnd();
	}
</script>

<div class="flex h-dvh flex-col">
	<!-- En-tete -->
	<header class="border-b border-cloud bg-ivory/90 backdrop-blur">
		<div class="mx-auto flex max-w-3xl items-baseline gap-3 px-4 py-4">
			<h1 class="font-serif text-2xl text-ink">GxP Copilot</h1>
			<span class="text-sm text-stone">intégrité des données · corpus public</span>
		</div>
	</header>

	<!-- Fil de conversation -->
	<main bind:this={feed} class="flex-1 overflow-y-auto">
		<div class="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8">
			{#if exchanges.length === 0}
				<div class="mt-16 text-center">
					<p class="font-serif text-3xl text-ink">Posez une question réglementaire.</p>
					<p class="mx-auto mt-4 max-w-md text-sm leading-relaxed text-stone">
						« Que dit l'annexe 11 sur les contrôles d'accès ? » ·
						« Quels sont les principes ALCOA+ ? » — chaque réponse est ancrée sur le
						corpus MHRA, FDA, PIC/S, WHO et EU GMP, avec citation des sources.
					</p>
				</div>
			{/if}

			{#each exchanges as exchange}
				<article class="flex flex-col gap-4">
					<!-- Question -->
					<div class="self-end rounded-2xl rounded-br-sm bg-ink px-4 py-3 text-ivory">
						{exchange.question}
					</div>

					<!-- Sources -->
					{#if exchange.sources.length > 0}
						<div class="flex flex-wrap gap-2">
							{#each exchange.sources as source, i}
								<a
									href={source.url_source}
									target="_blank"
									rel="noreferrer"
									class="group flex items-center gap-2 rounded-lg border border-cloud bg-white/60 px-3 py-1.5 text-xs transition hover:border-clay"
									title={source.titre}
								>
									<span class="font-semibold text-stone group-hover:text-clay">[{i + 1}]</span>
									<span
										class="rounded px-1.5 py-0.5 font-medium {AGENCY_COLORS[source.agence] ??
											'bg-cloud text-ink'}">{source.agence}</span
									>
									<span class="max-w-44 truncate text-ink">{source.titre}</span>
									{#if source.numero_page}
										<span class="text-stone">p. {source.numero_page}</span>
									{/if}
									{#if source.section}
										<span class="text-stone">§ {source.section}</span>
									{/if}
								</a>
							{/each}
						</div>
					{/if}

					<!-- Reponse -->
					<div
						class="rounded-2xl rounded-bl-sm border px-4 py-3 leading-relaxed whitespace-pre-wrap
						{exchange.error
							? 'border-clay/40 bg-clay/5 text-clay'
							: isRefusal(exchange)
								? 'border-stone/40 bg-cloud/40 text-ink italic'
								: 'border-cloud bg-white/70 text-ink'}"
					>
						{#if exchange.error}
							{exchange.error}
						{:else if exchange.answer}
							{exchange.answer}{#if exchange.streaming}<span
									class="ml-0.5 inline-block h-4 w-2 animate-pulse rounded-sm bg-clay align-text-bottom"
								></span>{/if}
						{:else if exchange.streaming}
							<span class="text-stone">Recherche dans les sources…</span>
						{/if}
					</div>

					<!-- Pied d'audit -->
					{#if exchange.done}
						<div class="flex gap-4 text-xs text-stone">
							<span>interaction #{exchange.done.interaction_id}</span>
							<span>confiance {exchange.done.score_confiance.toFixed(2)}</span>
							<span>{(exchange.done.latence_ms / 1000).toFixed(1)} s</span>
						</div>
					{/if}
				</article>
			{/each}
		</div>
	</main>

	<!-- Saisie -->
	<footer class="border-t border-cloud bg-ivory">
		<form onsubmit={submit} class="mx-auto flex max-w-3xl gap-2 px-4 py-4">
			<input
				bind:value={question}
				placeholder="Votre question (FR ou EN)…"
				maxlength="2000"
				class="flex-1 rounded-xl border border-cloud bg-white px-4 py-3 text-ink placeholder:text-stone focus:border-clay focus:ring-2 focus:ring-clay/30 focus:outline-none"
			/>
			<button
				type="submit"
				disabled={busy || question.trim().length < 3}
				class="rounded-xl bg-clay px-5 py-3 font-medium text-ivory transition enabled:hover:bg-clay/90 disabled:opacity-40"
			>
				{busy ? '…' : 'Demander'}
			</button>
		</form>
		<p class="mx-auto max-w-3xl px-4 pb-3 text-center text-xs text-stone">
			Démonstration technique — corpus 100&nbsp;% public. Aucun conseil réglementaire ;
			se référer aux textes officiels.
		</p>
	</footer>
</div>
