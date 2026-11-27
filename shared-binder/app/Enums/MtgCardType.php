<?php

namespace App\Enums;

/**
 * Cada valor se busca tal cual, con mayúscula, en mtg_cards.type_line.
 */
enum MtgCardType: string
{
    case Artifact = 'Artifact';
    case Battle = 'Battle';
    case Creature = 'Creature';
    case Enchantment = 'Enchantment';
    case Instant = 'Instant';
    case Kindred = 'Kindred';
    case Land = 'Land';
    case Planeswalker = 'Planeswalker';
    case Sorcery = 'Sorcery';
    case Token = 'Token';

    public function label(): string
    {
        return $this->value;
    }
}
