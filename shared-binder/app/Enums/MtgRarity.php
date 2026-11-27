<?php

namespace App\Enums;

/**
 * Sin bonus: Scryfall la define, pero ninguna carta del catálogo la tiene.
 */
enum MtgRarity: string
{
    case Common = 'common';
    case Uncommon = 'uncommon';
    case Rare = 'rare';
    case Mythic = 'mythic';
    case Special = 'special';

    public function label(): string
    {
        return match ($this) {
            self::Mythic => 'Mythic rare',
            default => ucfirst($this->value),
        };
    }
}
