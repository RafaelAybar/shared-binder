<?php

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use Inertia\Testing\AssertableInertia as Assert;

const MTG_CARD_INDEX_DEFAULT_FILTERS = ['lang' => 'en', 'name' => '', 'set' => '', 'mana_value' => null, 'types' => [], 'rarity' => null];

beforeEach(function () {
    $lea = '00000000-0000-4000-a000-000000000001';
    $fdn = '00000000-0000-4000-a000-000000000002';

    DB::table('mtg_sets')->insert([
        ['id' => $lea, 'code' => 'lea', 'name' => 'Limited Edition Alpha', 'set_type' => 'core', 'released_at' => '1993-08-05', 'card_count' => 295],
        ['id' => $fdn, 'code' => 'fdn', 'name' => 'Foundations', 'set_type' => 'core', 'released_at' => '2024-11-15', 'card_count' => 730],
    ]);

    $card = fn (string $set, string $number, string $name, string $type, string $rarity, int $cmc) => [
        'id' => (string) Str::uuid(),
        'set_id' => $set,
        'released_at' => '2024-11-15',
        'collector_number' => $number,
        'lang' => 'en',
        'name' => $name,
        'printed_name' => null,
        'rarity' => $rarity,
        'layout' => 'normal',
        'finishes' => '{nonfoil}',
        'type_line' => $type,
        'cmc' => $cmc,
    ];
    $inSpanish = fn (array $card, string $printedName) => [...$card, 'id' => (string) Str::uuid(), 'lang' => 'es', 'printed_name' => $printedName];

    $bolt = $card(set: $lea, number: '161', name: 'Lightning Bolt', type: 'Instant', rarity: 'common', cmc: 1);
    $elves = $card(set: $fdn, number: '227', name: 'Llanowar Elves', type: 'Creature — Elf Druid', rarity: 'common', cmc: 1);

    DB::table('mtg_cards')->insert([
        $card(set: $lea, number: '232', name: 'Black Lotus', type: 'Artifact', rarity: 'rare', cmc: 0),
        $bolt,
        $inSpanish($bolt, 'Relámpago'),
        $card(set: $lea, number: '255', name: 'Juggernaut', type: 'Artifact Creature — Juggernaut', rarity: 'uncommon', cmc: 4),
        $elves,
        $inSpanish($elves, 'Elfos de Llanowar'),
        $card(set: $fdn, number: '278', name: 'Forest', type: 'Basic Land — Forest', rarity: 'common', cmc: 0),
    ]);
});

test('lists the English cards by name by default', function () {
    $this->get(route('cards.index'))
        ->assertOk()
        ->assertInertia(fn (Assert $page) => $page
            ->component('cards/Index')
            ->where('filters', MTG_CARD_INDEX_DEFAULT_FILTERS)
            ->where('cards.total', 5)
            ->where('cards.data.0.name', 'Black Lotus')
            ->where('cards.data.0.mtg_set.code', 'lea')
            ->has('languages', 16)
            ->has('cardTypes', 10)
            ->has('rarities', 5)
            ->where('sets', [['code' => 'fdn', 'name' => 'Foundations'], ['code' => 'lea', 'name' => 'Limited Edition Alpha']]));
});

test('filters the cards', function (array $query, array $expected) {
    $cards = $this->get(route('cards.index', $query))->assertOk()->inertiaProps('cards.data');

    expect(array_column($cards, 'name'))->toBe($expected);
})->with([
    'nothing' => [[], ['Black Lotus', 'Forest', 'Juggernaut', 'Lightning Bolt', 'Llanowar Elves']],
    'name' => [['name' => 'bolt'], ['Lightning Bolt']],
    'a % in the name is not a wildcard' => [['name' => '%'], []],
    'printed name' => [['lang' => 'es', 'name' => 'relámpago'], ['Lightning Bolt']],
    'other languages, by printed name' => [['lang' => 'es'], ['Llanowar Elves', 'Lightning Bolt']],
    'set code, in collector order' => [['set' => 'fdn'], ['Llanowar Elves', 'Forest']],
    'set name in any case' => [['set' => 'FOUNDATIONS'], ['Llanowar Elves', 'Forest']],
    'part of a set name' => [['set' => 'Found'], []],
    'mana value 0' => [['mana_value' => '0'], ['Black Lotus', 'Forest']],
    'mana value with a leading zero' => [['mana_value' => '04'], ['Juggernaut']],
    'type' => [['types' => ['Land']], ['Forest']],
    'a type also finds cards with more types' => [['types' => ['Artifact']], ['Black Lotus', 'Juggernaut']],
    'every ticked type' => [['types' => ['Artifact', 'Creature']], ['Juggernaut']],
    'rarity' => [['rarity' => 'rare'], ['Black Lotus']],
    'all filters' => [['name' => 'bolt', 'set' => 'lea', 'mana_value' => '1', 'types' => ['Instant'], 'rarity' => 'common'], ['Lightning Bolt']],
]);

test('ignores values that are not valid', function (array $query) {
    $this->get(route('cards.index', $query))
        ->assertOk()
        ->assertInertia(fn (Assert $page) => $page
            ->where('filters', MTG_CARD_INDEX_DEFAULT_FILTERS)
            ->where('cards.total', 5));
})->with([
    'unknown language' => [['lang' => 'xx']],
    'unknown rarity' => [['rarity' => 'xx']],
    'unknown type' => [['types' => ['xx']]],
    'mana value that is not a number' => [['mana_value' => 'abc']],
    'negative mana value' => [['mana_value' => '-1']],
    'language as a list' => [['lang' => ['es']]],
    'name as a list' => [['name' => ['bolt']]],
    'set as a list' => [['set' => ['fdn']]],
    'mana value as a list' => [['mana_value' => ['0']]],
    'rarity as a list' => [['rarity' => ['rare']]],
    'type as a list' => [['types' => [['Land']]]],
]);

test('sends back the filters it applied', function () {
    $query = ['lang' => 'es', 'set' => ' FOUNDATIONS ', 'mana_value' => '01', 'types' => ['Creature', 'xx']];

    $this->get(route('cards.index', $query))
        ->assertInertia(fn (Assert $page) => $page
            ->where('filters', ['lang' => 'es', 'name' => '', 'set' => 'FOUNDATIONS', 'mana_value' => 1, 'types' => ['Creature'], 'rarity' => null])
            ->where('cards.data.0.printed_name', 'Elfos de Llanowar'));
});

test('keeps the filters in the pagination links', function () {
    $this->get(route('cards.index', ['set' => 'fdn']))
        ->assertInertia(fn (Assert $page) => $page
            ->where('cards.first_page_url', fn (string $url) => str_contains($url, 'set=fdn')));
});
