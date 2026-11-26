<script lang="ts">
    import { Link } from '@inertiajs/svelte';
    import AppHead from '@/components/AppHead.svelte';

    type Card = {
        id: string;
        name: string;
        printed_name: string | null;
        lang: string;
        collector_number: string;
        rarity: string;
        image_small_url: string | null;
        mtg_set: { id: string; code: string; name: string };
    };

    type Paginated<T> = {
        data: T[];
        current_page: number;
        last_page: number;
        total: number;
        prev_page_url: string | null;
        next_page_url: string | null;
    };

    let { cards }: { cards: Paginated<Card> } = $props();
</script>

<AppHead title="Cards" />

<main class="mx-auto max-w-6xl p-6">
    <h1 class="mb-6 text-2xl font-semibold">
        Cards <span class="text-gray-500">({cards.total.toLocaleString()})</span>
    </h1>

    <ul class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {#each cards.data as card (card.id)}
            <li class="text-sm">
                {#if card.image_small_url}
                    <img
                        src={card.image_small_url}
                        alt={card.printed_name ?? card.name}
                        loading="lazy"
                        class="aspect-[146/204] w-full rounded-md"
                    />
                {/if}
                <p class="mt-1 font-medium">{card.printed_name ?? card.name}</p>
                <p class="text-gray-500">
                    {card.mtg_set.code.toUpperCase()} #{card.collector_number} · {card.lang} · {card.rarity}
                </p>
            </li>
        {/each}
    </ul>

    <nav class="mt-8 flex items-center justify-between">
        {#if cards.prev_page_url}
            <Link href={cards.prev_page_url} class="underline">← Previous</Link>
        {:else}
            <span></span>
        {/if}
        <span>Page {cards.current_page.toLocaleString()} of {cards.last_page.toLocaleString()}</span>
        {#if cards.next_page_url}
            <Link href={cards.next_page_url} class="underline">Next →</Link>
        {:else}
            <span></span>
        {/if}
    </nav>
</main>
