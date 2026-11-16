# YouMixer

[English](README.md) · **Español**

Shuffle real y mixes propios con música de YouTube. Funciona en local, solo en tu PC: tus listas, tu historial y lo que aprende de tus gustos no salen de él.

YouMixer es un proyecto personal. No está afiliado a YouTube ni a Google, y lee YouTube con librerías no oficiales, así que puede dejar de funcionar cuando YouTube cambie algo. De momento funciona en Windows.

## Descargar (Windows)

Los archivos más recientes están en la [página de versiones](https://github.com/Orteku/YouMixer/releases):

- **`YouMixer-Setup-x.y.z.exe`**: el instalador. Se instala solo para tu usuario (sin permisos de administrador), pregunta el idioma, cómo abrir YouMixer (en el navegador o en su propia ventana) y las claves opcionales, añade un acceso en el menú Inicio y aparece en *Configuración → Aplicaciones* para desinstalarlo. Tus datos están en `%APPDATA%\YouMixer` y solo se borran si lo indicas al desinstalar.
- **`YouMixer-x.y.z-portable.zip`**: no hay que instalar nada. Descomprímelo donde quieras y abre `YouMixer.exe`; los datos se quedan en una carpeta `data` a su lado. Sin el instalador, la tecla de encendido de la página no puede encender YouMixer desde el navegador: abre `YouMixer.exe`.

La primera vez, Windows puede decir "Windows protegió tu PC" porque el programa no está firmado (un certificado de firma cuesta dinero). Pulsa *Más información → Ejecutar de todas formas*. Todo el código está en este repositorio y puedes generar tú mismo los mismos archivos (mira *Desarrollo*).

## Usarlo desde el código fuente

Necesitas Python 3.10 o más reciente.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe server.py
```

Los datos van a una carpeta `data` dentro del proyecto. El enlace `youmixer://` y el acceso del menú Inicio solo los crea el instalador.

## Abrirlo

Ejecuta `YouMixer.exe` (o `server.py`, desde el código fuente). Se abre en `http://localhost:8787` y funciona en segundo plano, sin ventana. La tecla roja de encendido, arriba a la derecha, lo apaga; con YouMixer apagado, la misma tecla lo enciende y el piloto de encima indica ON u OFF. Si lo abres estando ya encendido, solo abre la página.

Para encender desde la página: guarda `http://localhost:8787` en marcadores. El navegador guarda una copia de la página la primera vez que la abres con YouMixer encendido, así que después se abre aunque esté apagado. Al pulsar *Encender*, el navegador abre un enlace `youmixer://` que arranca YouMixer; la primera vez pregunta si puede abrirlo. Ese enlace lo registra el instalador y se quita al desinstalar; con la versión portable, abre `YouMixer.exe`.

Mientras está encendido aparece un icono junto al reloj de Windows: con un clic abre la página, y con clic derecho puedes abrirla o apagar YouMixer. Se quita y se pone con la casilla de *Ajustes → Icono junto al reloj*. Si no lo ves, puede estar escondido en la flecha ^ junto al reloj.

**Navegador o ventana propia:** en *Ajustes → Dónde se abre* eliges si YouMixer se abre en tu navegador o en su propia ventana (Microsoft Edge o Google Chrome en modo aplicación, sin barra de direcciones). La tecla junto a *Actividad* cambia de uno a otro en el momento; la copia que dejas se detiene, para que nunca suenen dos a la vez.

El menú del icono del reloj también permite abrirlo de una forma u otra, cambiar de perfil y apagarlo.

Todas las pestañas, en cualquier navegador o perfil, comprueban cada 5 segundos si YouMixer está encendido y se actualizan solas.

Los mensajes y errores quedan en `data/youmixer.log`.

## Uso

A la izquierda están las pestañas **Cola** y **Listas**, y a la derecha el reproductor. Arrastra la división para cambiar el ancho; con doble clic vuelve al tamaño inicial.

- **Listas:** pega una playlist, un mix o un vídeo. Marca una o varias listas y pulsa *Mezclar*, o *Parecidas*.
  Cada lista guarda una copia. Con *Actualizar sola al abrir* marcada, se pone al día con la original al abrir YouMixer, como mucho una vez cada 6 horas. Viene marcada en las playlists y desmarcada en los mixes, para conservar el mix que te gustó. El botón ↻ actualiza en cualquier momento.
- **Crear mix o descubrir** (tecla sepia en *Listas*): elige géneros o temas, y cuánto quieres de nuevo y de conocido.
- **Descúbreme algo** (dentro de *Crear mix*): canciones nuevas según lo que escuchas, te gusta y saltas.
- **Guardar como mix** (en *Cola*): guarda la cola actual. Después puedes marcarlo en *Listas* y pulsar *Parecidas* para usarlo como referencia.

*Crear mix*, *Actividad* (icono de pulso) y *Ajustes* (icono de controles) se abren en un panel que entra desde la derecha, sin cortar la música.

Teclas: espacio (reproducir o pausar), `N` (siguiente), `P` (anterior), `S` (aleatorio), `R` (repetir: no, toda la cola o esta canción), `L` (me gusta), `D` (no me gusta y saltar).

El aleatorio viene activado. Si lo quitas, la cola vuelve al orden original sin cortar la canción que suena. Sin repetir, la música se para al acabar la cola; con repetir toda la cola, si el aleatorio está activado, se hace una mezcla nueva.

En *Actividad*, el ✓ junto a un artista evitado lo pasa a tus artistas y el 🚫 junto a uno de tus artistas lo pasa a evitados; esa elección manda sobre lo que YouMixer aprenda de tus saltos. La ✕ junto a un artista olvida lo aprendido de él, también tu elección, y la ✕ junto a una entrada del historial borra solo esa entrada; por ejemplo, un salto por error.

## Perfiles

La tecla **Perfil** de la cabecera abre los perfiles. Cada perfil tiene sus propias listas, cola, historial, «Me gusta», artistas elegidos y lo que YouMixer aprende, así que puedes tener uno para escuchar con gente y otro para lo tuyo sin que se mezclen. Las claves, la cuenta de YouTube y el icono del reloj son comunes.

- Al crear un perfil puedes copiar las listas del perfil en uso; lo aprendido nunca se copia.
- Al cambiar de perfil, la página se recarga con el nuevo; las demás pestañas abiertas se ponen al día solas.
- El perfil *Principal* está en `data/youmixer.db`; los demás, en `data/profiles/`. Al borrar uno, su archivo se guarda en `data/backups/deleted`.

## Idiomas

YouMixer está en español e inglés. La primera vez usa el idioma de Windows; se cambia en *Ajustes → Idioma*.

Todos los textos están en `web/i18n/`, un archivo por idioma (`es.json`, `en.json`). Para añadir otro, copia `en.json` con el código del idioma (por ejemplo `fr.json`), y traduce los textos sin tocar las claves ni lo que va entre llaves, como `{name}`. Aparece solo en *Ajustes → Idioma*. Las pruebas comprueban que todos los idiomas tengan las mismas claves.

## Tus datos

Todo está en `data/`:

- `youmixer.db`: listas, mixes, historial, reacciones, cola y posición.
- `backups/`: una copia al arrancar, se guardan las 10 últimas.
- `profiles/` y `profiles.json`: los demás perfiles.
- `config.json` y `browser.json`: ajustes, claves opcionales y la sesión de tu cuenta, si las añades. No compartas `browser.json`: da acceso a esa cuenta de YouTube.

Para llevártelo a otro PC, copia la carpeta `data`. En *Ajustes* también puedes exportar el perfil en uso a JSON. La música no se descarga: se guardan las referencias, con título y artista.

## Si algo falla

- Un vídeo que no se puede incrustar se sustituye por otra versión o se salta. El motivo aparece en *Actividad*.
- Si un vídeo se queda cargando 60 s se pasa al siguiente, sin penalizarlo.
- Si YouTube no responde durante un rato, espera unos minutos: la app ya reintenta sola.
- Si se rompe la lectura de YouTube, actualiza la librería: `.venv\Scripts\python.exe -m pip install -U ytmusicapi`.

## Actualizaciones

Al encenderse, YouMixer consulta la última versión publicada en [github.com/Orteku/YouMixer](https://github.com/Orteku/YouMixer/releases) y, si hay una más nueva, avisa con un enlace para descargarla. Solo lee el número de versión; no descarga nada solo. Se puede desactivar en *Ajustes → Versión*.

## Desarrollo

### Generar las descargas de Windows

```
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe packaging\build.py
```

Esto crea en `dist/` el instalador y el zip portable. Necesita [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`); con `--no-installer` se salta esa parte.

Para publicar una versión: cambia `VERSION` en `youmixer/version.py`, genera las descargas y crea en GitHub una *release* con la etiqueta `v` más ese número (por ejemplo `v1.0.1`) con los dos archivos adjuntos. A partir de ahí, quien use YouMixer recibirá el aviso.

```
server.py            punto de entrada: el servidor web local y su API
youmixer/
  service.py         lo que hace la app: importar, mezclar, generar mixes, aprender
  engine.py          lógica de mezcla y recomendación, sin red ni disco
  ytclient.py        YouTube Music, YouTube Data API y Last.fm, con pausas para evitar cortes
  store.py           guardado en SQLite de un perfil
  profiles.py        una base de datos por perfil
  config.py          ajustes comunes a todos los perfiles
  i18n.py            textos, leídos de web/i18n/
  launcher.py        abre la página en el navegador o en ventana propia
  tray.py            icono junto al reloj
  updates.py         busca versiones nuevas en GitHub
web/
  index.html, style.css, app.js   la página (HTML, CSS y JavaScript sin compilar)
  sw.js              mantiene la página disponible con YouMixer apagado
  i18n/              un archivo JSON por idioma
tests/               pruebas unitarias; nunca tocan la red
```

Las peticiones a YouTube van de una en una, con dos segundos entre ellas y reintentos: más rápido, YouTube responde vacío. Por eso importar tarda unos segundos.

El código y sus comentarios están en inglés.

Pruebas: `.venv\Scripts\python.exe -m unittest discover -s tests`

`YOUMIXER_DATA` y `YOUMIXER_PORT` cambian la carpeta de datos y el puerto, para probar sin tocar los datos reales. `YOUMIXER_TRAY=0` evita el icono junto al reloj, para que un YouMixer de prueba cerrado de golpe no deje iconos fantasma, y `YOUMIXER_NO_LAUNCH=1` evita que abra ventanas del navegador o avisos.

## Guardar un mix tal como lo ves

Los mixes de YouTube cambian según la cuenta y en cada carga, así que copiar el enlace no sirve para conservarlos. En *Ajustes → Guardar mixes desde YouTube* hay un botón «+ YouMixer»: arrástralo a la barra de marcadores de cada perfil. Con YouMixer abierto, pulsa ese marcador en YouTube o YouTube Music con el mix o la cola a la vista, y se guardan exactamente esas canciones.

Para publicar una versión, cambia `VERSION` en `youmixer/version.py` y crea en GitHub una *release* cuya etiqueta sea ese mismo número con una `v` delante, por ejemplo `v1.0.0`.
