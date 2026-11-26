<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Table;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Carbon;

/**
 * Expansión de Magic copiada de Scryfall. Solo la escribe el ETL.
 *
 * @property string $id
 * @property Carbon $released_at
 * @property int $card_count
 * @property string $code
 * @property string $set_type
 * @property string|null $parent_set_code
 * @property string $name
 * @property string|null $icon_svg_uri
 * @property Carbon $created_at
 * @property Carbon $updated_at
 */
#[Table('mtg_sets', keyType: 'string', incrementing: false)]
class MtgSet extends Model
{
    /**
     * @return HasMany<MtgCard, $this>
     */
    public function cards(): HasMany
    {
        return $this->hasMany(MtgCard::class, 'set_id');
    }

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return ['released_at' => 'date'];
    }
}
