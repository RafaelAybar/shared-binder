<?php

namespace App\Http\Controllers;

use App\Enums\MtgCardType;
use App\Enums\MtgLanguage;
use App\Enums\MtgRarity;
use App\Models\MtgCard;
use App\Models\MtgSet;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

class MtgCardController extends Controller
{
    public function index(Request $request): Response
    {
        $lang = $request->enum('lang', MtgLanguage::class, MtgLanguage::English);
        $name = $request->string('name')->trim()->toString();
        $set = $request->string('set')->trim()->lower()->toString();
        // No $request->integer(): convierte «abc» en 0, que es un valor de maná válido.
        $manaValue = filter_var($request->input('mana_value'), FILTER_VALIDATE_INT, [
            'options' => ['min_range' => 0],
            'flags' => FILTER_NULL_ON_FAILURE,
        ]);
        // enums() conserva las claves de los valores válidos, y [1 => Land] llegaría a
        // JavaScript como un objeto en vez de una lista.
        $types = array_values($request->enums('types', MtgCardType::class));
        $rarity = $request->enum('rarity', MtgRarity::class);

        $cards = MtgCard::query()
            ->select(['id', 'set_id', 'name', 'printed_name', 'lang', 'collector_number', 'rarity', 'mana_cost', 'type_line', 'image_small_url'])
            ->with('mtgSet:id,code,name')
            ->where('lang', $lang->value)
            ->when($name !== '', function ($query) use ($name) {
                // Sin escapar % y _, buscar «%» devolvería todas las cartas.
                $pattern = '%'.addcslashes($name, '%_\\').'%';
                $query->where(fn ($query) => $query->whereLike('name', $pattern)->orWhereLike('printed_name', $pattern));
            })
            ->when($set !== '', fn ($query) => $query->whereRelation('mtgSet', 'code', $set))
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
                fn ($query) => $query->orderBy('name'),
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
     * @param  list<MtgLanguage>|list<MtgCardType>|list<MtgRarity>  $cases
     * @return list<array{value: string, label: string}>
     */
    private function options(array $cases): array
    {
        return array_map(fn ($case) => ['value' => $case->value, 'label' => $case->label()], $cases);
    }
}
