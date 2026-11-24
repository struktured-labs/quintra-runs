# 20261123-1945-805476ea-easy-corvin-full

- Hero: **Corvin** (class_id 2)
- Difficulty: **easy**
- Player: machine / official-wrap-v13
- Seed: `2064128948`
- Build: `805476ea`
- Outcome: **timeout**
- Play time: 7188s cartridge, 432000 frames, wall 175.41s
- Furthest: stage 3, room 40, bosses beaten 2

## What happened

- Stage 1: 331s, 16 rooms, 28 hits / 28 dmg, deaths=0, boss seen=1 cleared=1, status={'bleed': 3, 'haste': 2}, outcome=cleared
- Stage 2: 706s, 19 rooms, 26 hits / 26 dmg, deaths=0, boss seen=1 cleared=1, status={'haste': 6}, outcome=cleared
- Stage 3: 6151s, 1 rooms, 0 hits / 0 dmg, deaths=0, boss seen=0 cleared=0, status={}, outcome=timeout

## Deaths

- None.

## Gameplay notes

- Stage 1 room 13: rune_sequence (locked).
- Solved rune_sequence in stage 1 room 13.
- Stage 1 room 14: none combat-sealed.
- Stage 1 room 15: none combat-sealed.
- Stage 1 room 7: none combat-sealed.
- Stage 1 room 9: push_seal (locked).
- Solved push_seal in stage 1 room 9.
- Stage 1 room 10: none combat-sealed.
- Stage 1 room 1: none combat-sealed.
- Stage 1 room 3: phase_switch.
- Stage 1 room 4: phase_gate.
- Stage 1 room 3: phase_switch.
- Stage 1 room 9: push_seal.
- Stage 1 room 7: none combat-sealed.
- Entered a Colossus fight on stage 1.
- Cleared stage 1 Colossus at t=331s.
- Stage 2 room 29: none combat-sealed.
- Stage 2 room 30: rune_sequence (locked).
- Solved rune_sequence in stage 2 room 30.
- Stage 2 room 29: none combat-sealed.
- Stage 2 room 28: none combat-sealed.
- Sealed room 28 t=30s pos=(114,139) hp=16 hostiles=2.
- Stage 2 room 27: none combat-sealed.
- Stage 2 room 28: none combat-sealed.
- Stage 2 room 29: none combat-sealed.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 29: none combat-sealed.
- Stage 2 room 27: none combat-sealed.
- Stage 2 room 26: push_seal (locked).
- Solved push_seal in stage 2 room 26.
- Stage 2 room 27: none combat-sealed.
- Stage 2 room 29: none combat-sealed.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 34: none combat-sealed.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 22: none combat-sealed.
- Stage 2 room 24: phase_switch.
- Stage 2 room 22: none combat-sealed.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 30: rune_sequence.
- Stage 2 room 34: none combat-sealed.
- Stage 2 room 35: none combat-sealed.
- Stage 2 room 36: phase_gate.
- Entered a Colossus fight on stage 2.
- Cleared stage 2 Colossus at t=706s.
- Timed out after 120.0 emulated minutes at stage 3 room 40.
- Entered 76 room transitions.
- Reached stage 3 (Cinder Rex wall). boss_seen=0 cleared=0 deaths=0 play_s=6151.
- Hit the emulated time cap; not a cartridge game-over.

## Boss attempts

- {'type': 'boss', 'event': 'seen', 'stage': 1, 'frame': 17674}
- {'type': 'boss', 'event': 'cleared', 'stage': 1, 'frame': 20098}
- {'type': 'boss', 'event': 'seen', 'stage': 2, 'frame': 60536}
- {'type': 'boss', 'event': 'cleared', 'stage': 2, 'frame': 62952}

## Notes (added at publish, Nov 23 8:20 PM ET)

- First full title-boot run on 805476ea to beat the stage-2 boss (cleared at frame 62952, about 17.5 game-minutes) and walk into the stage-3 Riftwild with 0 deaths.
- The "timeout" afterwards is a policy stall, not a game problem: on Riftwild field 14 the bot tried to square up into a thicket (it should have stepped 1px sideways). This was fixed after the run (step_to_waypoint alternates to the axis that changes cell); a probe from that point reaches the stage-3 dungeon.
- The video is trimmed to the first 15 minutes, which covers both boss clears.
