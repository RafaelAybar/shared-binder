<?php

namespace App\Http\Controllers;

use App\Models\MtgCard;
use Inertia\Inertia;
use Inertia\Response;

class MtgCardController extends Controller
{
    public function index(): Response
    {
        $cards = MtgCard::query()
            ->select(['id', 'set_id', 'name', 'printed_name', 'lang', 'collector_number', 'rarity', 'image_small_url'])
            ->with('mtgSet:id,code,name')
            ->orderBy('name')
            ->orderBy('id')
            ->paginate(50);

        return Inertia::render('cards/Index', [
            'cards' => $cards,
        ]);
    }
}
