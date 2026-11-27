<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Table;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Carbon;

/**
 * Impresión de una carta en un idioma, copiada de Scryfall. Solo la escribe el ETL.
 *
 * @property string $id
 * @property string|null $oracle_id
 * @property string $set_id
 * @property Carbon $released_at
 * @property string $collector_number
 * @property string $lang
 * @property string $rarity
 * @property string $layout
 * @property string $name
 * @property string|null $printed_name
 * @property string|null $mana_cost
 * @property string|null $cmc
 * @property string|null $type_line
 * @property string|null $image_small_url
 * @property string|null $image_small_back_url
 * @property Carbon $created_at
 * @property Carbon $updated_at
 */
#[Table('mtg_cards', keyType: 'string', incrementing: false)]
class MtgCard extends Model
{
    /**
     * @return BelongsTo<MtgSet, $this>
     */
    public function mtgSet(): BelongsTo
    {
        return $this->belongsTo(MtgSet::class, 'set_id');
    }

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return ['released_at' => 'date'];
    }
}
