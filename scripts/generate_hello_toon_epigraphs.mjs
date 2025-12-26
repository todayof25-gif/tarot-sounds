#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';

const SUPPORTED_LOCALES = ['kr', 'en', 'ja'];

function usage() {
  return `\
Usage:
  GEMINI_API_KEY=... node scripts/generate_hello_toon_epigraphs.mjs [--manifest <path>] [--dry-run]

Defaults:
  --manifest hello-toon/v1/manifest.json
  model: gemini-2.5-flash-lite (override with GEMINI_MODEL)

Notes:
  - Fills missing epigraphs for locales: ${SUPPORTED_LOCALES.join(', ')}
  - Writes epigraphs into manifest.json (server-fixed, shared by all users).
`;
}

function parseArgs(argv) {
  const args = { manifest: 'hello-toon/v1/manifest.json', dryRun: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--help' || a === '-h') args.help = true;
    else if (a === '--dry-run') args.dryRun = true;
    else if (a === '--manifest') {
      const v = argv[++i];
      if (!v) throw new Error('Missing value for --manifest');
      args.manifest = v;
    } else {
      throw new Error(`Unknown arg: ${a}`);
    }
  }
  return args;
}

function languageLabel(locale) {
  switch (locale) {
    case 'kr':
      return 'Korean';
    case 'en':
      return 'English';
    case 'ja':
      return 'Japanese';
    default:
      return 'English';
  }
}

function normalizeEpigraph(raw) {
  let line = String(raw ?? '').trim();
  if (!line) return null;

  line = line.split(/[\r\n]+/g)[0].trim();
  line = line.replace(/^[-•\s]+/g, '').trim();

  // Strip quotes.
  line = line.replace(/^["“”'‘’]+/g, '').replace(/["“”'‘’]+$/g, '').trim();

  // Strip leading/trailing ellipses.
  line = line.replace(/^(?:\.\.\.|…)+\s*/g, '');
  line = line.replace(/\s*(?:\.\.\.|…)+$/g, '');

  // Collapse whitespace.
  line = line.replace(/\s+/g, ' ').trim();

  if (!line) return null;
  if (line.length > 120) return null;
  return line;
}

async function generateWithGemini({ apiKey, modelId, systemInstruction, prompt }) {
  const modelPath = modelId.startsWith('models/') ? modelId : `models/${modelId}`;
  const url = `https://generativelanguage.googleapis.com/v1beta/${modelPath}:generateContent`;

  const body = {
    model: modelPath,
    systemInstruction: { role: 'system', parts: [{ text: systemInstruction }] },
    generationConfig: { temperature: 0.7 },
    contents: [{ role: 'user', parts: [{ text: prompt }] }],
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-goog-api-key': apiKey,
    },
    body: JSON.stringify(body),
  });

  const json = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = json?.error?.message || `HTTP ${res.status}`;
    throw new Error(`Gemini error: ${msg}`);
  }

  const parts = json?.candidates?.[0]?.content?.parts;
  if (!Array.isArray(parts) || parts.length === 0) return null;
  const text = parts
    .map((p) => (typeof p?.text === 'string' ? p.text : ''))
    .join('')
    .trim();
  return text || null;
}

function buildPrompt({ locale, toon, episode }) {
  const language = languageLabel(locale);
  const title = toon?.titles?.[locale] ?? toon?.titles?.en ?? toon?.id ?? '';
  const description =
    toon?.descriptions?.[locale] ?? toon?.descriptions?.en ?? '';
  const episodeTitle =
    episode?.titles?.[locale] ?? episode?.titles?.en ?? episode?.id ?? '';

  return `\
Language: ${language}

Context:
- Series title: ${title}
- Series genre: ${toon?.genre ?? ''}
- Series description: ${description}
- Episode title: ${episodeTitle}

TASK:
Write ONE short epigraph sentence for this episode.

STYLE:
- Tarot / fortune vibe, calm and elegant.
- Avoid clichés and generic motivational quotes.
- Do NOT include the series title or episode title verbatim.

FORMAT (STRICT):
- Exactly one sentence, one line.
- Output ONLY the sentence. No extra labels.
- No quotes, no surrounding ellipses, no emojis, no hashtags.
- Keep it concise (about <= 12 words, or <= 45 characters).
`;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    console.log(usage());
    process.exit(0);
  }

  const apiKey = process.env.GEMINI_API_KEY?.trim();
  if (!apiKey) {
    console.error('[error] GEMINI_API_KEY is required.');
    console.error(usage());
    process.exit(1);
  }

  const modelId = (process.env.GEMINI_MODEL || 'gemini-2.5-flash-lite').trim();
  const manifestPath = path.resolve(process.cwd(), args.manifest);

  const raw = await fs.readFile(manifestPath, 'utf8');
  const manifest = JSON.parse(raw);

  const toons = Array.isArray(manifest?.toons) ? manifest.toons : [];
  let changed = false;

  const systemInstruction = `\
You write short poetic epigraph lines for a tarot-themed webtoon viewer.

CRITICAL OUTPUT RULES:
- Output ONLY the epigraph sentence (user-visible plain text).
- Exactly one line. No newlines.
- No quotes, no surrounding ellipses, no emojis, no hashtags.
- Always respond in the requested language.
`;

  for (const toon of toons) {
    const episodes = Array.isArray(toon?.episodes) ? toon.episodes : [];
    for (const episode of episodes) {
      if (typeof episode !== 'object' || episode == null) continue;
      episode.epigraphs ??= {};

      for (const locale of SUPPORTED_LOCALES) {
        const current = String(episode.epigraphs?.[locale] ?? '').trim();
        if (current) continue;

        const prompt = buildPrompt({ locale, toon, episode });
        console.log(
          `[gen] toon=${toon.id} episode=${episode.id} locale=${locale} model=${modelId}`,
        );

        const text = await generateWithGemini({
          apiKey,
          modelId,
          systemInstruction,
          prompt,
        });

        const normalized = normalizeEpigraph(text);
        if (!normalized) {
          console.warn(
            `[warn] empty/invalid output (toon=${toon.id} episode=${episode.id} locale=${locale})`,
          );
          continue;
        }

        episode.epigraphs[locale] = normalized;
        changed = true;
      }
    }
  }

  if (!changed) {
    console.log('[ok] No missing epigraphs.');
    return;
  }

  const out = JSON.stringify(manifest, null, 2) + '\n';
  if (args.dryRun) {
    console.log('[dry-run] Would write updated manifest.');
    return;
  }

  await fs.writeFile(manifestPath, out, 'utf8');
  console.log('[ok] Updated manifest:', path.relative(process.cwd(), manifestPath));
}

main().catch((err) => {
  console.error('[fatal]', err?.message || err);
  process.exit(1);
});
