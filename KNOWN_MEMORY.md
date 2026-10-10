# Known Memory

Confirmed RAM addresses and layout. Per the project's development rules, nothing goes in this file without evidence and a confidence level — this file currently holds **zero addresses we've confirmed ourselves**. What follows is community-sourced and explicitly unverified; treat it as a lead to test, not a fact to build on.

## Community-sourced Action Replay addresses (US, game ID `YWSE-ACB0DF12`) — UNVERIFIED

Source: [Kodewerx AR code thread](https://www.kodewerx.org/forum/viewtopic.php?f=16&t=6169&p=69131) (a second related thread at `f=19&t=7383` has not been reviewed yet). Found during the external-research pass (see [RESEARCH.md](RESEARCH.md)), **not** confirmed against our own ROM/emulator session.

| Address (US) | Claimed meaning | Confidence |
|---|---|---|
| `02237520` | Sonic current HP (32-bit) | unverified |
| `02238720` | Amy current HP (32-bit) | unverified |
| `0223A2C0` | Rouge current HP (32-bit) | unverified |
| `02239380` | Tails current HP (32-bit) | unverified |
| `022262F4` | Rings count (32-bit) | unverified |
| `222264CF` (note: 7 hex digits as posted — likely a typo for an 8-digit address, needs rechecking against the source) | Chao-related, used in a "max Chao level / lots of eggs" multi-line AR code | unverified, address itself is suspect |

These are **US-region only** as posted; EU addresses will very likely differ and have not been looked for at all.

## How to confirm an address ourselves

Per the project's development rules reverse-engineering process: don't assume a community address is right just because a code "seems to work" for someone else. Confirm via:
1. melonDS's GDB stub (ARM9 port 3333, ARM7 port 3334 — see `RESEARCH.md`) for live memory inspection while the game runs, using our own DeSmuME-verified save/state as a starting point, **or**
2. DeSmuME's own RAM search / memory viewer (same emulator we're already using for playtesting) as a lower-setup-cost first pass, before reaching for melonDS+GDB.

No such confirmation session has happened yet this project.

## Not yet known

Everything: level cap constant, XP/level tables, stat growth formulas, POW/ability resource costs, enemy scaling formulas, Chao data layout, party/recruitment flags, save-file field layout.

## Save file (`.dsv`) — first confirmed offsets

**Confidence: high** — located by diffing a pristine save (Shadow level 19) against the same save after levelling him to 30 in game. Only 98 bytes differed across 24 regions, which made the character record easy to isolate. EU ROM, DeSmuME `.dsv` (65,658 bytes, including DeSmuME's own trailing footer).

**Shadow's character record** (all values are `uint32` little-endian):

| Offset | Field | lv19 -> lv30 |
|---|---|---|
| `0x0263D` | speed (base **+ allocated bonus points**) | 51 -> 74 |
| `0x02641` | attack | 43 -> 64 |
| `0x02645` | defense | 45 -> 61 |
| `0x02649` | HP | 333 -> 518 |
| `0x0264D` | power (POW) | 41 -> 59 |
| `0x02651` | grit (GRT) | 30 -> 46 |
| `0x02655` | luck (base + bonus points) | 30 -> 42 |
| `0x02661` | PP / fatigue | 15 -> 21 |
| `0x026B9` | **level** | 19 -> 30 |
| `0x026E1` | **movement ability slot 1 level** (Dash) | 2 (unchanged) |
| `0x026E5` | **movement ability slot 2 level** (Teleport) | 1 (unchanged) |
| `0x025A9` | a second HP copy (current vs max?) | 333 -> 518 |

Stats match `Adv_Shadow.GDA` base values exactly for attack/defense/hp/power/grit, while speed and luck are stored as **base + allocated bonus points** — which independently confirms that the displayed-stat model is `table + bonus points + equipment`, with equipment applied at display time rather than stored.

**This resolves why table edits could not change Dash II:** the movement-ability level is **persistent per-character save state**, not recomputed from `Adv_<char>.GDA` on level-up. Shadow levelled 19 -> 30 with the edited table and slot 1 stayed at 2.

A refined hypothesis, **not yet tested**: the engine may grant an upgrade only at the *transition* level where the table value increases. The edited curve raised Dash to 3 from level 8, but Shadow was already past 8, so no transition was ever crossed. That would make the table meaningful only at the moment it steps up.

### The save is validated — direct editing is blocked

**Tested and failed (confidence: high).** Writing `0x026E1` from 2 to 3 — a **single byte** — caused the game to **reject and wipe the save slot** on load: level read back as 0 and ~3,096 bytes across 130 regions were cleared. The rest of the 64 KB file survived, so validation and clearing appear to be **per slot**, not whole-file.

**Consequence: the save carries a checksum or integrity field, and no save edit will work until it is identified.** This also blocks using a save edit to test the ability-level hypothesis.

**What was ruled out** (so nobody repeats it): the two random-looking 4-byte fields that differ between valid saves, at `0x203` and `0x234`, do **not** match CRC32 or a byte sum over any contiguous range starting `0x200`–`0x700` and ending up to `0x9000` (scanned at 4-byte start / 64-byte end granularity, requiring both sample saves to match). So it is not a plain CRC32 over an obvious span. Candidates remaining: a BioWare-custom algorithm, a CRC variant with non-standard polynomial/init, a non-contiguous range, or those fields being something else entirely.

Note `0x244` is probably **not** a checksum: it increments (`0x375421` -> `0x376927`) and looks like play time or a frame counter.

**No data was lost in the experiment** — the pristine save was never touched, and the level-30 playthrough was restored from a backup taken before the edit. The game-wiped file is preserved as `sonic_chronicles_dash3b.dsv.game-wiped-evidence` for anyone analysing the clearing pattern.

**Better route to testing the ability-level field:** edit the value in **live RAM** rather than the save, via DeSmuME's RAM search / cheat system (or melonDS + GDB). The game loads the save into memory and validates on load, so a RAM poke sidesteps the checksum entirely.

**Caveat:** these offsets are for this particular save. Whether the record is at a fixed address or depends on party composition/slot order is unknown — other characters' records have not been located, so the per-character stride is not yet established.

### Checksum hunt — what has been ruled out

Four systematic attempts, **no crack yet**. Recorded so the next attempt starts where this one stopped rather than repeating it.

**Save layout established:**
- bytes `0x004`–`0x1FF` are all `0xFF` (erased flash); **real save data begins at `0x200`** with ASCII magic `"VB"` — the same magic as the leftover `SaveTest1.sav` inside the ROM, which is therefore a usable reference sample.
- fields are **byte-packed, not 4-aligned** (the checksum candidates sit at `0x203` and `0x234`).

**Field roles identified:**

| Offset | Role |
|---|---|
| `0x203` (u32) | checksum candidate — high entropy, changes between valid saves |
| `0x234` (u32) | second checksum candidate, same character |
| `0x244`, `0x253` | **counters, not checksums** — monotonically increasing (play time / timestamp) |
| `0x55C` | a counter, 2 → 3 across one save (save count?) |
| `0xEA8`, `0xEBC` | further counters/timestamps |

**Ruled out** (both sample saves required to match, candidate field both zeroed and left intact):
- **CRC32** in all four init/final-xor conventions (`std`, no-final-xor, init-0, init-0 + xor), over every contiguous range with start on any byte offset `0x200`–`0x600`, and every 4-aligned start `0x000`–`0x2000`, ending anywhere up to `0x10000` at 32–64 byte granularity.
- **32-bit additive sum** over the same space.

**The strongest remaining lead:** the standard reflected CRC32 polynomial `0xEDB88320` occurs **exactly once** in the ARM9 binary, at RAM `0x020B7C34`. The game therefore does contain CRC32 code. Since a plain CRC32 over a contiguous span does not reproduce either field, the checksum is likely computed over a **non-contiguous region** (e.g. skipping the header or the counters), or over a transformed buffer, or the stored value is derived from the CRC rather than being it.

**Recommended next step:** disassemble around `0x020B7C34` in Ghidra to find the caller and the exact buffer/length it is given. That is a static-analysis task rather than a search problem, and it would settle the range in one go. Until then **save editing remains blocked** — a single changed byte causes the game to wipe the slot.

---

## SAVE CHECKSUM CRACKED (2026-10-05)

Recovered by **disassembling the ARM9 CRC routine**, after four brute-force search attempts had failed. Verified against two independent valid saves.

### The algorithm

`crc32` lives at RAM **`0x020B7C38`**, with its 256-entry table built at runtime by **`0x020B7C00`** (reflected polynomial `0xEDB88320`, table stored at RAM `0x021AD594`).

The routine is **not** the usual convention — disassembly shows `crc = 0` on entry and the value returned unmodified:

> **init = 0, no final XOR**, reflected poly `0xEDB88320`

In Python: `zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF`.

### The two checksums

The caller at `0x02017558` does `r0 = buf + 7`, `r1 = <length>`, calls crc32, then stores the four result bytes to `buf+3`. With save data beginning at `0x200`:

| | Stored at | Covers | Length |
|---|---|---|---|
| **outer** | `0x203` | `0x207` … | `0x3BF9` (15353) |
| **inner** | `0x234` | `0x238` … | `0x21` (33) |

The inner region sits **inside** the outer one, so **the inner checksum must be recomputed first** — otherwise the outer is computed over stale bytes.

Both verified exactly against the pristine save and the levelled save.

**Why the earlier searches missed it:** the outer length `0x3BF9` is **odd**, and the scans stepped the range end in 32- and 64-byte increments, so that end was never tested. The algorithm guess (`init 0, no final xor`) had actually been correct all along.

### Tooling

[tools/build/save_edit.py](tools/build/save_edit.py) reads a `.dsv`, reports both checksums and the known fields, applies `--set <hex_offset>=<value>` edits, reseals both checksums in the right order, and **refuses to write if the result does not validate**. It backs up the original on first write.

**Save editing is now unblocked**, which also removes the obstacle in front of Phase 13 (enhanced New Game+) and any Chao-progression work that needs save state.
