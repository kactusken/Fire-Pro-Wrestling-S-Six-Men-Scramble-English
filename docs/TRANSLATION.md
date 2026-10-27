# Translation

## Where the text is

| File | Holds | Checked by |
|---|---|---|
| `translation/script/interviews.txt` | Victory Road: the interviews before each match, the narration | `tools/lint.py` (lines, 236 px) |
| `translation/text/menus.txt` | menus, options, help lines, match and mode text (2ND.BIN) | `tools/lint.py` |
| `translation/text/messages.txt` | save / backup memory messages and others (1ST.BIN) | `tools/lint.py` |
| `translation/text/wrestlers.csv` | the 160-wrestler roster: names (real and parody), nicknames | `tools/lint.py` (bytes) |
| `translation/text/promotions.csv` | the 15 promotions, long and short names (real and parody) | `tools/lint.py` (bytes) |
| `translation/text/moves.csv` | move names (one row per distinct name) | the build (pool size) |
| `translation/text/name_tokens.csv` | other names that differ between the builds: factions, a referee, the word Panther | `tools/lint.py` (tokens) |
| `translation/text/save_titles.csv` | the two backup files' comments (memory manager) | `tools/lint.py` (bytes), the build (ASCII) |
| `translation/glossary.csv` | names (written by `tools/names.py glossary`) and terms | `tools/lint.py` |

## File formats

Message blocks: `@ id`, source lines (`JP `), translation lines (`EN `); no `EN` lines = original
kept. Interviews: one `EN` line per line on screen, at most as many as the `JP` lines. Menus: one
string per block, `{n}` is a new line inside it. Tables: original columns beside English ones. See
`tools/blocks.py` and `tools/textdb.py`.

Control codes (`tools/fpstext.py`): `{n}` new line, `{t}` tab, `{s3}` colour, `{p8,32,}` position,
`{x1,}` / `{y7,}` move the pen, `{r12,}` line height, `{b}`, `{w..}` / `{c..}` boxes, `{$hh}` a raw
byte. Keep them exactly; `{x..}` lines up columns, so keep it where the Japanese has it.

**Names** that differ between the two builds are written as `<tokens>` in the game's own (parody)
form: `<Rikimaru>`, `<Fighter Yamato>`, `<View Japan>`, `<VJP>`. The build turns them into the real
names (default) or keeps the parody names (`--names parody`). `python3 tools/names.py list` shows
every token; the glossary has the Japanese for each.

## Style guide

- **Characters:** the font has A-Z a-z 0-9 and ``! " # % & ' ( ) * + , - . / : ; = ? [ \ ] ^ _ ` ~``
  plus … ★ ☆ ♪ × ÷; not `$ < > @ { | }` (lint reports any character without a glyph).
  Letters, `. , ' -` and space take 1 byte; digits and other symbols 2.
- **Widths:** letters are proportional (a-z 6-10 px, A-Z 8-12, space 8). Interview lines: at most
  236 px (about 30 letters). Menus: keep the English about as wide as the Japanese (`# px=` in
  each block is the original width); abbreviate where needed (Pts, W-L-D, Lv).
- **Interviews:** speech in double quotes: 「 opens on the first line, 」 closes on the last;
  『』 become "" too. Narration unquoted. `・・・` becomes `...`; `～` is dropped or becomes `!`.
- **Voice:** natural, punchy wrestling-promo English, like a well-localized 1990s wrestling
  game. Heels rude, veterans gruff, rookies eager, champions proud. Keep shouts and emphasis.
  No added jokes, no modern slang, no censorship.
- **Names:** given name first in prose. Story speech usually uses the surname (the short-name
  token, `<Rikimaru>`). Honorifics: drop さん/君; "Mr. X" for polite address; 先輩 is just the
  name; 社長 is "the President" / "Boss".
- **Terms:** the established English Fire Pro terms (Recovery, Breathing, Spirit, Submission...),
  the usual English move names (Lariat, German Suplex, DDT); katakana English becomes the English
  word. Numbers as digits. Menus in Title Case, help text in sentence case.
- **Repeated text** gets the same English every time.

## Decisions

| Decision | Who / why |
|---|---|
| Scope: all text useful to the player - menus, wrestler names and profiles, moves, edit mode, Victory Road and all storylines, messages, save title, images with such text | user, 2026-10-26 |
| Two English releases: real wrestler names and the game's parody names (`build.py --names`) | user, 2026-10-26 |
| Optional extras: debug menu and the hidden extra wrestlers (unlock group `extras`, "(Extras)" patches) | user, 2026-10-26 (replaced 2026-10-27, below) |
| Extras also unlock the 24 hidden roster wrestlers and let Wrestler Edit pick the secret G Gundam theme; the Edit presets list stops at 212 (the last real one); the match monitor stays a developer build option (`debug-monitor`) | user, 2026-10-27 |
| A new translation, not based on the earlier v0.91 fan patch | user, 2026-10-26 |
| Shares names and terms with Fire Pro Wrestling G and Iron Slam '96 (same series) | user, 2026-10-26 |
| Wrestler names given name first in both builds ("Keiji Mutoh", "Ken Shundo"); the short name stays the family or ring name | user, 2026-10-26 |
| Real and parody wrestler names from the owner's list, which also names the 8 that were unknown; Fire Pro G elsewhere. Kept against the list: parody Hisakatsu Toya (久勝), Takashi Minemura (峰村), Taishi Hosaka (大志), the kanji's readings; real Hans Nijman (spelling) | user, 2026-10-26; the exceptions provisional |
| Promotions: HIDE is "Legends" in the real build, HWA stays HWA | user, 2026-10-26 |
| Short names too long for the Wrestler Select grid (7 glyphs, 52 px) are split over both name fields with no separator ("Fujinam" + "i"): the grid shows the start, the full name is the family name alone ("Fujinami"); 37 real, 36 parody. Text tokens keep the whole name | user, 2026-10-27 |
| Factions get their real names in the real build, parody names in the parody build: Road Warriors, Steiner Brothers, Mascaras Brothers (`name_tokens.csv`); the YukiPro faction is Snow Monkey Unit (parody) / Kaientai (real, provisional). Royal Lips, J. Force and the team list's other names: same in both | user, 2026-10-26 |
| The Brilliant Bulls are Dynamite Kid's team (Victory Road): real name British Bulldogs, not Steiner Brothers. The YukiPro faction is Snow Monkeys (parody) / Kaientai (real) in the team list and "Heisei Snow Monkeys" / "Heisei Kaientai" in the interview | user, 2026-10-27 |
| Victory Road and endings: second English review (78 suggestions) applied | user, 2026-10-27 |
| Release patches: English Real Names, English Parody Names, English Real + Unlocked, English Parody + Unlocked, Japanese + Unlocked. "Unlocked" (group `unlock`) = everything a game clear unlocks (game-clear flag treated as set), 255 Edit points, Edit presets to 212, the G Gundam theme. The debug menu is a developer build option only (`debug-menu`), not in any patch | user, 2026-10-27 |
| パンサー as a word (styles, costume parts, Panther Squad, Flying Panther) is "Tiger" in the real build (`<Panther*>`); referee Panther Tottori = Tiger Hattori (provisional) | user, 2026-10-26 |
| Staff credits stay as the original (Japanese names, the English job titles as they are) | user, 2026-10-26 |
| Puroresu shouts kept (Ora!, Kora!, Eh!), also for speakers outside Kono's faction; 必殺 "Special", "blocks", "Overtime" | user, 2026-10-26 |
| Nicknames written as tokens (ケイスキー, オキータ, the アックス chant), 羽山 "Hayama", ＮＡＴＯ: left for now | user, 2026-10-26 |
| Hometowns Thai / Swiss / Holland; item names Thunder Tights, Fuma Tights, Aztec Suit, G.C. Appeal | user, 2026-10-26 |
| The debug menu (extras) keeps its developer ASCII labels; the name-entry keyboard is unchanged (it has A-Z/a-z rows) | user, 2026-10-26 |
| Taunt marks ○ / × in front of taunt names: kept until seen in game | user, 2026-10-26 (open) |
| Save comments "FPS6M DATA" / "FPS6M EDIT" (capitals: the memory manager's font) | provisional, 2026-10-26 |
| Victory Road interview speakers keep the short names (tight against the opening quote, no overlap); interview lines at most 204 px | user, 2026-10-27 |
| Two-letter glyphs for common letter pairs; the name-entry keyboard's kanji page is blank (no kanji needed in the English release) | user, 2026-10-27 |
| Wrestler Edit profile labels in full words (Promotion, Height, Weight, Year, Reversal, Critical, Recovery...; かけ声 = Shout) | user, 2026-10-27 |
| Wrestler Select labels: Nick, From, Move, Ht., Born, Wt. (40x16 plates; the game's own English glyphs, bold, with the original's shadow) | provisional, 2026-10-27 |
| English text: tightened Latin glyphs (flush left, ink + 1 px), digits keep 8 px; space stays 8 px until seen in game | user, 2026-10-26 (wait and see) |

## Names

Every wrestler name is kept twice: the real wrestler the character stands for, and the game's
parody name romanized. `build.py --names real` (the default) and `--names parody` pick the
column; the release has a patch for each. `wrestlers.csv` has `en_*` (real) and `parody_*`
columns: name1 (the short name), name2, and the order the two are joined in (`2-1`: name2 first,
for "Keiji Mutoh"; `1-2` for western names the Japanese writes given name first, such as Big
Schteiner). The build sets the record's order bit and separator to match, so the names carry no
spaces at their ends. `promotions.csv` has `en_*` / `parody_*` long and short names.

## What stays untranslated

Scenery text that only decorates the background art (signs such as an exit sign on a door, posters
in the arena) - marked `keep` in graphics.csv. Anything the player reads to use the game is
translated.
