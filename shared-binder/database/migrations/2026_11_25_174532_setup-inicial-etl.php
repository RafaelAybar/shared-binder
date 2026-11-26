<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;

return new class extends Migration
{
    public function up(): void
    {
        DB::connection()->getPdo()->exec(File::get(base_path('../python-scripts/esquema.sql')));
    }

    public function down(): void
    {
        // Vacío a propósito: el catálogo es del ETL, y migrate:reset no debe borrarlo.
    }
};
