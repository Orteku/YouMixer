# YouMixer

**English** · [Español](README.es.md)

True shuffle and your own mixes with music from YouTube. It runs locally, on your PC only: your lists, your history and what it learns about your taste never leave it.

YouMixer is a personal project. It is not affiliated with YouTube or Google, and it reads YouTube through unofficial libraries, so it may stop working when YouTube changes something. For now it runs on Windows.

## Download (Windows)

Get the latest files from the [Releases page](https://github.com/Orteku/YouMixer/releases):

- **`YouMixer-Setup-x.y.z.exe`**: the installer. It installs for your user only (no administrator rights), asks for the language, how to open YouMixer (in your browser or in its own window) and the optional keys, adds a Start menu shortcut and shows up in *Settings → Apps* to uninstall. Your data lives in `%APPDATA%\YouMixer` and is only deleted if you say so when uninstalling.
- **`YouMixer-x.y.z-portable.zip`**: nothing to install. Unzip it anywhere and run `YouMixer.exe`; the data stays in a `data` folder beside it. Without the installer, the page's power key can't turn YouMixer on from the browser: open `YouMixer.exe` instead.

The first time, Windows may say "Windows protected your PC" because the program is not signed (a code-signing certificate costs money). Click *More info → Run anyway*. All of the code is in this repository, and you can build the very same files yourself (see *Development*).

## Running from the source code

You need Python 3.10 or newer.

- **`Install.bat`**: sets up Python, registers the `youmixer://` link (used by the page's power key) and creates a "YouMixer" shortcut in the Start menu. It's for your Windows user only and doesn't ask for administrator rights. If you don't run it, `YouMixer.bat` does it the first time.
- **`Uninstall.bat`**: turns YouMixer off and removes the `youmixer://` link, the Start menu shortcut and the Python environment (`.venv`). It asks whether to delete your data (`data`) too; by default it's kept. The folder and the code are left untouched.

## Opening it

Double-click `YouMixer.bat`. The first time it sets up what it needs. It opens at `http://localhost:8787` and runs in the background, with no window. The red power key at the top right turns it off; with YouMixer off, the same key turns it on, and the light above it shows ON or OFF. If you open it while it's already on, it just opens the page.

You don't need the `.bat` to turn it on from the page: bookmark `http://localhost:8787`. Your browser keeps a copy of the page the first time you open it with YouMixer on, so afterwards it opens even when YouMixer is off. When you press the power key, the browser opens a `youmixer://` link that starts YouMixer; the first time, it asks whether it may open it. That link is registered by `Install.bat` and removed by `Uninstall.bat`.

While it's on, an icon appears next to the Windows clock: click it to open the page, or right-click it to open the page or turn YouMixer off. It can be turned on or off in *Settings → Icon next to the clock*. If you can't see it, it may be hidden behind the ^ arrow next to the clock.

**Browser or its own window:** in *Settings → Where it opens* you choose whether YouMixer opens in your browser or in its own window (Microsoft Edge or Google Chrome in app mode, with no address bar). The key next to *Activity* switches between them right away; the copy you leave behind stops, so two players never play at once.

The clock icon's menu also lets you open it either way, switch profiles and turn it off.

Every tab, in any browser or browser profile, checks every 5 seconds whether YouMixer is on and updates itself.

Messages and errors are written to `data/youmixer.log`.

## Using it

On the left are the **Queue** and **Lists** tabs, and on the right the player. Drag the divider to change the width; double-click it to reset.

- **Lists:** paste a playlist, a mix or a video. Turn on the *Shuffle* switch of one or more lists and press *Shuffle*, or *Similar*.
  Each list keeps a copy. With *Update when opening* on, it catches up with the original when YouMixer opens, at most once every 6 hours. It's on for playlists and off for mixes, so the mix you liked is kept. The ↻ button updates it at any time.
- **Create a mix or discover** (sepia key in *Lists*): pick genres or topics, and how much should be new and how much familiar.
- **Discover something** (inside *Create a mix*): new songs based on what you play, like and skip.
- **Save mix** (in *Queue*): saves the current queue. Later you can select it in *Lists* and press *Similar* to use it as a reference.

*Create a mix*, *Activity* (pulse icon) and *Settings* (sliders icon) open in a panel that slides in from the right, without stopping the music.

Keys: space (play or pause), `N` (next), `P` (previous), `S` (shuffle), `R` (repeat: off, whole queue or this song), `L` (like), `D` (dislike and skip).

Shuffle is on by default. If you turn it off, the queue goes back to its original order without interrupting the current song. Without repeat, the music stops when the queue ends; with repeat on the whole queue and shuffle on, a new shuffle is made.

In *Activity*, the ✓ next to an avoided artist moves it to your artists, and the 🚫 next to one of your artists moves it to avoided; that choice overrides what YouMixer learns from your skips. The ✕ next to an artist forgets what was learned about it, including your choice, and the ✕ next to a history entry deletes only that entry, for example a skip by mistake.

### Saving a mix exactly as you see it

YouTube mixes change with each account and every time they load, so copying the link won't keep them. In *Settings → Save mixes from YouTube* there's a "+ YouMixer" button: drag it to the bookmarks bar of each browser profile. With YouMixer on, click that bookmark on YouTube or YouTube Music with the mix or the queue visible, and exactly those songs are saved.

## Profiles

The **Profile** key in the header opens the profiles. Each profile has its own lists, queue, history, likes, chosen artists and what YouMixer learns, so you can have one for listening with other people and another one just for you without mixing them up. Keys, the YouTube account and the clock icon are shared.

- When you create a profile you can copy the lists of the profile in use; what it learned is never copied.
- When you switch profiles, the page reloads with the new one; other open tabs update themselves.
- The *Main* profile lives in `data/youmixer.db`; the others in `data/profiles/`. When you delete one, its file is kept in `data/backups/deleted`.

## Languages

YouMixer is available in English and Spanish. The first time, it uses the Windows language; you can change it in *Settings → Language*.

All texts live in `web/i18n/`, one file per language (`en.json`, `es.json`). To add another one, copy `en.json` using the language code as the name (for example `fr.json`), and translate the texts without changing the keys or anything in braces such as `{name}`. It shows up in *Settings → Language* by itself. The tests check that every language has the same keys.

## Your data

Everything lives in `data/`:

- `youmixer.db`: lists, mixes, history, reactions, queue and position.
- `backups/`: a copy made at every start; the last 10 are kept.
- `profiles/` and `profiles.json`: the other profiles.
- `config.json` and `browser.json`: settings, optional keys and your account session, if you add them. Keep `browser.json` to yourself: it gives access to that YouTube account.

To move it to another PC, copy the `data` folder. In *Settings* you can also export the profile in use as JSON. No music is downloaded: only references are stored, with title and artist.

## If something fails

- A video that can't be embedded is replaced with another version or skipped. The reason shows up in *Activity*.
- If a video keeps loading for 60 s, it moves on to the next one without penalizing it.
- If YouTube stops responding for a while, wait a few minutes: the app already retries by itself.
- If reading from YouTube breaks, update the library: `.venv\Scripts\python.exe -m pip install -U ytmusicapi`.

## Updates

YouMixer checks the latest release published at [github.com/Orteku/YouMixer](https://github.com/Orteku/YouMixer/releases) when it turns on, and shows a notice with a download link if there's a newer one. It only reads the version number; nothing is downloaded automatically. It can be turned off in *Settings → Version*.

## Development

### Building the Windows downloads

```
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe packaginguild.py
```

This produces, in `dist/`, the installer and the portable zip. It needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`); use `--no-installer` to skip that part.

To publish a version: change `VERSION` in `youmixer/version.py`, build, and create a GitHub release tagged `v` plus that number (for example `v1.0.1`) with the two files attached. People running YouMixer are told about it from then on.

```
server.py            entry point: the local web server and its API
install.py           Windows integration (youmixer:// link, Start menu shortcut)
youmixer/
  service.py         what the app does: import, shuffle, generate mixes, learn
  engine.py          shuffling and recommendation logic, with no network or disk
  ytclient.py        YouTube Music, YouTube Data API and Last.fm, paced to avoid throttling
  store.py           SQLite storage of one profile
  profiles.py        one database per profile
  config.py          settings shared by all profiles
  i18n.py            texts, read from web/i18n/
  launcher.py        opens the page in the browser or in its own window
  tray.py            icon next to the clock
  updates.py         looks for new releases on GitHub
web/
  index.html, style.css, app.js   the page (plain HTML, CSS and JavaScript, no build step)
  sw.js              keeps the page available while YouMixer is off
  i18n/              one JSON file per language
tests/               unit tests; they never touch the network
```

Requests to YouTube go one at a time, two seconds apart, with retries: going faster gets empty answers. That is why importing takes a few seconds.

Tests: `.venv\Scripts\python.exe -m unittest discover -s tests`

`YOUMIXER_DATA` and `YOUMIXER_PORT` change the data folder and the port, to test without touching your real data. `YOUMIXER_TRAY=0` disables the clock icon, so a test instance that gets killed doesn't leave ghost icons behind, and `YOUMIXER_NO_LAUNCH=1` stops it from opening browser windows or message boxes.

To publish a version, update `VERSION` in `youmixer/version.py` and create a GitHub release whose tag is that same number with a `v` in front, for example `v1.0.0`.
