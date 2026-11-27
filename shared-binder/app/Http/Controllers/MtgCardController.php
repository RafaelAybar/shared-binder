<?php

namespace App\Http\Controllers;

use App\Enums\MtgCardType;
use App\Enums\MtgLanguage;
use App\Enums\MtgRarity;
use App\Models\MtgCard;
use App\Models\MtgSet;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

class MtgCardController extends Controller
{
    public function index(Request $request): Response
    {
        $lang = MtgLanguage::tryFrom($this->text($request, 'lang')) ?? MtgLanguage::English;
        $name = $this->text($request, 'name');
        $set = $this->text($request, 'set');
        // Acepta «03», «3.0» y «1e1», que el campo numérico del navegador da por buenos, y ½.
        $manaValue = filter_var($this->text($request, 'mana_value'), FILTER_VALIDATE_FLOAT, [
            'options' => ['min_range' => 0],
            'flags' => FILTER_NULL_ON_FAILURE,
        ]);
        $types = array_values(array_filter(array_map(
            fn (mixed $type) => is_string($type) ? MtgCardType::tryFrom($type) : null,
            Arr::wrap($request->query('types')),
        )));
        $rarity = MtgRarity::tryFrom($this->text($request, 'rarity'));

        $cards = MtgCard::query()
            ->select(['id', 'set_id', 'name', 'printed_name', 'lang', 'collector_number', 'rarity', 'mana_cost', 'type_line', 'image_small_url'])
            ->with('mtgSet:id,code,name')
            ->where('lang', $lang->value)
            ->when($name !== '', function ($query) use ($name) {
                $pattern = '%'.$this->escapeLike($name).'%';
                $query->where(fn ($query) => $query->whereLike('name', $pattern)->orWhereLike('printed_name', $pattern));
            })
            ->when($set !== '', function ($query) use ($set) {
                // Por código o por el nombre entero, sin distinguir mayúsculas: fdn o Foundations.
                $query->whereHas('mtgSet', fn ($query) => $query->where('code', Str::lower($set))->orWhereLike('name', $this->escapeLike($set)));
            })
            ->when($manaValue !== null, fn ($query) => $query->where('cmc', $manaValue))
            ->when($types !== [], function ($query) use ($types) {
                // La carta tiene que tener todos los tipos marcados. \m y \M son límites de
                // palabra: Land no encuentra «Token Artifact — Lander».
                foreach ($types as $type) {
                    $query->where('type_line', '~', '\m'.$type->value.'\M');
                }
            })
            ->when($rarity, fn ($query, MtgRarity $rarity) => $query->where('rarity', $rarity->value))
            ->when(
                $set !== '',
                fn ($query) => $query->orderBy('collector_number'),
                // El nombre que muestra la página. Es la expresión del índice
                // mtg_cards_lang_display_name_id_idx: si no coincide, no se usa.
                fn ($query) => $query->orderByRaw('coalesce(printed_name, name)'),
            )
            ->orderBy('id')
            ->paginate(50)
            ->withQueryString();

        return Inertia::render('cards/Index', [
            'cards' => $cards,
            'filters' => [
                'lang' => $lang->value,
                'name' => $name,
                'set' => $set,
                'mana_value' => $manaValue,
                'types' => array_map(fn (MtgCardType $type) => $type->value, $types),
                'rarity' => $rarity?->value,
            ],
            'languages' => $this->options(MtgLanguage::cases()),
            'cardTypes' => $this->options(MtgCardType::cases()),
            'rarities' => $this->options(MtgRarity::cases()),
            'sets' => Inertia::once(fn () => MtgSet::query()->orderByDesc('released_at')->get(['code', 'name'])),
        ]);
    }

    /**
     * Un parámetro de la URL como texto: '' si falta o llega como lista (?name[]=x).
     */
    private function text(Request $request, string $key): string
    {
        $value = $request->query($key);

        return is_string($value) ? trim($value) : '';
    }

    /**
     * Sin escapar % y _, buscar «%» devolvería todas las cartas.
     */
    private function escapeLike(string $value): string
    {
        return addcslashes($value, '%_\\');
    }

    /**
     * @param  list<MtgLanguage>|list<MtgCardType>|list<MtgRarity>  $cases
     * @return list<array{value: string, label: string}>
     */
    private function options(array $cases): array
    {
        return array_map(fn ($case) => ['value' => $case->value, 'label' => $case->label()], $cases);
    }
}
