# Sonic Chronicles Modding Project

## Vision

A community-oriented modding framework and Mod Builder for *Sonic Chronicles: The Dark Brotherhood*.

**This is the original brief, kept in its own words.** It is worth having a record of what
was intended before anything was known about the game, separate from what was built.
[ROADMAP.md](ROADMAP.md) carries the status of each goal below; [README.md](README.md)
describes the tool as it actually exists.

The project lets a user supply their own Sonic Chronicles ROM, select modifications through
a profile or GUI, and generate a patch or build for their own game — which is what it now
does, through `tools/build/modbuild.py` and the Mod Pack Maker.

This is a **framework**, rather than one fixed ROM hack.

## Core goals

### Shadow Mode
Allow a new game to begin with Shadow functioning as the primary character instead of Sonic. Shadow already exists as a playable character, so the goal is to redirect existing systems rather than create a new character.

### Expanded progression
Investigate increasing the original level cap.

- Targets:
  - Level 50
  - Potentially Level 99
- Determine what systems depend on the original cap.

### Character abilities
Investigate whether existing POW/ability systems can be modified or recombined. Long-term examples include:

- Sonic teleport
- Sonic dash
- Shadow Chaos Control
- Shadow multi-dash
- New effects based on existing systems

Determine what is possible before designing the final ability system.

### Equipment overhaul
Make equipment more interesting and useful. Investigate:

- Stat bonuses
- Special effects
- Prices
- Requirements
- Rewards
- Unused equipment

### Chao progression
The original game relies on wireless functionality/trading for aspects of Chao progression. Investigate whether this can be replaced or supplemented with local progression.

Potential system: **Chao XP → Chao Level → stronger bonuses**

### Enemy scaling
Allow enemies to scale with player progression.

- Potential references:
  - Active character level
  - Highest party level
  - Average party level
- Potential scaling:
  - HP
  - Attack
  - Defense
  - Speed
  - XP
  - Rewards

### Boss scaling
Bosses should have their own scaling system so they remain relevant at higher player levels.

### Party freedom
Preserve story-based character recruitment. Once a character has been legitimately unlocked, investigate allowing greater freedom in party composition. Do not automatically unlock everyone at the beginning.

### New Game+
The original game already contains New Game+. Do not recreate it. Instead investigate modifying its existing persistence/reset behavior.

Potential future options:
- Retain equipment
- Retain Chao
- Retain abilities
- Use expanded level cap
- Enemy scaling against retained levels
- Change what resets

### Randomized character recruitment
Investigate whether character unlocks can be randomized while keeping the game's story functional.

Example:
- Original: Chapter 2 → Tails, Chapter 3 → Knuckles
- Randomized: Chapter 2 → Shadow, Chapter 3 → Rouge

This is a later feature and should not be attempted until the recruitment/story architecture is understood.

### Challenge modes
Eventually support predefined configurations such as:

- Vanilla+
- Hard Mode
- Shadow Mode
- Chaos Mode
- Randomizer

### Randomizer
The eventual final major feature. Potential randomized systems:

- Character recruitment
- Encounters
- Equipment
- Items
- Rewards
- Stats
- Chao bonuses
- Abilities

Randomization must support deterministic seeds.

## Important philosophy

The project should preserve the spirit of Sonic Chronicles while allowing players to create alternate ways to experience it. The goal is not simply to make the game harder. The goal is to expose interesting systems that the original game already contains and extend them where technically practical.

## Development priority

Priority should generally be:

1. Research
2. Extraction/build pipeline
3. Small proof of concept
4. Data editing
5. Shadow Mode
6. Level expansion
7. Equipment/Chao systems
8. Enemy/boss scaling
9. Party freedom
10. Ability experimentation
11. Enhanced NG+
12. Randomized recruitment
13. Challenge modes
14. Full randomizer
15. GUI polish

This order can change if reverse engineering reveals a better path.

## Important constraint

Do not assume any desired feature is possible. Prove it experimentally. A technically impossible or excessively fragile feature should be identified honestly rather than simulated with unreliable code.
