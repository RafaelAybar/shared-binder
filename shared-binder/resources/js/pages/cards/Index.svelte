<script lang="ts">
    import { Link, router } from '@inertiajs/svelte';
    import AppHead from '@/components/AppHead.svelte';
    import { index as cardsIndex } from '@/routes/cards';

    type Card = {
        id: string;
        name: string;
        printed_name: string | null;
        lang: string;
        collector_number: string;
        rarity: string;
        mana_cost: string | null;
        type_line: string | null;
        image_small_url: string | null;
        mtg_set: { id: string; code: string; name: string };
    };

    type Paginated<T> = {
        data: T[];
        current_page: number;
        last_page: number;
        total: number;
        last_page_url: string;
        prev_page_url: string | null;
        next_page_url: string | null;
    };

    type Option = { value: string; label: string };

    type Filters = {
        lang: string;
        name: string;
        set: string;
        mana_value: number | null;
        types: string[];
        rarity: string | null;
    };

    let {
        cards,
        filters,
        languages,
        cardTypes,
        rarities,
        sets,
    }: {
        cards: Paginated<Card>;
        filters: Filters;
        languages: Option[];
        cardTypes: Option[];
        rarities: Option[];
        sets: { code: string; name: string }[];
    } = $props();

    // No es el <Form> de Inertia: con GET mete los campos en la URL antes de
    // llamar a transform, así que no puede quitar los vacíos.
    function filter(event: SubmitEvent & { currentTarget: HTMLFormElement }) {
        event.preventDefault();
        const query = new URLSearchParams();
        for (const [key, value] of new FormData(event.currentTarget)) {
            if (typeof value === 'string' && value !== '') {
                query.append(key, value);
            }
        }
        router.get(`${cardsIndex.url()}?${query}`);
    }

    function label(options: Option[], value: string): string {
        return options.find((option) => option.value === value)?.label ?? value;
    }
</script>

<AppHead title="Cards" />

<main class="mx-auto max-w-6xl p-6">
    <h1 class="mb-6 text-2xl font-semibold">
        Cards <span class="text-gray-500">({cards.total.toLocaleString()})</span>
    </h1>

    <form onsubmit={filter} class="mb-8 flex flex-wrap items-end gap-4 text-sm">
        <label class="flex flex-col gap-1">
            Name
            <input
                type="search"
                name="name"
                value={filters.name}
                class="rounded-md border px-2 py-1"
            />
        </label>
        <label class="flex flex-col gap-1">
            Set
            <input
                name="set"
                list="sets"
                value={filters.set}
                placeholder="Code or name"
                class="rounded-md border px-2 py-1"
            />
            <datalist id="sets">
                {#each sets as set (set.code)}
                    <option value={set.code}>{set.name}</option>
                {/each}
            </datalist>
        </label>
        <label class="flex flex-col gap-1">
            Mana value
            <input
                type="number"
                name="mana_value"
                min="0"
                step="1"
                value={filters.mana_value ?? ''}
                class="w-24 rounded-md border px-2 py-1"
            />
        </label>
        <label class="flex flex-col gap-1">
            Rarity
            <select name="rarity" class="rounded-md border px-2 py-1">
                <option value="">Any</option>
                {#each rarities as rarity (rarity.value)}
                    <option
                        value={rarity.value}
                        selected={rarity.value === filters.rarity}
                    >
                        {rarity.label}
                    </option>
                {/each}
            </select>
        </label>
        <label class="flex flex-col gap-1">
            Language
            <select name="lang" class="rounded-md border px-2 py-1">
                {#each languages as language (language.value)}
                    <option
                        value={language.value}
                        selected={language.value === filters.lang}
                    >
                        {language.label}
                    </option>
                {/each}
            </select>
        </label>
        <fieldset class="flex basis-full flex-wrap gap-x-4 gap-y-1">
            <legend class="mb-1">
                Type <span class="text-gray-500">(cards with every ticked type)</span>
            </legend>
            {#each cardTypes as type (type.value)}
                <label class="flex items-center gap-1">
                    <input
                        type="checkbox"
                        name="types[]"
                        value={type.value}
                        checked={filters.types.includes(type.value)}
                    />
                    {type.label}
                </label>
            {/each}
        </fieldset>
        <div class="flex items-center gap-4">
            <button
                type="submit"
                class="rounded-md bg-gray-900 px-3 py-1 text-white"
            >
                Filter
            </button>
            <Link href={cardsIndex.url()} class="underline">Clear</Link>
        </div>
    </form>

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
                {#if card.mana_cost}
                    <p class="text-gray-500">{card.mana_cost}</p>
                {/if}
                {#if card.type_line}
                    <p class="text-gray-500">{card.type_line}</p>
                {/if}
                <p class="text-gray-500">
                    {card.mtg_set.code.toUpperCase()} #{card.collector_number} · {label(languages, card.lang)} · {label(rarities, card.rarity)}
                </p>
            </li>
        {/each}
    </ul>

    {#if cards.total === 0}
        <p class="text-gray-500">No cards match these filters.</p>
    {:else if cards.data.length === 0}
        <p class="text-gray-500">
            This page is past the end of the results.
            <Link href={cards.last_page_url} class="underline">
                Go to the last page
            </Link>
        </p>
    {/if}

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
