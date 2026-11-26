<?php

use App\Http\Controllers\MtgCardController;
use Illuminate\Support\Facades\Route;

Route::inertia('/', 'Welcome')->name('home');
Route::get('/cards', [MtgCardController::class, 'index'])->name('cards.index');
