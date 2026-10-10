# Credits

## No third-party code

Every line in `tools/` was written for this project: roughly 9,700 lines across 34 files.
Nothing is vendored, adapted or copied. The only imports are the Python standard library
plus **capstone** in one file.

This is stated precisely because it matters for licensing. **xoreos is GPLv3**, and had
any of its code been reused, this project would have to be GPLv3 too. It was not.

To be exact rather than flattering: xoreos' own source was **read as a reference** while
implementing GFF4 — reading `gff4file.cpp` beforehand rather than guessing at bytes is
recorded in the log for 2026-10-05. What came out of that is original code written against
this game's files, structured differently and covering a different subset. Nothing was
copied, adapted or translated, and a file format is not itself copyrightable. But
"consulted the reference implementation" is the honest description, not "clean-room".

What follows is therefore credit for **knowledge**, which is owed regardless.

## Knowledge this project is built on

### xoreos / xoreos-tools — the big one

- <https://github.com/xoreos/xoreos> · <https://github.com/xoreos/xoreos-tools> · <https://wiki.xoreos.org/>

The xoreos project reverse-engineered BioWare's Aurora engine family, and their work is
why this project knew that a Sonic game would contain GFF4 structures, TLK string tables,
GDA/2DA tables and an ERF-family archive at all. Their three-part blog series on Sonic
Chronicles specifically — *"The Odd One Out"*, [part 1][x1], [part 2][x2], [part 3][x3] —
pointed at the formats, the `.small` compression wrapper and the Nintendo DS graphics
containers.

Two observations from their wiki saved real time. That Sonic Chronicles "doesn't seem to
use any scripts at all" turned out to be the single most important structural fact about
modding this game, and it was years old before this project started. And their note that
the game renders with an orthogonal projection explained area geometry that would
otherwise have been confusing.

xoreos is licensed GPLv3. No xoreos code is present here.

[x1]: https://xoreos.org/blog/2015/06/05/the-odd-one-out-sonic-chronicles-1-slash-3/
[x2]: https://xoreos.org/blog/2015/06/06/the-odd-one-out-sonic-chronicles-2-slash-3/
[x3]: https://xoreos.org/blog/2015/06/07/the-odd-one-out-sonic-chronicles-3-slash-3/

### ChroniclesDX

- <https://github.com/DS-Homebrew/ChroniclesDX>

An existing fan mod of this same game, taking a different approach: RomFS injection
(overriding files at load time) rather than rebuilding the ROM. Nothing from it is used
here, but it is the prior art in this space and deserves the credit for being first.
Its documentation that `.axi` cutscene files cannot currently be edited saved this project
from rediscovering that the hard way.

### Tools and references

- **DeSmuME** — <https://desmume.org/> — the emulator every in-game result here was
  confirmed on. Version 0.9.11 specifically; newer builds have reported issues with this
  game.
- **melonDS** — <https://github.com/melonDS-emu/melonDS> — for its GDB stub, which is the
  route to the ARM9 questions still open.
- **capstone** — <https://www.capstone-engine.org/> — BSD-3-Clause. The only runtime
  dependency, used solely by `tools/recon/disasm.py`. Everything else is standard library.
- **No-Intro** — ROM cataloguing. The EU dump is catalogue #2699, which is how "is this a
  known-good dump" was answered in Phase 0.
- **NitroPacker** (<https://github.com/haroohie-club/NitroPacker>) and **ndstool**
  (<https://github.com/blocksds/ndstool>) — surveyed as prior art for NDS ROM
  rebuilding. Not used; this project rebuilds the filesystem itself, but they were the
  reference points for what the job involves.
- The community **Action Replay** code lists, whose US game ID `YWSE-ACB0DF12` served as
  an independent cross-check on the dumps during reconnaissance.
- **Chao Island** — <https://chao-island.com/guides/spin-off-games/sonic-chronicles/> —
  a fan guide whose per-level Chao figures were used as external data to work out that
  the game's code-driven Chao scale with level even though `Chaos.GDA` holds no numbers
  for them, and to confirm that Ferox is unaffected by level. No content is reproduced
  here; the findings it supported are recorded in the log for 2026-10-10.

## Trademarks

Sonic Chronicles: The Dark Brotherhood is the property of SEGA and was developed by
BioWare. This project is unaffiliated with either, contains no game assets, and ships no
ROM.
