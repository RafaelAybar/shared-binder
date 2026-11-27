# Análisis de calidad con SonarQube Cloud

SonarQube Cloud busca bugs, vulnerabilidades, *code smells*, código duplicado y secretos
(contraseñas, tokens...) en el código del proyecto.

## Qué se analiza

| Fichero | Reglas |
| --- | --- |
| `shared-binder/`: la aplicación Laravel | PHP |
| `shared-binder/resources/js/`, `vite.config.ts` y `svelte.config.js` | TypeScript y JavaScript |
| `shared-binder/resources/css/` | CSS |
| Componentes `.svelte` | Solo HTML: SonarQube no admite Svelte, y el TypeScript de `<script>` no se analiza |
| `python-scripts/`: el ETL | Python |
| `backend.Dockerfile` | Docker |
| `docker-compose.yaml` | Solo secretos: SonarQube no tiene reglas para Docker Compose |

Los tests (`shared-binder/tests/` y `python-scripts/tests/`) se analizan como tests, con
reglas propias.

## Cuándo se ejecuta

El workflow `.github/workflows/sonarqube.yml` lo lanza en cada push a `main` y en cada pull
request que cambie alguno de esos ficheros o la configuración, que está en
`sonar-project.properties`.

## Qué no se analiza

- El SQL, como `python-scripts/esquema.sql`.
- El TypeScript dentro de los componentes Svelte. Para que se analice, tiene que estar en
  un fichero `.ts` aparte.
- La cobertura de tests: el análisis no ejecuta los tests.
- El código de terceros y el generado: `vendor/`, `node_modules/`, `storage/`,
  `bootstrap/cache/`, `bootstrap/ssr/`, `public/build/` y las rutas de Wayfinder
  (`resources/js/actions/`, `routes/` y `wayfinder/`).
- Las plantillas Blade, que son HTML con directivas y no PHP.

## Puesta en marcha

Se hace una sola vez, con el repositorio ya importado en SonarQube Cloud:

1. En el proyecto, en **Administration → Analysis Method**, desactiva **Automatic Analysis**.
   SonarQube Cloud no admite los dos métodos a la vez: si sigue activo, el análisis desde
   GitHub Actions falla.
2. Crea un token en **My Account → Security** y guárdalo en GitHub como secreto del
   repositorio con el nombre `SONAR_TOKEN` (**Settings → Secrets and variables → Actions**).
3. Comprueba que `sonar.organization` y `sonar.projectKey` de `sonar-project.properties`
   coinciden con los de la página **Information** del proyecto.
