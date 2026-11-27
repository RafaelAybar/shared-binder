<?php

namespace App\Enums;

/**
 * Los idiomas ficticios (klingon, enano, pirexiano y quenya) están en mtg_cards, pero no se
 * ofrecen. Los casos van en el orden del desplegable: inglés y después por número de cartas.
 */
enum MtgLanguage: string
{
    case English = 'en';
    case Japanese = 'ja';
    case French = 'fr';
    case German = 'de';
    case Spanish = 'es';
    case Italian = 'it';
    case SimplifiedChinese = 'zhs';
    case Portuguese = 'pt';
    case TraditionalChinese = 'zht';
    case Russian = 'ru';
    case Korean = 'ko';
    case AncientGreek = 'grc';
    case Hebrew = 'he';
    case Arabic = 'ar';
    case Latin = 'la';
    case Sanskrit = 'sa';

    public function label(): string
    {
        return match ($this) {
            self::English => 'English',
            self::Japanese => '日本語',
            self::French => 'Français',
            self::German => 'Deutsch',
            self::Spanish => 'Español',
            self::Italian => 'Italiano',
            self::SimplifiedChinese => '简体中文',
            self::Portuguese => 'Português',
            self::TraditionalChinese => '繁體中文',
            self::Russian => 'Русский',
            self::Korean => '한국어',
            self::AncientGreek => 'Ἀρχαία Ἑλληνικά',
            self::Hebrew => 'עברית',
            self::Arabic => 'العربية',
            self::Latin => 'Latina',
            self::Sanskrit => 'संस्कृतम्',
        };
    }
}
