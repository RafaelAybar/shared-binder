<?php

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

test('runs migrations against PostgreSQL', function () {
    expect(DB::connection()->getDriverName())->toBe('pgsql')
        ->and(Schema::hasTable('users'))->toBeTrue();
});
