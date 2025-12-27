#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

try:
  from PIL import Image
except Exception:  # pragma: no cover
  print(
    'Missing dependency: Pillow\n\n'
    'Suggested:\n'
    '  python3 -m venv /tmp/ht-venv\n'
    '  /tmp/ht-venv/bin/pip install Pillow==10.4.0\n'
    '  /tmp/ht-venv/bin/python tarot-sounds/scripts/build_tarot_decks.py --all\n',
    file=sys.stderr,
  )
  raise


def _repo_root() -> Path:
  return Path(__file__).resolve().parents[2]


def _load_slot_ids(schema_path: Path) -> list[str]:
  text = schema_path.read_text(encoding='utf-8')
  slot_ids = re.findall(r"id: '([^']+)'", text)
  if len(slot_ids) != 78:
    raise RuntimeError(f'Unexpected slot id count: {len(slot_ids)} (expected 78)')
  return slot_ids


def _commons_upload_url(file_name: str) -> str:
  digest = hashlib.md5(file_name.encode('utf-8')).hexdigest()
  quoted = urllib.parse.quote(file_name)
  return f'https://upload.wikimedia.org/wikipedia/commons/{digest[0]}/{digest[:2]}/{quoted}'


def _download_url(url: str, dest: Path) -> None:
  dest.parent.mkdir(parents=True, exist_ok=True)
  dest.unlink(missing_ok=True)

  attempt = 0
  while True:
    result = subprocess.run(
      [
        'curl',
        '-sS',
        '-L',
        '-A',
        'hellotarot-ai/1.0',
        '-o',
        str(dest),
        '-w',
        '%{http_code}',
        url,
      ],
      check=False,
      capture_output=True,
      text=True,
    )

    code = (result.stdout or '').strip()
    if code == '200' and dest.exists() and dest.stat().st_size > 0:
      return

    dest.unlink(missing_ok=True)

    if code != '429' or attempt >= 6:
      raise RuntimeError(
        f'curl download failed ({code}). url={url}\n{result.stderr}'.strip()
      )

    wait_s = min(60.0, 2.0 * (2**attempt))
    print(
      f'Wikimedia rate-limited (429). Retrying in {wait_s:.0f}s...',
      file=sys.stderr,
    )
    time.sleep(wait_s)
    attempt += 1


def _resize_to_jpeg(
  *,
  src: Path,
  dest: Path,
  width: int,
  quality: int,
) -> None:
  image = Image.open(src).convert('RGB')
  target_height = round(image.height * width / image.width)
  resized = image.resize((width, target_height), Image.Resampling.LANCZOS)
  dest.parent.mkdir(parents=True, exist_ok=True)
  resized.save(
    dest,
    format='JPEG',
    quality=quality,
    optimize=True,
    progressive=True,
  )


def _rws_minor_rank_to_index(rank: str) -> int:
  return {
    'ace': 1,
    '2': 2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    '10': 10,
    'page': 11,
    'knight': 12,
    'queen': 13,
    'king': 14,
  }[rank]


def build_rws_1909(*, src_dir: Path, dest_dir: Path, slot_ids: list[str]) -> None:
  major_slots = [slot for slot in slot_ids if slot.startswith('major_')]
  if len(major_slots) != 22:
    raise RuntimeError(f'Unexpected major arcana slots: {len(major_slots)}')

  dest_dir.mkdir(parents=True, exist_ok=True)

  for index, slot in enumerate(major_slots):
    glob = f'RWS_Tarot_{index:02d}_*.jpg'
    matches = sorted(src_dir.glob(glob))
    if len(matches) != 1:
      raise RuntimeError(f'Expected exactly 1 match for {glob}, got {len(matches)}')
    shutil.copyfile(matches[0], dest_dir / f'{slot}.jpg')

  def copy_minor(prefix: str, slot_prefix: str) -> None:
    for slot in slot_ids:
      if not slot.startswith(f'{slot_prefix}_'):
        continue
      rank = slot.split('_', 1)[1]
      index = _rws_minor_rank_to_index(rank)
      src = src_dir / f'{prefix}{index:02d}.jpg'
      if not src.exists():
        raise RuntimeError(f'Missing file: {src}')
      shutil.copyfile(src, dest_dir / f'{slot}.jpg')

  copy_minor('Wands', 'wands')
  copy_minor('Cups', 'cups')
  copy_minor('Swords', 'swords')
  copy_minor('Pents', 'pentacles')

  shutil.copyfile(dest_dir / 'major_fool.jpg', dest_dir / 'cover.jpg')


def _marseille_major_code(slot: str) -> str:
  codes = {
    'major_fool': 'TT',
    'major_magician': 'T1',
    'major_high_priestess': 'T2',
    'major_empress': 'T3',
    'major_emperor': 'T4',
    'major_hierophant': 'T5',
    'major_lovers': 'T6',
    'major_chariot': 'T7',
    'major_strength': 'T11',
    'major_hermit': 'T9',
    'major_wheel_of_fortune': 'T10',
    'major_justice': 'T8',
    'major_hanged_man': 'T12',
    'major_death': 'T13',
    'major_temperance': 'T14',
    'major_devil': 'T15',
    'major_tower': 'T16',
    'major_star': 'T17',
    'major_moon': 'T18',
    'major_sun': 'T19',
    'major_judgement': 'T20',
    'major_world': 'T21',
  }
  if slot not in codes:
    raise RuntimeError(f'Unsupported major slot for Marseille: {slot}')
  return codes[slot]


def _marseille_minor_code(slot: str) -> str:
  suit, rank = slot.split('_', 1)
  suit_code = {
    'wands': 'B',
    'cups': 'C',
    'pentacles': 'P',
    'swords': 'S',
  }[suit]
  rank_code = {
    'ace': '1',
    '2': '2',
    '3': '3',
    '4': '4',
    '5': '5',
    '6': '6',
    '7': '7',
    '8': '8',
    '9': '9',
    '10': '10',
    'page': 'J',
    'knight': 'H',
    'queen': 'Q',
    'king': 'K',
  }[rank]
  return f'{rank_code}{suit_code}'


def _marseille_commons_title(slot: str) -> str:
  if slot.startswith('major_'):
    code = _marseille_major_code(slot)
  else:
    code = _marseille_minor_code(slot)
  return f'{code} Tarot.png'


def build_marseille_bnf(
  *,
  dest_dir: Path,
  slot_ids: list[str],
  tmp_dir: Path,
  width: int,
  quality: int,
  sleep_seconds: float,
) -> None:
  dest_dir.mkdir(parents=True, exist_ok=True)
  tmp_dir.mkdir(parents=True, exist_ok=True)

  for slot in slot_ids:
    title = _marseille_commons_title(slot)
    tmp = tmp_dir / title.replace(' ', '_')
    if not tmp.exists():
      upload_url = _commons_upload_url(tmp.name)
      _download_url(upload_url, tmp)
      time.sleep(sleep_seconds)
    _resize_to_jpeg(
      src=tmp,
      dest=dest_dir / f'{slot}.jpg',
      width=width,
      quality=quality,
    )

  shutil.copyfile(dest_dir / 'major_fool.jpg', dest_dir / 'cover.jpg')


def main() -> int:
  parser = argparse.ArgumentParser(description='Build tarot deck assets (tarot-sounds).')
  parser.add_argument('--all', action='store_true', help='Build all supported decks.')
  parser.add_argument('--rws', action='store_true', help='Build rws_1909 deck.')
  parser.add_argument('--marseille', action='store_true', help='Build marseille_bnf deck.')
  parser.add_argument('--width', type=int, default=320, help='Target width for downloaded decks.')
  parser.add_argument('--quality', type=int, default=80, help='JPEG quality (1-95).')
  parser.add_argument(
    '--sleep',
    type=float,
    default=1.0,
    help='Seconds to sleep between Wikimedia downloads (polite crawling).',
  )
  args = parser.parse_args()

  build_rws = args.all or args.rws
  build_marseille = args.all or args.marseille

  if not build_rws and not build_marseille:
    parser.error('No deck selected. Use --all or --rws/--marseille.')

  root = _repo_root()
  slot_ids = _load_slot_ids(root / 'flutter/lib/data/tarot_deck_schema.dart')

  if build_rws:
    build_rws_1909(
      src_dir=root / 'tarot-sounds/assets/cards',
      dest_dir=root / 'tarot-sounds/assets/cards/v1/rws_1909',
      slot_ids=slot_ids,
    )

  if build_marseille:
    build_marseille_bnf(
      dest_dir=root / 'tarot-sounds/assets/cards/v1/marseille_bnf',
      slot_ids=slot_ids,
      tmp_dir=root / '.tmp/marseille_bnf_sources',
      width=args.width,
      quality=args.quality,
      sleep_seconds=args.sleep,
    )

  return 0


if __name__ == '__main__':
  raise SystemExit(main())
