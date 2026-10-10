# Known Functions

Confirmed ARM9/ARM7 addresses and behavior, with evidence and confidence, per the project's development rules.

**All offsets below are for the EU ROM (game code `CSNP`).** US (`YWSE`) addresses will differ and have not been looked up. The ARM9 binary loads at RAM `0x02000000` and sits at ROM offset `0x4000`, so:

```
RAM address = 0x02000000 + (ARM9 file offset)
ARM9 file offset = (ROM offset) - 0x4000
```

The binary is **not compressed** — code occupies roughly the first `0x0F0000`, with the main read-only string/RTTI region at about `0x0F0000`–`0x110000`. No ARM9/ARM7 overlays exist in this game, so there is no dynamically-loaded code to account for.

## `CDebugMenu` (C++ class, present in the retail binary)

**Confidence: high** for the addresses (derived by following the RTTI → typeinfo → vtable pointer chain and verifying the targets contain valid THUMB prologues). **Not confirmed** whether any of this is reached during normal play — see the reachability analysis in [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

| Item | ARM9 offset | RAM address |
|---|---|---|
| RTTI mangled name `10CDebugMenu` | `0xF8BA4` | `0x020F8BA4` |
| typeinfo struct | `0xF8B98` | `0x020F8B98` |
| vtable (layout: typeinfo ptr, then 3 function pointers) | `0xF8BB8` | `0x020F8BB8` |
| **vptr value stored into instances** | — | `0x020F8BBC` |
| virtual function 1 | `0x27880` | `0x02027881` (THUMB) |
| virtual function 2 | `0x278A4` | `0x020278A5` (THUMB) |
| virtual function 3 | `0x2789C` | `0x0202789D` (THUMB) |

Function pointers are odd because ARM encodes THUMB mode in bit 0; clear it to get the real instruction address. All three begin with `10 b5` (`push {r4, lr}`) and end with `10 bd` (`pop {r4, pc}`), and call out to sub-object destructors at instance offsets `+0x10`, `+0x1c`, `+0x1d` — consistent with destructors for a class holding member objects.

**Three code sites store the `0x020F8BBC` vptr** (i.e. construct a `CDebugMenu`):

| ARM9 offset | RAM address |
|---|---|
| `0x2FE6C` | `0x0202FE6C` |
| `0x301D0` | `0x020301D0` |
| `0x30A50` | `0x02030A50` |

Also present nearby in RTTI: `9SingletonI10CDebugMenuE` — i.e. `Singleton<CDebugMenu>`, so the menu was a singleton.

**Best next experiment:** set an execution breakpoint at `0x0202FE6C` (or on the vtable address) in melonDS/DeSmuME and play normally. If it is never hit, the constructor is dead code; if it is hit, the menu object is being built and the question becomes how it is displayed and dispatched.

## Character profile stat display (the POW/GRT visibility question)

**Confidence: high** for the addresses and the mechanism; derived by locating the GUI widget names in ARM9 and finding what points at them. **Not yet patched or tested.**

The character profile's stat rows live in `ProfileCreaturePanel.gui` → `EquipmentDataPanel`, as **label + value widget pairs**:

| Label widget | TLK strref | Shown | Value widget |
|---|---|---|---|
| `CLevel` | 19372 | Lv | `CLevelV` |
| `CHP` | 19373 | HP | `CHPV` |
| `CFP` | 19374 | **PP** | `CFPV` |
| `CSP` | 19375 | Spd | `CSPV` |
| `CAT` | 19376 | Atk | `CATV` |
| `CDE` | 19377 | Def | `CDEV` |
| `CLU` | 19378 | Lck | `CLUV` |

(`CFP` labelled "PP" is further confirmation that stat 28 is internally FP/Fatigue and displayed as PP.)

**The value widgets carry no stat binding.** Their only content is placeholder text `'99'` (field 60005) and their name (62000); field 60029 is a sequential tab index (6–13) shared by each label/value pair, *not* a stat ID. So the engine populates them **by widget name**, and the names are hardcoded in ARM9:

| Location | What it is |
|---|---|
| ARM9 `0x10666C`–`0x1069C` (RAM `0x0210666C`+) | the seven name strings, contiguous |
| ARM9 `0x1073D0`+ (RAM `0x021073D0`+) | a second copy of the same strings |
| **RAM `0x020BE944`–`0x020BE95C`** | **a 7-entry contiguous array of pointers to those strings** (4-byte spacing) |
| RAM `0x020EF188`–`0x020EF1D4` | individual literal-pool references, irregular spacing (per-instruction `ldr rX, =str`) |

**Consequence: POW (25) and GRT (26) cannot be added to the profile by data editing alone.** Adding `CPOWV`/`CGRTV` widgets to the `.gui` would place labels on screen, but nothing would fill them — they would render the literal placeholder `'99'`. The stat list is table-driven, but the table lives in the ARM9 binary, not in a GDA.

**Patch target if this is pursued:** the 7-pointer array at `0x020BE944` is the most promising entry point — extending it (and whatever loop bound consumes it) plus adding the matching stat fetches would make the hidden stats displayable. This needs: disassembly around the array's consumer, free space or a relocated array, and the stat-fetch logic for IDs 25/26. A real but scoped ARM9 project, and the first concrete candidate for one.

## Not yet known

Everything else: the level/XP curve code, level cap constant, stat growth, ability dispatch, enemy scaling, Chao handling, save serialization. No systematic disassembly has been done — only the targeted pointer-chase above.

## Planned approach when this starts

- Static: disassemble the ARM9 binary (offset `0x4000`, size `0x110DD8` in the EU ROM — see `research/phase0/rom_report_EU.txt`) with a tool that understands ARM/THUMB (e.g. Ghidra with an ARM9 loader, or similar), cross-referencing known Nitro SDK library function signatures where possible so we don't waste time re-identifying standard SDK code as if it were game-specific logic.
- Dynamic: melonDS's GDB stub (ARM9 port 3333, ARM7 port 3334 — `Config > Emu settings > Devtools > Enable GDB stub`, `gdb-multiarch`, `target remote 127.0.0.1:3333`) to watch real execution, e.g. single-stepping through a level-up or an ability activation to find the responsible code, once we have a save positioned at a useful point (we already have real local save data — see `KNOWN_MEMORY.md` and the reverse-engineering log).
- No overlay system exists in this game (confirmed — see the log), so there's no need to track dynamically-loaded overlay code; everything relevant is in the one static ARM9 binary.

This file gets populated once that work actually starts.
