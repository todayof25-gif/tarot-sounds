#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Locale = Literal["kr", "en", "ja"]


@dataclass(frozen=True)
class ChapterSource:
    locale: Locale
    episode_number: int
    path: Path


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _strip_markdown_bold(line: str) -> str:
    s = line.strip()
    if len(s) >= 4 and s.startswith("**") and s.endswith("**"):
        return s[2:-2].strip()
    if len(s) >= 2 and s.startswith("*") and s.endswith("*"):
        return s[1:-1].strip()
    return s


def _looks_like_chapter_title(line: str) -> bool:
    s = _strip_markdown_bold(line).strip()
    if not s:
        return False
    if re.search(r"(?i)\bepisode\b", s):
        return True
    if re.search(r"(?i)\bside\s*story\b", s):
        return True
    if re.search(r"\bEP\.\s*\d+", s):
        return True
    if re.match(r"^제\s*\d+", s) or re.match(r"^제\s*[.:：\-]", s):
        return True
    if re.match(r"^第\s*\d+\s*話", s):
        return True
    return False


def _extract_title_and_body(text: str) -> tuple[str, str]:
    lines = text.split("\n")
    non_empty = [i for i, line in enumerate(lines) if line.strip()]
    if not non_empty:
        return "", ""

    first_i = non_empty[0]
    first = lines[first_i]
    second_i = non_empty[1] if len(non_empty) > 1 else None
    second = lines[second_i] if second_i is not None else ""

    if second_i is not None and not _looks_like_chapter_title(first) and _looks_like_chapter_title(second):
        title_line = second
        body_start = second_i + 1
    else:
        title_line = first
        body_start = first_i + 1

    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1

    body = "\n".join(lines[body_start:]).lstrip("\n")
    if body and not body.endswith("\n"):
        body += "\n"

    return title_line.strip(), body


def _normalize_title_for_manifest(*, series_id: str, locale: Locale, raw_title: str) -> str:
    title = _strip_markdown_bold(raw_title).strip()
    if not title:
        return ""

    if series_id == "today_fortune_cat":
        return title

    if locale == "en":
        title = re.sub(r"(?i)^episode\s*\d+\s*[.:：\-]\s*", "", title).strip()
        return title
    if locale == "kr":
        title = re.sub(r"^제\s*\d+\s*화\s*[.:：\-]?\s*", "", title).strip()
        title = re.sub(r"^제\s*[.:：\-]\s*", "", title).strip()
        return title
    if locale == "ja":
        title = re.sub(r"^第\s*\d+\s*話\s*[.:：\-]?\s*", "", title).strip()
        return title
    return title


def _convert_cover(*, src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "convert",
            str(src),
            "-resize",
            "720x",
            "-strip",
            "-quality",
            "90",
            str(dest),
        ],
        check=True,
    )


def _collect_numbered_files(*, directory: Path, pattern: re.Pattern[str]) -> dict[int, Path]:
    mapping: dict[int, Path] = {}
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        match = pattern.match(entry.name)
        if not match:
            continue
        number = int(match.group(1))
        mapping[number] = entry
    return mapping


def _sync_today_fortune_cat(*, webnovels_root: Path, tanovel_root: Path, manifest: dict) -> None:
    src_root = webnovels_root / "03_Today_Fortune_Cat"
    out_root = tanovel_root / "series" / "today_fortune_cat"

    covers = {
        "kr": src_root / "00.jpg",
        "en": src_root / "00.en.jpg",
        "ja": src_root / "00.ja.jpg",
    }
    for locale, cover_src in covers.items():
        _convert_cover(
            src=cover_src,
            dest=out_root / locale / "cover_720.webp",
        )

    drafts = {
        "kr": src_root / "Drafts.kr",
        "en": src_root / "Drafts.en",
        "ja": src_root / "Drafts.ja",
    }

    main_patterns: dict[Locale, re.Pattern[str]] = {
        "kr": re.compile(r"^(\d+)_.*\.txt$"),
        "en": re.compile(r"^Today_Fortune_Cat_Ep(\d+)_EN\.txt$"),
        "ja": re.compile(r"^Today_Fortune_Cat_Ep(\d+)_JA\.txt$"),
    }
    side_patterns: dict[Locale, re.Pattern[str]] = {
        "kr": re.compile(r"^SideStory_(\d+)_.*\.txt$"),
        "en": re.compile(r"^Today_Fortune_Cat_SideStory_(\d+)_EN\.txt$"),
        "ja": re.compile(r"^Today_Fortune_Cat_SideStory_(\d+)_JA\.txt$"),
    }

    main_files_by_locale = {
        locale: _collect_numbered_files(directory=dir_path, pattern=main_patterns[locale])
        for locale, dir_path in drafts.items()
    }
    side_files_by_locale = {
        locale: _collect_numbered_files(directory=dir_path, pattern=side_patterns[locale])
        for locale, dir_path in drafts.items()
    }

    for locale in ("kr", "en", "ja"):
        if len(main_files_by_locale[locale]) != 30:
            raise RuntimeError(f"today_fortune_cat main({locale}) expected 30 files, got {len(main_files_by_locale[locale])}")
        if len(side_files_by_locale[locale]) != 20:
            raise RuntimeError(f"today_fortune_cat side({locale}) expected 20 files, got {len(side_files_by_locale[locale])}")

    chapters_out = {
        "kr": out_root / "chapters" / "kr",
        "en": out_root / "chapters" / "en",
        "ja": out_root / "chapters" / "ja",
    }
    for p in chapters_out.values():
        p.mkdir(parents=True, exist_ok=True)

    chapters_manifest: list[dict] = []
    date = "2026.01.01"

    def write_chapter(*, ch_number: int, files_by_locale: dict[Locale, Path]) -> dict[str, str]:
        titles: dict[str, str] = {}
        for locale in ("kr", "en", "ja"):
            src_path = files_by_locale[locale]
            title, body = _extract_title_and_body(_read_text(src_path))
            titles[locale] = _normalize_title_for_manifest(
                series_id="today_fortune_cat",
                locale=locale,
                raw_title=title,
            )
            (chapters_out[locale] / f"ch{ch_number:02d}.txt").write_text(body, encoding="utf-8", newline="\n")
        return titles

    for episode in range(1, 31):
        ch_number = episode
        titles = write_chapter(
            ch_number=ch_number,
            files_by_locale={locale: main_files_by_locale[locale][episode] for locale in ("kr", "en", "ja")},
        )
        chapters_manifest.append({"id": f"ch{ch_number:02d}", "date": date, "titles": titles})

    for side_episode in range(1, 21):
        ch_number = 30 + side_episode
        titles = write_chapter(
            ch_number=ch_number,
            files_by_locale={locale: side_files_by_locale[locale][side_episode] for locale in ("kr", "en", "ja")},
        )
        chapters_manifest.append({"id": f"ch{ch_number:02d}", "date": date, "titles": titles})

    new_series = {
        "id": "today_fortune_cat",
        "isNew": True,
        "isUp": True,
        "authors": {"kr": "HelloTarot", "en": "HelloTarot", "ja": "HelloTarot"},
        "genres": {"kr": "#힐링로맨스", "en": "#HealingRomance", "ja": "#癒しロマンス"},
        "titles": {"kr": "오늘의 운세 냥이", "en": "Today's Fortune Cat", "ja": "今日の運勢ニャン"},
        "descriptions": {
            "kr": "집사야, 츄르를 바치면 너의 운명을 알려주마! 신비한 냥이 ‘묘르신’이 점쳐주는 기막힌 하루하루!",
            "en": "Human, offer up Churu and I shall tell your fate! A mysterious cat, Myoreusin, predicts your day—one chaotic fortune at a time.",
            "ja": "下僕よ、ちゅ〜るを捧げれば運命を教えてやるニャ！不思議な猫「ミョルシン」が占う、波乱だらけの毎日。",
        },
        "chapters": chapters_manifest,
    }

    series_list = manifest.get("series")
    if not isinstance(series_list, list):
        raise RuntimeError("manifest.series must be a list")

    for i, s in enumerate(series_list):
        if isinstance(s, dict) and s.get("id") == "today_fortune_cat":
            series_list[i] = new_series
            break
    else:
        series_list.append(new_series)


def _sync_direction_of_love(*, webnovels_root: Path, tanovel_root: Path, manifest: dict) -> None:
    src_root = webnovels_root / "01_The_Direction_of_Love"
    out_root = tanovel_root / "series" / "direction_of_love"

    covers = {
        "kr": src_root / "00.jpg",
        "en": src_root / "00.en.jpg",
        "ja": src_root / "00.ja.jpg",
    }
    for locale, cover_src in covers.items():
        _convert_cover(src=cover_src, dest=out_root / locale / "cover_720.webp")

    drafts = {
        "kr": src_root / "Drafts.kr",
        "en": src_root / "Drafts.en",
        "ja": src_root / "Drafts.ja",
    }
    patterns: dict[Locale, re.Pattern[str]] = {
        "kr": re.compile(r"^연애의_정방향_(\d+)화(?:_완)?\.txt$"),
        "en": re.compile(r"^The_Direction_of_Love_Ep(\d+)\.txt$"),
        "ja": re.compile(r"^The_Direction_of_Love_Ep(\d+)_JA\.txt$"),
    }

    files_by_locale = {
        locale: _collect_numbered_files(directory=dir_path, pattern=patterns[locale])
        for locale, dir_path in drafts.items()
    }
    for locale in ("kr", "en", "ja"):
        if len(files_by_locale[locale]) != 30:
            raise RuntimeError(f"direction_of_love({locale}) expected 30 files, got {len(files_by_locale[locale])}")

    chapters_out = {
        "kr": out_root / "chapters" / "kr",
        "en": out_root / "chapters" / "en",
        "ja": out_root / "chapters" / "ja",
    }
    for p in chapters_out.values():
        p.mkdir(parents=True, exist_ok=True)

    titles_by_chid: dict[str, dict[str, str]] = {}
    for episode in range(1, 31):
        ch_id = f"ch{episode:02d}"
        titles_by_chid[ch_id] = {}
        for locale in ("kr", "en", "ja"):
            src_path = files_by_locale[locale][episode]
            title, body = _extract_title_and_body(_read_text(src_path))
            titles_by_chid[ch_id][locale] = _normalize_title_for_manifest(
                series_id="direction_of_love",
                locale=locale,
                raw_title=title,
            )
            (chapters_out[locale] / f"{ch_id}.txt").write_text(body, encoding="utf-8", newline="\n")

    series_list = manifest.get("series")
    if not isinstance(series_list, list):
        raise RuntimeError("manifest.series must be a list")

    series = next((s for s in series_list if isinstance(s, dict) and s.get("id") == "direction_of_love"), None)
    if not isinstance(series, dict):
        raise RuntimeError("direction_of_love series not found in manifest")

    chapters = series.get("chapters")
    if not isinstance(chapters, list):
        raise RuntimeError("direction_of_love.chapters must be a list")

    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        ch_id = chapter.get("id")
        if not isinstance(ch_id, str):
            continue
        titles = titles_by_chid.get(ch_id)
        if not titles:
            continue
        titles_obj = chapter.get("titles")
        if not isinstance(titles_obj, dict):
            titles_obj = {}
            chapter["titles"] = titles_obj
        titles_obj["en"] = titles["en"]
        titles_obj["ja"] = titles["ja"]


def _sync_midnight_counseling(*, webnovels_root: Path, tanovel_root: Path, manifest: dict) -> None:
    src_root = webnovels_root / "02_Midnight_Counseling"
    out_root = tanovel_root / "series" / "midnight_counseling"

    covers = {
        "kr": src_root / "00.jpg",
        "en": src_root / "00.en.jpg",
        "ja": src_root / "00.ja.jpg",
    }
    for locale, cover_src in covers.items():
        _convert_cover(src=cover_src, dest=out_root / locale / "cover_720.webp")

    drafts = {
        "kr": src_root / "Drafts.kr",
        "en": src_root / "Drafts.en",
        "ja": src_root / "Drafts.ja",
    }
    patterns: dict[Locale, re.Pattern[str]] = {
        "kr": re.compile(r"^밤_12시의_상담소_(\d+)화\.txt$"),
        "en": re.compile(r"^Midnight_Counseling_Ep(\d+)_EN\.txt$"),
        "ja": re.compile(r"^Midnight_Counseling_Ep(\d+)_JA\.txt$"),
    }

    files_by_locale = {
        locale: _collect_numbered_files(directory=dir_path, pattern=patterns[locale])
        for locale, dir_path in drafts.items()
    }
    for locale in ("kr", "en", "ja"):
        if len(files_by_locale[locale]) != 30:
            raise RuntimeError(f"midnight_counseling({locale}) expected 30 files, got {len(files_by_locale[locale])}")

    chapters_out = {
        "kr": out_root / "chapters" / "kr",
        "en": out_root / "chapters" / "en",
        "ja": out_root / "chapters" / "ja",
    }
    for p in chapters_out.values():
        p.mkdir(parents=True, exist_ok=True)

    titles_by_chid: dict[str, dict[str, str]] = {}
    for episode in range(1, 31):
        ch_id = f"ch{episode:02d}"
        titles_by_chid[ch_id] = {}
        for locale in ("kr", "en", "ja"):
            src_path = files_by_locale[locale][episode]
            title, body = _extract_title_and_body(_read_text(src_path))
            titles_by_chid[ch_id][locale] = _normalize_title_for_manifest(
                series_id="midnight_counseling",
                locale=locale,
                raw_title=title,
            )
            (chapters_out[locale] / f"{ch_id}.txt").write_text(body, encoding="utf-8", newline="\n")

    series_list = manifest.get("series")
    if not isinstance(series_list, list):
        raise RuntimeError("manifest.series must be a list")

    series = next((s for s in series_list if isinstance(s, dict) and s.get("id") == "midnight_counseling"), None)
    if not isinstance(series, dict):
        raise RuntimeError("midnight_counseling series not found in manifest")

    series["titles"] = {
        "kr": "밤 12시의 상담소",
        "en": "Midnight Counseling",
        "ja": "深夜12時の相談所",
    }
    series["genres"] = {
        "kr": "#힐링/미스터리",
        "en": "#Healing/Mystery",
        "ja": "#癒し/ミステリー",
    }
    series["descriptions"] = {
        "kr": "당신의 악몽을 팝니다. 밤 12시, 세상에서 가장 수상하고 따뜻한 상담소가 문을 엽니다.",
        "en": "We buy your nightmares. At midnight, the warmest—and most suspicious—counseling office in the world opens its doors.",
        "ja": "あなたの悪夢を買い取ります。深夜12時、世界で一番怪しくて温かい相談所が開きます。",
    }

    chapters = series.get("chapters")
    if not isinstance(chapters, list):
        raise RuntimeError("midnight_counseling.chapters must be a list")

    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        ch_id = chapter.get("id")
        if not isinstance(ch_id, str):
            continue
        titles = titles_by_chid.get(ch_id)
        if not titles:
            continue
        titles_obj = chapter.get("titles")
        if not isinstance(titles_obj, dict):
            titles_obj = {}
            chapter["titles"] = titles_obj
        titles_obj["en"] = titles["en"]
        titles_obj["ja"] = titles["ja"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync tanovel CDN assets from WebNovels sources.")
    parser.add_argument(
        "--src",
        required=True,
        type=Path,
        help="WebNovels root directory (e.g. /mnt/c/Users/JOON/Desktop/HelloTarot-IP/WebNovels)",
    )
    parser.add_argument(
        "--series",
        action="append",
        choices=["direction_of_love", "midnight_counseling", "today_fortune_cat"],
        help="Series to sync (repeatable). If omitted, sync all supported series.",
    )

    args = parser.parse_args()
    webnovels_root: Path = args.src

    tarot_sounds_root = Path(__file__).resolve().parents[1]
    tanovel_root = tarot_sounds_root / "tanovel" / "v1"
    manifest_path = tanovel_root / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    requested = set(args.series or ["direction_of_love", "midnight_counseling", "today_fortune_cat"])
    if "direction_of_love" in requested:
        _sync_direction_of_love(webnovels_root=webnovels_root, tanovel_root=tanovel_root, manifest=manifest)
    if "midnight_counseling" in requested:
        _sync_midnight_counseling(webnovels_root=webnovels_root, tanovel_root=tanovel_root, manifest=manifest)
    if "today_fortune_cat" in requested:
        _sync_today_fortune_cat(webnovels_root=webnovels_root, tanovel_root=tanovel_root, manifest=manifest)

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
