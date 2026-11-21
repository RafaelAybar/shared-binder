<?php

namespace App\Providers;

use Carbon\CarbonImmutable;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Date;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\ServiceProvider;
use Illuminate\Validation\Rules\Password;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        $this->restrictDatabaseConnectionsToPostgres();
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        $this->configureDefaults();
    }

    /**
     * Laravel merges its own default connections (sqlite, mysql, mariadb,
     * sqlsrv) into "database.connections". Keep only the ones declared in
     * config/database.php so PostgreSQL is the sole connection available.
     */
    protected function restrictDatabaseConnectionsToPostgres(): void
    {
        $connections = config('database.connections', []);

        config(['database.connections' => Arr::only($connections, ['pgsql'])]);
    }

    /**
     * Configure default behaviors for production-ready applications.
     */
    protected function configureDefaults(): void
    {
        Date::use(CarbonImmutable::class);

        DB::prohibitDestructiveCommands(
            app()->isProduction(),
        );

        Password::defaults(fn (): ?Password => app()->isProduction()
            ? Password::min(12)
                ->mixedCase()
                ->letters()
                ->numbers()
                ->symbols()
                ->uncompromised()
            : null,
        );
    }
}
