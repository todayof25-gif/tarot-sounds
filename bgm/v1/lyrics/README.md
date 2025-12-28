# BGM Lyrics (HelloTarot)

Add lyrics files here to enable in-app lyrics.

## Naming
- Recommended (synced): `<trackId>.lrc`
- Fallback (plain text): `<trackId>.txt`

`trackId` is the `id` field in `../manifest.json`.

## LRC example
```lrc
[00:00.00] (Intro)
[00:12.50] First line...
[00:28.10] Next line...
```

After commit + push, the app will load:
- `https://www.aeipet.com/bgm/v1/lyrics/<trackId>.lrc`
- or `https://www.aeipet.com/bgm/v1/lyrics/<trackId>.txt`

