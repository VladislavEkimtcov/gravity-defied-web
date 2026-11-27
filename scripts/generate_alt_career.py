#!/usr/bin/env python3
"""Generate `/Users/ekimtco2/gravity-defied-web/src/assets/alt-career.mrg`.

Produces a 3-tier x 10-track (30 tracks total) Gravity Defied career file
inspired by the legendary `100%` track:
  - Tier 0 (Easy):   100% Warmup  (10 tracks)
  - Tier 1 (Medium): 100% Trials  (10 tracks)
  - Tier 2 (Pro):    100% Legends (10 tracks)

Binary `.mrg` format (big endian):
  For each of 3 levels:
    int32 trackCount
    For each track:
      int32 offset
      char[] name (ASCII, '_' renders as space, NUL-terminated, max 40 bytes)
  At each track offset:
    int8 marker (0)
    4 x int32: startX, startY, finishX, finishY (in world << 13 units)
    int16 pointsCount
    2 x int32: x0, y0 (world units)
    (pointsCount - 1) deltas:
      if 1 <= dx <= 127 and -127 <= dy <= 127: int8 dx, int8 dy
      else: int8 -1, int32 x, int32 y
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


WORLD_SHIFT = 1 << 13  # 8192


@dataclass
class TrackData:
    name: str
    start_x: int
    start_y: int
    finish_x: int
    finish_y: int
    points: list[tuple[int, int]]


class TrackBuilder:
    """Fluent polyline builder enforcing strict X-monotonicity and beveled geometry."""

    def __init__(self, start_x: int = -125, start_y: int = 142) -> None:
        self.points: list[tuple[int, int]] = [(int(start_x), int(start_y))]
        self.x = int(start_x)
        self.y = int(start_y)
        self.spawn_x = 95
        self.spawn_y = 118
        self.finish_x = 0

    def add_rel(self, dx: int, dy: int) -> "TrackBuilder":
        dx = int(round(dx))
        dy = int(round(dy))
        if dx < 1:
            dx = 1
        self.x += dx
        self.y += dy
        self.points.append((self.x, self.y))
        return self

    def start_runway(self, ground_y: int = 100, pad_len: int = 160) -> "TrackBuilder":
        """Build a 100%-style backstop + flat/gentle start pad."""
        self.points = [(-125, ground_y + 42)]
        self.x, self.y = -125, ground_y + 42
        self.add_rel(95, -40)   # x = -30, ground_y + 2
        self.add_rel(45, -2)    # x = 15, ground_y
        spawn_center = 95
        self.add_rel(spawn_center + 20 - self.x, 0)  # x = 115
        self.add_rel(pad_len - 100, 1)  # gentle pad past start flag
        self.spawn_x = spawn_center
        self.spawn_y = ground_y + 18  # matches 100%: drops gently onto both wheels
        return self

    def finish_runoff(self, runoff_len: int = 230) -> "TrackBuilder":
        """Create a safe flat finish pad and generous runoff past finishX."""
        self.add_rel(36, 0)
        self.finish_x = self.x - 16
        # First point past finish_x triggers finish line in GameLevel
        self.add_rel(40, 0)
        self.add_rel(75, 4)
        self.add_rel(max(80, runoff_len - 115), 14)
        return self

    def flat(self, length: int, dy: int = 0) -> "TrackBuilder":
        return self.add_rel(length, dy)

    def ramp(self, dx: int, dy: int, steps: int = 1) -> "TrackBuilder":
        if steps <= 1:
            return self.add_rel(dx, dy)
        sx = dx / steps
        sy = dy / steps
        rem_x, rem_y = 0.0, 0.0
        for _ in range(steps):
            rem_x += sx
            rem_y += sy
            ix = max(1, int(round(rem_x)))
            iy = int(round(rem_y))
            rem_x -= ix
            rem_y -= iy
            self.add_rel(ix, iy)
        return self

    def crest(self, up_dx: int, up_dy: int, top_flat: int, down_dx: int, down_dy: int) -> "TrackBuilder":
        """Beveled crest like 100%'s plateaus."""
        self.add_rel(max(6, up_dx - 7), max(1, up_dy - 5))
        self.add_rel(7, min(5, up_dy))
        self.add_rel(max(12, top_flat), 0)
        self.add_rel(7, max(-5, down_dy))
        self.add_rel(max(6, down_dx - 7), min(-1, down_dy + 5))
        return self

    def step_up(self, height: int, rise_dx: int = 16, deck_len: int = 34, bevel: int = 6) -> "TrackBuilder":
        """100%-style beveled trials step-up ledge."""
        b_dy = min(4, max(2, height // 5))
        core_dy = max(2, height - 2 * b_dy)
        core_dx = max(5, rise_dx - bevel)
        self.add_rel(bevel, b_dy)
        self.add_rel(core_dx, core_dy)
        self.add_rel(bevel, b_dy)
        self.add_rel(max(16, deck_len), 0)
        return self

    def step_down(self, drop: int, drop_dx: int = 16, floor_len: int = 32, bevel: int = 6) -> "TrackBuilder":
        """Beveled step-down with gentle catch floor."""
        b_dy = min(4, max(2, drop // 5))
        core_dy = max(2, drop - 2 * b_dy)
        core_dx = max(5, drop_dx - bevel)
        self.add_rel(bevel, -b_dy)
        self.add_rel(core_dx, -core_dy)
        self.add_rel(bevel, -b_dy)
        self.add_rel(max(16, floor_len), 0)
        return self

    def crevice(self, width: int = 15, depth: int = 44) -> "TrackBuilder":
        """100%-style narrow V-crevice preceded by a short settling lip."""
        self.add_rel(16, 4)
        half_w = max(6, width // 2)
        other_w = max(6, width - half_w)
        self.add_rel(5, -3)
        self.add_rel(half_w, -depth)
        self.add_rel(other_w, depth + 2)
        self.add_rel(22, 2)
        return self

    def chasm(
        self,
        gap_width: int = 44,
        depth: int = 68,
        drop_net: int = -18,
        launch_dx: int = 44,
        launch_dy: int = 24,
        catch_dx: int = 56,
        catch_dy: int = -18,
    ) -> "TrackBuilder":
        """Sculpted jumpable chasm with exact lip-to-lip gap_width and recoverable bottom bowl."""
        # Approach launch ramp with beveled lip
        if launch_dx > 0:
            self.add_rel(max(12, launch_dx - 8), max(2, launch_dy - 4))
            self.add_rel(8, min(4, launch_dy))

        # Lip-to-lip horizontal span ~= gap_width
        in_dx = max(10, int(gap_width * 0.24))
        bowl_dx = max(16, int(gap_width * 0.34))
        out_dx = max(14, gap_width - in_dx - bowl_dx)
        # Keep drop realistic so bottom bowl is recoverable if a rider drops short
        eff_depth = min(depth, max(44, int(out_dx * 2.2) + abs(drop_net)))

        self.add_rel(5, -5)
        self.add_rel(in_dx, -(eff_depth - 5))
        # Bottom bowl
        b1 = bowl_dx // 2
        b2 = bowl_dx - b1
        self.add_rel(b1, -3)
        self.add_rel(b2, 5)
        # Climbable/stepped exit wall to landing lip
        exit_rise = eff_depth + drop_net - 2
        if exit_rise > 42:
            m_dx = out_dx // 2
            m_dy = exit_rise // 2
            self.add_rel(m_dx, m_dy)
            self.add_rel(5, 2)
            self.add_rel(max(8, out_dx - m_dx - 5), exit_rise - m_dy - 2)
        else:
            self.add_rel(out_dx, exit_rise)

        # Rounded landing lip + catch downslope + settling flat
        self.add_rel(7, 1)
        if catch_dx > 0:
            self.add_rel(catch_dx, catch_dy)
        self.add_rel(22, 0)
        return self

    def bowl(self, width: int = 130, depth: int = 52, exit_rise: int = 50) -> "TrackBuilder":
        """Smooth curved G-out bowl with gradual entry and exit transitions."""
        w1 = max(20, int(width * 0.16))
        w2 = max(22, int(width * 0.18))
        w3 = max(20, int(width * 0.15))
        w4 = max(22, int(width * 0.15))
        w5 = max(20, int(width * 0.18))
        w6 = max(20, width - w1 - w2 - w3 - w4 - w5)
        d1 = int(depth * 0.44)
        d2 = int(depth * 0.40)
        d3 = depth - d1 - d2
        r1 = int(exit_rise * 0.22)
        r2 = int(exit_rise * 0.44)
        r3 = exit_rise - r1 - r2
        self.add_rel(w1, -d1)
        self.add_rel(w2, -d2)
        self.add_rel(w3, -d3)
        self.add_rel(w4, r1)
        self.add_rel(w5, r2)
        self.add_rel(w6, r3)
        self.add_rel(22, 4)
        return self

    def plunge_catch(self, drop: int = 110, horiz: int = 105, catch_len: int = 85) -> "TrackBuilder":
        """Dramatic plunge with smooth circular-arc catch transition and settling flat."""
        s1 = max(14, int(horiz * 0.28))
        s2 = max(16, int(horiz * 0.36))
        s3 = max(16, horiz - s1 - s2)
        d1 = int(drop * 0.22)
        d2 = int(drop * 0.56)
        d3 = drop - d1 - d2
        self.add_rel(s1, -d1)
        self.add_rel(s2, -d2)
        self.add_rel(s3, -d3)
        c1 = max(22, catch_len // 2)
        c2 = max(22, catch_len - c1)
        self.add_rel(c1, -6)
        self.add_rel(c2, 6)
        self.add_rel(24, 2)
        return self

    def rollers(self, count: int = 3, period: int = 68, amp: int = 14, climb_per: int = 14) -> "TrackBuilder":
        """Flowing rhythm rollers climbing gently."""
        q = max(10, period // 4)
        for _ in range(count):
            self.add_rel(q, amp + climb_per // 3)
            self.add_rel(q, -amp // 2)
            self.add_rel(q, -amp // 2 + climb_per // 3)
            self.add_rel(q, climb_per - 2 * (climb_per // 3))
        return self

    def build(self, name: str) -> TrackData:
        for i in range(1, len(self.points)):
            assert self.points[i][0] > self.points[i - 1][0], (
                f"{name}: non-increasing X at {i}: {self.points[i-1]} -> {self.points[i]}"
            )
        return TrackData(
            name=name,
            start_x=self.spawn_x,
            start_y=self.spawn_y,
            finish_x=self.finish_x,
            finish_y=0,
            points=self.points,
        )


# ---------------------------------------------------------------------------
# TIER 0: "100% Warmup" (Easy, 10 tracks)
# ---------------------------------------------------------------------------

def build_tier0() -> list[TrackData]:
    tracks: list[TrackData] = []

    # 1. First_Percent
    b = TrackBuilder().start_runway(100, 155)
    b.ramp(70, 22, 2).step_up(12, 16, 36).ramp(65, 24, 2)
    b.crevice(14, 24).flat(30, 4)
    b.rollers(2, 68, 12, 18)
    b.step_up(14, 18, 38).ramp(75, 26, 2)
    b.bowl(115, 34, 42).ramp(70, 22, 2)
    b.finish_runoff(230)
    tracks.append(b.build("First_Percent"))

    # 2. Crest_Flow
    b = TrackBuilder().start_runway(95, 155)
    b.crest(42, 24, 26, 48, -16)
    b.ramp(55, 22, 2).step_up(13, 18, 34)
    b.crest(46, 28, 28, 52, -18)
    b.bowl(120, 38, 46)
    b.crest(45, 26, 24, 44, -12)
    b.ramp(65, 24, 2)
    b.finish_runoff(230)
    tracks.append(b.build("Crest_Flow"))

    # 3. Notch_Intro
    b = TrackBuilder().start_runway(100, 150)
    b.ramp(60, 24, 2).crevice(14, 28).flat(34, 4)
    b.step_up(14, 16, 36).ramp(55, 22, 2)
    b.crevice(15, 32).flat(38, 2)
    b.bowl(120, 40, 46)
    b.step_up(15, 18, 38).crevice(14, 30).ramp(60, 20, 2)
    b.finish_runoff(230)
    tracks.append(b.build("Notch_Intro"))

    # 4. Mini_Chasm
    b = TrackBuilder().start_runway(100, 160)
    b.ramp(55, 16, 2)
    b.chasm(gap_width=24, depth=44, drop_net=-8, launch_dx=36, launch_dy=18, catch_dx=46, catch_dy=-10)
    b.ramp(60, 20, 2).step_up(14, 18, 36)
    b.chasm(gap_width=26, depth=48, drop_net=-10, launch_dx=40, launch_dy=20, catch_dx=50, catch_dy=-12)
    b.rollers(2, 66, 12, 16).ramp(55, 20, 2)
    b.finish_runoff(230)
    tracks.append(b.build("Mini_Chasm"))

    # 5. Step_Rhythm
    b = TrackBuilder().start_runway(90, 150)
    b.ramp(45, 14)
    for h in (12, 15, 14, 17, 15):
        b.step_up(h, 16, 38)
        b.ramp(38, 12)
    b.plunge_catch(68, 78, 68)
    b.step_up(16, 18, 40).ramp(65, 22, 2)
    b.finish_runoff(230)
    tracks.append(b.build("Step_Rhythm"))

    # 6. Ridge_Run
    b = TrackBuilder().start_runway(95, 155)
    b.ramp(85, 42, 3).crest(36, 22, 26, 36, -16)
    b.ramp(75, 44, 3).crevice(15, 32).flat(36, 6)
    b.step_up(16, 18, 36).ramp(80, 48, 3)
    b.crest(40, 26, 28, 44, -20)
    b.plunge_catch(80, 86, 72).ramp(60, 18, 2)
    b.finish_runoff(230)
    tracks.append(b.build("Ridge_Run"))

    # 7. Double_Dip
    b = TrackBuilder().start_runway(100, 155)
    b.ramp(50, 18).bowl(140, 52, 62)
    b.step_up(16, 18, 38).crevice(15, 32)
    b.ramp(55, 18).bowl(145, 56, 66)
    b.rollers(2, 68, 14, 18)
    b.finish_runoff(230)
    tracks.append(b.build("Double_Dip"))

    # 8. Twin_Peaks
    b = TrackBuilder().start_runway(90, 150)
    b.ramp(75, 38, 2).step_up(15, 18, 34).crest(38, 26, 28, 40, -22)
    b.bowl(160, 52, 50).flat(20, 0)
    b.step_up(14, 18, 34).ramp(75, 40, 2).step_up(15, 18, 36)
    b.crest(36, 24, 30, 36, -12)
    b.finish_runoff(230)
    tracks.append(b.build("Twin_Peaks"))

    # 9. Climb_Trial
    b = TrackBuilder().start_runway(90, 150)
    b.ramp(70, 36, 2).step_up(15, 16, 36)
    b.ramp(80, 48, 3).crevice(15, 34).flat(36, 4)
    b.step_up(18, 18, 38).ramp(85, 52, 3)
    b.bowl(115, 28, 44)
    b.step_up(16, 16, 36).ramp(85, 46, 3)
    b.finish_runoff(230)
    tracks.append(b.build("Climb_Trial"))

    # 10. Fifty_Percent
    b = TrackBuilder().start_runway(95, 155)
    b.ramp(65, 28, 2).step_up(16, 16, 36).ramp(60, 32, 2)
    b.crevice(15, 36).flat(34, 4)
    b.chasm(gap_width=28, depth=52, drop_net=-10, launch_dx=40, launch_dy=22, catch_dx=52, catch_dy=-14)
    b.step_up(18, 18, 36).bowl(135, 48, 56)
    b.rollers(2, 66, 13, 20).step_up(16, 16, 34)
    b.ramp(70, 28, 2)
    b.finish_runoff(240)
    tracks.append(b.build("Fifty_Percent"))

    return tracks


# ---------------------------------------------------------------------------
# TIER 1: "100% Trials" (Medium, 10 tracks)
# ---------------------------------------------------------------------------

def build_tier1() -> list[TrackData]:
    tracks: list[TrackData] = []

    # 1. Seventy_Five
    b = TrackBuilder().start_runway(95, 155)
    b.ramp(65, 34, 2).step_up(18, 16, 34).ramp(70, 46, 2)
    b.crevice(15, 44).flat(36, 4)
    b.chasm(gap_width=34, depth=60, drop_net=-14, launch_dx=42, launch_dy=24, catch_dx=54, catch_dy=-16)
    b.step_up(19, 16, 34).bowl(135, 50, 60)
    b.crevice(16, 44).ramp(75, 44, 3).step_up(18, 16, 36)
    b.finish_runoff(240)
    tracks.append(b.build("Seventy_Five"))

    # 2. Split_Crevice
    b = TrackBuilder().start_runway(100, 155)
    b.ramp(60, 26, 2).crevice(15, 44).flat(38, 4)
    b.step_up(18, 16, 32).crevice(16, 46).flat(38, 4)
    b.bowl(130, 48, 58)
    b.step_up(19, 16, 34).crevice(16, 46).ramp(60, 28, 2)
    b.crevice(15, 44).ramp(65, 30, 2)
    b.finish_runoff(240)
    tracks.append(b.build("Split_Crevice"))

    # 3. Switchback
    b = TrackBuilder().start_runway(95, 155)
    b.ramp(75, 48, 3).step_up(18, 16, 32).crest(34, 26, 22, 34, -22)
    b.plunge_catch(96, 92, 72).ramp(70, 48, 3)
    b.step_up(20, 16, 34).crest(36, 28, 24, 38, -24)
    b.plunge_catch(104, 98, 74).ramp(85, 52, 3)
    b.finish_runoff(240)
    tracks.append(b.build("Switchback"))

    # 4. Ledge_Hook
    b = TrackBuilder().start_runway(95, 150)
    b.ramp(50, 20)
    for h in (18, 21, 19, 22, 20, 22):
        b.step_up(h, 16, 34)
        b.ramp(36, 16)
    b.bowl(135, 54, 62)
    b.step_up(20, 16, 36).ramp(65, 28, 2)
    b.finish_runoff(240)
    tracks.append(b.build("Ledge_Hook"))

    # 5. Drop_Canyon
    b = TrackBuilder().start_runway(120, 150)
    b.ramp(55, 22).plunge_catch(125, 106, 80)
    b.step_up(18, 16, 34).ramp(75, 46, 3)
    b.chasm(gap_width=36, depth=62, drop_net=-16, launch_dx=42, launch_dy=24, catch_dx=54, catch_dy=-18)
    b.plunge_catch(118, 102, 78)
    b.ramp(80, 52, 3).step_up(20, 16, 36)
    b.finish_runoff(240)
    tracks.append(b.build("Drop_Canyon"))

    # 6. Sawtooth
    b = TrackBuilder().start_runway(95, 155)
    for up_dx, up_dy, drop in ((72, 46, 52), (76, 52, 58), (80, 56, 62), (76, 54, 54)):
        b.ramp(up_dx, up_dy, 3)
        b.crest(24, 16, 16, 20, -14)
        b.plunge_catch(drop, 60, 56)
    b.ramp(75, 42, 3)
    b.finish_runoff(240)
    tracks.append(b.build("Sawtooth"))

    # 7. Razor_Ridge
    b = TrackBuilder().start_runway(100, 155)
    b.ramp(70, 42, 3).crest(32, 24, 24, 32, -18)
    b.chasm(gap_width=36, depth=62, drop_net=-14, launch_dx=40, launch_dy=24, catch_dx=52, catch_dy=-16)
    b.step_up(20, 16, 34).crevice(16, 46)
    b.ramp(60, 30, 2)
    b.chasm(gap_width=38, depth=66, drop_net=-16, launch_dx=44, launch_dy=26, catch_dx=54, catch_dy=-18)
    b.step_up(18, 16, 34).ramp(70, 38, 3)
    b.finish_runoff(240)
    tracks.append(b.build("Razor_Ridge"))

    # 8. Stairway
    b = TrackBuilder().start_runway(90, 150)
    b.ramp(55, 28, 2).step_up(18, 16, 32).step_up(20, 16, 32)
    b.ramp(75, 48, 3).bowl(120, 36, 48)
    b.step_up(20, 16, 34).step_up(22, 16, 34)
    b.ramp(85, 56, 3).crevice(16, 46)
    b.step_up(20, 16, 34).ramp(85, 54, 3)
    b.finish_runoff(240)
    tracks.append(b.build("Stairway"))

    # 9. Saddle_Gap
    b = TrackBuilder().start_runway(100, 155)
    b.ramp(60, 24, 2).bowl(135, 48, 56)
    b.chasm(gap_width=38, depth=64, drop_net=-16, launch_dx=44, launch_dy=26, catch_dx=56, catch_dy=-18)
    b.bowl(140, 50, 58)
    b.chasm(gap_width=40, depth=66, drop_net=-18, launch_dx=46, launch_dy=26, catch_dx=58, catch_dy=-18)
    b.step_up(19, 16, 34).ramp(70, 34, 2)
    b.finish_runoff(240)
    tracks.append(b.build("Saddle_Gap"))

    # 10. Ninety_Nine
    b = TrackBuilder().start_runway(95, 155)
    b.ramp(65, 36, 2).step_up(20, 16, 34).ramp(70, 48, 3)
    b.step_up(20, 16, 32).crevice(16, 48).flat(36, 4)
    b.chasm(gap_width=38, depth=66, drop_net=-16, launch_dx=44, launch_dy=26, catch_dx=54, catch_dy=-18)
    b.plunge_catch(104, 96, 76)
    b.step_up(21, 16, 34).ramp(85, 56, 3)
    b.chasm(gap_width=36, depth=62, drop_net=-14, launch_dx=42, launch_dy=24, catch_dx=54, catch_dy=-16)
    b.step_up(18, 16, 34).ramp(75, 40, 3)
    b.finish_runoff(250)
    tracks.append(b.build("Ninety_Nine"))

    return tracks


# ---------------------------------------------------------------------------
# TIER 2: "100% Legends" (Pro, 10 tracks)
# ---------------------------------------------------------------------------

def build_tier2() -> list[TrackData]:
    tracks: list[TrackData] = []

    # 1. 100%_Redux
    b = TrackBuilder().start_runway(94, 160)
    b.ramp(72, 42, 3).step_up(22, 16, 32).ramp(72, 54, 3)
    b.step_up(23, 16, 42).step_up(20, 15, 28).step_down(20, 15, 28)
    b.ramp(85, 62, 3)
    b.chasm(gap_width=46, depth=72, drop_net=-18, launch_dx=46, launch_dy=28, catch_dx=56, catch_dy=-20)
    b.plunge_catch(115, 100, 74).ramp(80, 58, 3)
    b.crevice(16, 60).flat(38, 4)
    b.chasm(gap_width=48, depth=74, drop_net=-20, launch_dx=48, launch_dy=30, catch_dx=58, catch_dy=-22)
    b.step_up(23, 16, 34).ramp(85, 60, 3)
    b.chasm(gap_width=44, depth=68, drop_net=-16, launch_dx=44, launch_dy=28, catch_dx=56, catch_dy=-18)
    b.step_up(22, 16, 36).ramp(95, 58, 3)
    b.finish_runoff(260)
    tracks.append(b.build("100%_Redux"))

    # 2. Skyline_100
    b = TrackBuilder().start_runway(95, 160)
    b.ramp(80, 52, 3).step_up(22, 16, 32).crest(36, 28, 24, 34, -20)
    b.chasm(gap_width=46, depth=72, drop_net=-18, launch_dx=46, launch_dy=28, catch_dx=56, catch_dy=-18)
    b.ramp(85, 58, 3).step_up(23, 16, 34).crevice(16, 54).flat(36, 4)
    b.chasm(gap_width=52, depth=76, drop_net=-22, launch_dx=50, launch_dy=30, catch_dx=60, catch_dy=-22)
    b.bowl(165, 50, 56).flat(26, 2)
    b.step_up(20, 17, 36).ramp(95, 62, 3)
    b.chasm(gap_width=44, depth=68, drop_net=-16, launch_dx=44, launch_dy=26, catch_dx=56, catch_dy=-16)
    b.ramp(85, 48, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Skyline_100"))

    # 3. Needle_Crest
    b = TrackBuilder().start_runway(95, 155)
    b.ramp(65, 38, 3).crevice(16, 54).flat(34, 4)
    b.crest(38, 30, 22, 34, -20)
    b.chasm(gap_width=44, depth=70, drop_net=-16, launch_dx=44, launch_dy=28, catch_dx=54, catch_dy=-18)
    b.crevice(16, 56).step_up(22, 16, 32)
    b.crest(36, 28, 22, 34, -20)
    b.chasm(gap_width=48, depth=74, drop_net=-18, launch_dx=48, launch_dy=30, catch_dx=58, catch_dy=-20)
    b.crevice(16, 54).ramp(75, 48, 3)
    b.step_up(23, 16, 34).ramp(85, 52, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Needle_Crest"))

    # 4. Vortex_Bowl
    b = TrackBuilder().start_runway(140, 155)
    b.ramp(55, 22).plunge_catch(140, 114, 82)
    b.ramp(85, 62, 3).step_up(23, 16, 34)
    b.chasm(gap_width=48, depth=74, drop_net=-20, launch_dx=48, launch_dy=28, catch_dx=58, catch_dy=-22)
    b.plunge_catch(148, 118, 84)
    b.step_up(22, 16, 32).ramp(90, 64, 3)
    b.bowl(155, 60, 72)
    b.chasm(gap_width=46, depth=70, drop_net=-16, launch_dx=46, launch_dy=28, catch_dx=56, catch_dy=-18)
    b.ramp(85, 50, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Vortex_Bowl"))

    # 5. Cliffhanger
    b = TrackBuilder().start_runway(110, 155)
    b.ramp(60, 32, 2)
    for h in (22, 24, 22):
        b.step_up(h, 16, 34)
        b.ramp(40, 22)
    b.plunge_catch(126, 108, 78)
    b.step_up(23, 16, 34)
    b.chasm(gap_width=46, depth=72, drop_net=-18, launch_dx=46, launch_dy=28, catch_dx=56, catch_dy=-20)
    b.step_up(24, 16, 36).ramp(85, 56, 3)
    b.plunge_catch(112, 98, 74).ramp(85, 52, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Cliffhanger"))

    # 6. Gravity_Well
    b = TrackBuilder().start_runway(140, 155)
    b.ramp(55, 20).plunge_catch(156, 122, 86)
    b.step_up(22, 16, 34).ramp(80, 56, 3)
    b.chasm(gap_width=52, depth=78, drop_net=-20, launch_dx=50, launch_dy=30, catch_dx=60, catch_dy=-22)
    b.plunge_catch(138, 112, 80)
    b.step_up(22, 16, 34).crevice(14, 48).ramp(85, 56, 3)
    b.chasm(gap_width=50, depth=76, drop_net=-18, launch_dx=48, launch_dy=28, catch_dx=58, catch_dy=-20)
    b.ramp(95, 60, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Gravity_Well"))

    # 7. Iron_Ladder
    b = TrackBuilder().start_runway(90, 155)
    b.ramp(55, 30, 2)
    for h in (22, 24, 24):
        b.step_up(h, 16, 32)
        b.ramp(42, 24, 2)
    b.crevice(16, 54).flat(36, 4)
    b.bowl(160, 48, 54).flat(24, 2)
    for h in (20, 22, 20):
        b.step_up(h, 18, 38)
        b.ramp(44, 24, 2)
    b.chasm(gap_width=44, depth=68, drop_net=-16, launch_dx=44, launch_dy=28, catch_dx=56, catch_dy=-18)
    b.ramp(85, 48, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Iron_Ladder"))

    # 8. Apex_Assault
    b = TrackBuilder().start_runway(100, 165)
    b.ramp(80, 36, 3)
    b.chasm(gap_width=52, depth=74, drop_net=-22, launch_dx=50, launch_dy=30, catch_dx=62, catch_dy=-24)
    b.bowl(150, 48, 60)
    b.chasm(gap_width=50, depth=74, drop_net=-20, launch_dx=52, launch_dy=30, catch_dx=64, catch_dy=-18)
    b.flat(28, -2).step_up(18, 18, 38).ramp(85, 52, 3)
    b.chasm(gap_width=52, depth=74, drop_net=-20, launch_dx=50, launch_dy=30, catch_dx=60, catch_dy=-22)
    b.ramp(95, 52, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Apex_Assault"))

    # 9. Gauntlet_110
    b = TrackBuilder().start_runway(95, 160)
    b.ramp(70, 42, 3).step_up(23, 16, 32).crevice(16, 56).flat(34, 4)
    b.chasm(gap_width=48, depth=74, drop_net=-18, launch_dx=48, launch_dy=28, catch_dx=58, catch_dy=-20)
    b.plunge_catch(128, 108, 78)
    b.step_up(24, 16, 34).step_up(23, 16, 34)
    b.chasm(gap_width=50, depth=76, drop_net=-18, launch_dx=48, launch_dy=30, catch_dx=60, catch_dy=-20)
    b.crevice(16, 56).ramp(85, 58, 3)
    b.chasm(gap_width=46, depth=70, drop_net=-16, launch_dx=46, launch_dy=28, catch_dx=56, catch_dy=-18)
    b.ramp(90, 54, 3)
    b.finish_runoff(260)
    tracks.append(b.build("Gauntlet_110"))

    # 10. 200%_Finale
    b = TrackBuilder().start_runway(94, 165)
    b.ramp(75, 44, 3).step_up(22, 16, 34).crevice(16, 56).flat(36, 4)
    b.step_up(24, 16, 32).step_up(23, 16, 34).step_up(22, 16, 34)
    b.plunge_catch(140, 114, 82)
    b.ramp(85, 62, 3)
    b.chasm(gap_width=54, depth=78, drop_net=-20, launch_dx=52, launch_dy=32, catch_dx=62, catch_dy=-22)
    b.bowl(150, 56, 70)
    b.crevice(16, 58).step_up(24, 16, 34)
    b.chasm(gap_width=50, depth=76, drop_net=-18, launch_dx=48, launch_dy=30, catch_dx=60, catch_dy=-20)
    b.ramp(95, 64, 3).step_up(24, 16, 36).ramp(95, 58, 3)
    b.finish_runoff(280)
    tracks.append(b.build("200%_Finale"))

    return tracks


def encode_track_payload(track: TrackData) -> bytes:
    buf = bytearray()
    buf.append(0)  # marker != 50
    buf.extend(
        struct.pack(
            ">4i",
            track.start_x * WORLD_SHIFT,
            track.start_y * WORLD_SHIFT,
            track.finish_x * WORLD_SHIFT,
            track.finish_y * WORLD_SHIFT,
        )
    )
    pts = track.points
    buf.extend(struct.pack(">h", len(pts)))
    x0, y0 = pts[0]
    buf.extend(struct.pack(">2i", x0, y0))
    px, py = x0, y0
    for x, y in pts[1:]:
        dx = x - px
        dy = y - py
        assert dx > 0, f"{track.name}: non-increasing X ({px} -> {x})"
        if 1 <= dx <= 127 and -127 <= dy <= 127:
            buf.extend(struct.pack(">bb", dx, dy))
        else:
            buf.extend(struct.pack(">bii", -1, x, y))
        px, py = x, y
    return bytes(buf)


def write_mrg(levels: list[list[TrackData]], out_path: Path) -> None:
    assert len(levels) == 3
    header_size = 0
    for tracks in levels:
        header_size += 4
        for t in tracks:
            name_bytes = t.name.encode("ascii")
            assert len(name_bytes) < 40, f"Track name too long: {t.name}"
            header_size += 4 + len(name_bytes) + 1

    payloads: list[list[bytes]] = []
    offsets: list[list[int]] = []
    cur_offset = header_size
    for tracks in levels:
        lvl_payloads: list[bytes] = []
        lvl_offsets: list[int] = []
        for t in tracks:
            p = encode_track_payload(t)
            lvl_offsets.append(cur_offset)
            lvl_payloads.append(p)
            cur_offset += len(p)
        payloads.append(lvl_payloads)
        offsets.append(lvl_offsets)

    out = bytearray()
    for lvl_idx, tracks in enumerate(levels):
        out.extend(struct.pack(">i", len(tracks)))
        for trk_idx, t in enumerate(tracks):
            out.extend(struct.pack(">i", offsets[lvl_idx][trk_idx]))
            out.extend(t.name.encode("ascii"))
            out.append(0)

    assert len(out) == header_size
    for lvl_payloads in payloads:
        for p in lvl_payloads:
            out.extend(p)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(out))


def print_summary(levels: list[list[TrackData]]) -> None:
    tier_names = ["Tier 0 (Easy - 100% Warmup)", "Tier 1 (Medium - 100% Trials)", "Tier 2 (Pro - 100% Legends)"]
    for lvl_idx, tracks in enumerate(levels):
        print(f"=== {tier_names[lvl_idx]} ===")
        for i, t in enumerate(tracks):
            xs = [p[0] for p in t.points]
            gain = sum(max(0, t.points[k + 1][1] - t.points[k][1]) for k in range(len(t.points) - 1))
            drop = sum(min(0, t.points[k + 1][1] - t.points[k][1]) for k in range(len(t.points) - 1))
            print(
                f"  [{i}] {t.name:16s} pts={len(t.points):3d} x=[{min(xs)}..{max(xs)}] "
                f"start=({t.start_x},{t.start_y}) finX={t.finish_x} gain=+{gain} drop={drop}"
            )


def main() -> None:
    levels = [build_tier0(), build_tier1(), build_tier2()]
    out_path = Path(__file__).resolve().parent.parent / "src" / "assets" / "alt-career.mrg"
    write_mrg(levels, out_path)
    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
    print_summary(levels)


if __name__ == "__main__":
    main()
