# Changelog

All notable changes to this project are documented here. This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.0] - 2026-11-09

### Added
- **Stats tab** (desktop and web): look up any Epic, Xbox or PlayStation player for the current season in 8 modes (All, Battle Royale, Blitz, OG, Reload, Ranked, Ranked Reload, Arenas Boxfights): wins, win rate, matches, K/D, kills per match, kills, time played, average match, level, and rank with progress for Ranked / Arenas. **Track** players (sidebar + header), recent searches, and **progress since your last check** with a wins/kills trend from saved lookups. `Ctrl+8`; web route `#stats/<mode>/<name>[@xbl|@psn]`
- **Season leaderboards**: 25 boards (level, wins, kills, time, rank per mode), top 40 each; click a name to look them up. `tools/scrape_fortnitegg.py --only stats` builds `docs/data/stats.json`; the data Action refreshes it every 3 hours
- Player lookups use Fortnite.GG's stats JSON (`/stats[/<mode>]?player=<name>&ajax`). The desktop app calls it directly; browsers block it from the web demo until Fortnite.GG sends a CORS header, so the web page explains that and links to the player on Fortnite.GG
- **Locker tab** (desktop and web): every outfit, emote, back bling, pickaxe, glider, sidekick, kicks, wrap, contrail, aura, emoticon, spray and loading screen from [Fortnite.GG](https://fortnite.gg/cosmetics) (15,744 items, 13 type chips) with in-game **showcase videos**, grouped by season (newest first), NEW / IN SHOP badges, and filters that adapt to the type (This season, In the shop now, Dances, Traversal, Synced, Built-in, With styles, Reactive, Animated, Unreleased). Sort by newest, oldest, name or rarity. `Ctrl+7`; web routes `#locker/<type>/<id>` (old `#emotes/<id>` links still work)
- **Showcase player:** play/pause, seek, `HD` (remembered), `0.5×` speed, sound and full screen (web). Web cards play a muted preview on hover (toggle with **Previews**). Desktop decodes the clip in the app with PyAV and plays its sound in sync through Windows' built-in `winsound` (no extra dependency): sound follows play/pause, loops, and `0.5×` (slow-motion pitch), with a remembered **Sound on/off** switch; silent clips show "No sound". Sprays and loading screens show their full-size art. Without PyAV, clips open in the browser
- Items in the **Cosmetics** tab play their showcase video too (each type's data loads on demand), with "Open in Locker"
- `tools/scrape_fortnitegg.py --only locker` builds `docs/data/locker/index.json` plus one file per type from Fortnite.GG's item list, and matches items to Epic ids (fortnite-api.com) by type, name and release date (15,716 / 15,744 matched). The daily data Action refreshes it. Clips stream from Fortnite.GG's CDN (`video-sd.mp4` ~1-2 MB, `video.mp4` HD); nothing is bundled
- Desktop dependency: `av` (PyAV) is now in `requirements.txt` and in the release exe (the exe grows from ~19 MB to ~47 MB)

## [1.1.0] - 2026-11-08

### Changed
- **New look:** both apps use the Fortnite.GG visual style. Dark grey surfaces (`#2f3136` / `#202225`), yellow accent (`#fce51e`), green owned and red locked states, and condensed uppercase headings (Bahnschrift; the site's Burbank font is licensed and not bundled)

### Added
- **News tab** (desktop and web): Epic's official Fortnite news (about 60 posts, two months) as image cards grouped by month, with an **In game now** section from Epic's live in-game news (fortnite-api.com), player votes, search, and links that open featured cosmetics in the app. Links to fortnite.com/news and the Fortnite.GG archive. `Ctrl+6`; web route `#news/<id>`
- `tools/scrape_fortnitegg.py --only news` builds `docs/data/news.json` from fortnite.gg/news. The data Action now refreshes news every 3 hours (vote changes alone don't commit). fortnite.com/news can't be read by scripts (Cloudflare 403, and its `/api/news` route is feature-flagged off), so the same Epic posts come from Fortnite.GG
- **Interactive map** (desktop and web): the current season's island from Fortnite.GG with 38 layers: named locations, landmarks, chests (gold outline = 100% spawn), rare/buried/sprite chests, vaults, loot cannons, wanted posters, ammo boxes, vending machines, launch pads, cannons, cars, boats, off-road tires, ziplines, Port-a-Potty tunnels, campfires, produce boxes, slurp barrels/trucks/cacti, fishing rods and spots, reboot vans, extraction sites and NPCs. Pan, zoom (wheel, pinch, keyboard), marker clusters with counts, hover names, click for details (layer, nearest place, position), "Only this layer" / "Hide layer", location search with `Enter` to jump, and layer choices remembered. Web view links `#map/@x,y,zoom`
- `tools/scrape_fortnitegg.py` now also builds `docs/data/map.json` (`--only map` for just the map). Tiles and icons are loaded from fortnite.gg at runtime; the desktop app caches them under `%LOCALAPPDATA%\FortniteCosmeticsBrowser\map\`. The daily data Action refreshes it with the weapon stats
- Keyboard: `Ctrl+5` opens the map
- **Weapons & Items tab** (desktop and web): the current Battle Royale loot pool (weapons, consumables, utility) with damage, headshot damage, DPS, fire rate, magazine, reload, structure damage, spread, recoil and aim-down-sights time for every rarity, a damage-by-distance chart, spawn chances (chests, floor loot, rare chests, supply drops, plus vending machines and ammo boxes), modes and descriptions. Also browse all 476 weapons ever (damage and DPS per rarity), sort by any stat, and copy stats
- `tools/scrape_fortnitegg.py` builds `docs/data/weapons.json` from Fortnite.GG (standard library only, rate-limited). A daily GitHub Action (`data.yml`) re-runs it and commits changes, so stats stay current without app releases
- Keyboard: `Ctrl+4` opens Weapons & Items; `Enter` / double-click opens the weapon on Fortnite.GG. Web route `#weapons/<slug>`
- **Sprite tracker** (desktop and web): every Sprite in the current season (Chapter 7 · Treasure Hunters) with its ability, rarity, resummon cost and variants
- Fortnite.GG-style sprite page: a hero header with Owned / Mastered counters and season chips. **Every sprite and every variant (Fortune, Cursed, Gold) is its own card** with **Owned** and **Mastered** checkboxes, plus Variant and Sort filters. Unreleased versions show a lock and their release date. Variants come from data, so new ones Epic adds later show up without an app update
- **Official sprite images from [Fortnite.GG](https://fortnite.gg/sprites)**, loaded at runtime from its image CDN by each sprite's internal name (`T_Icon_BR_Creature_Sprite_<Name>[_Jeweled|_Cursed|_Gold]_L.webp`). Used with the site owner's permission
- Filters for Missing, Captured, Mastered and Missing variants, plus per-rarity progress and totals
- Upcoming sprites and variants are marked with their release date
- Export / import progress as JSON. The same file works in both the desktop app and the web demo
- Keyboard: `Ctrl+3` opens Sprites. With a card selected, `Space` toggles Owned and `M` toggles Mastered
- Web routes `#sprites/<id>` and `#sprites/<id>~<variant>`
- **Your own sprite photos:** select a sprite, take a screenshot (`Win+Shift+S`) and press `Ctrl+V`, or pick a file. This works for the base sprite or any variant. Desktop saves to `sprite_images\`; web saves in the browser
- **Official Epic art:** Battle Royale news cards that mention Sprites (Epic's feed via fortnite-api.com `/v2/news/br`) show in the sprite detail panel
- **Real sprite art** from the Fortnite Wiki, looked up at runtime by the wiki's file naming (`Fire Sprite - Item - Fortnite.png`, `Gold Fire Sprite - ...`) and cached for 6 hours. It is hotlinked, not bundled. Desktop also uses your own images from `%LOCALAPPDATA%\FortniteCosmeticsBrowser\sprite_images\<id>.png` or `<id>_<variant>.png`. `sprites.json` can set `image`, `images` or `wiki` per sprite. Stand-in art is shown until real art exists

### Notes
- Epic has no public Sprite API, so the catalog is a community-maintained file, `docs/data/sprites.json`. Both apps download it from the website, so roster updates go live without a new release. The desktop app falls back to its last copy, then to the copy built into the exe.
- As of Nov 7, 2026 the wiki has no Treasure Hunters sprite art yet, so stand-ins show for now. Art appears automatically once the wiki uploads it.

## [1.0.0] - 2026-11-07

First public release by [248Tech](https://248tech.com).

### Desktop app (Windows)
- Browse all 16,000+ Fortnite Battle Royale cosmetics with search, category, rarity and sort filters
- Today's Item Shop grouped by section, with V-Bucks prices, discounts, "leaves in" timers and a reset countdown
- "In shop" badges, item ↔ offer navigation, and an "Open in Epic Store" button that opens fortnite.com in Chrome
- Virtualized grid, S/M/L tile sizes, keyboard navigation and a right-click menu
- Offline thumbnail cache (WebP) with a one-click "download all icons" option, plus CSV export

### Web demo
- Static web version in `docs/`, served by GitHub Pages, with the same search, filters, shop view and fortnite.com links
- Mobile layout, shareable `#item/<id>` and `#shop/<offerId>` links

[Unreleased]: https://github.com/248Tech/fortnite-cosmetics-browser/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/248Tech/fortnite-cosmetics-browser/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/248Tech/fortnite-cosmetics-browser/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/248Tech/fortnite-cosmetics-browser/releases/tag/v1.0.0
