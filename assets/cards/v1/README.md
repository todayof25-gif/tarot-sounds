# Tarot Deck Assets (`/assets/cards/v1`)

This folder contains tarot deck images served from `https://www.aeipet.com/assets/cards/v1/...`.

## Structure
- `rws_1909/`
  - `cover.jpg`
  - `major_fool.jpg` ... `pentacles_king.jpg` (78 files, slot-id naming)
- `marseille_bnf/`
  - `cover.jpg`
  - `major_fool.jpg` ... `pentacles_king.jpg` (78 files, slot-id naming)

## Naming
Files are named by `TarotDeckSchema` slot ids:
- Major: `major_*`
- Minor: `{wands|cups|swords|pentacles}_{ace|2..10|page|knight|queen|king}`

## Rebuild
The repo includes a helper script:
- `tarot-sounds/scripts/build_tarot_decks.py`

Example (requires Pillow):
```bash
python3 -m venv /tmp/ht-venv
/tmp/ht-venv/bin/pip install Pillow==10.4.0
/tmp/ht-venv/bin/python tarot-sounds/scripts/build_tarot_decks.py --all
```

## Sources / License
- `marseille_bnf` images are downloaded from Wikimedia Commons
  (`Category:Tarot de Marseille (Single Cards)`) and are marked as `Public domain`.

