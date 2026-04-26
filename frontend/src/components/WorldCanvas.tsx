// Binds data (React Query) + view state (Zustand) + render adapter
// (Renderer interface) behind a single React component.
//
// Render loop contract:
//   - We do NOT re-render the component every tick. React decides when
//     to mount/unmount; requestAnimationFrame decides when to draw.
//     Tick-rate and frame-rate are decoupled by design (§9.23).
//   - The rAF callback reads the *latest* data from refs populated by
//     the React/Zustand hooks. So when React Query or Zustand updates,
//     the next frame picks it up; we don't restart the loop.
//   - The Renderer is mounted once and disposed on unmount.
//
// Sizing:
//   - A `ResizeObserver` watches the wrapper `observe__frame` (the
//     parent node of this component). On world-load or frame resize,
//     we compute the zoom that makes the world fill the frame, then
//     centre the camera. This is the Konva/TileMap "fit-to-viewport"
//     pattern — the canvas is never a small island in a big dark void.
//   - Manual wheel-zoom overrides auto-fit until the world reloads.
//
// Interaction:
//   - Drag (mousedown → mousemove → mouseup) pans the camera.
//   - Wheel zooms around the cursor — the tile under the cursor stays
//     under the cursor across the zoom, which feels natural.
//   - A click without meaningful drag hit-tests the agent layer and
//     updates `selectedAgentId` via Zustand.
import { useEffect, useMemo, useRef, useState } from 'react';

import { ApiError } from '../api/client';
import type { Agent, Colony } from '../api/types';
import { useAgents, useColonies, useSimulation, useWorld, useWorldStream } from '../api/queries';
import { Canvas2DRenderer } from '../render/Canvas2DRenderer';
import type { FrameSnapshot, Renderer } from '../render/Renderer';
import { isReducedMotion } from '../state/reducedMotion';
import { useViewStore } from '../state/viewStore';
import { AgentTooltip } from './AgentTooltip';

// Source sprites are 64×64, so BASE_TILE_PX=64 means zoom=1.0 renders
// at native resolution (no scaling, sharpest result). The zoom floor
// drops to 0.0625 to preserve the same minimum effective tile size as
// the old 16×0.25=4px floor — large worlds in small frames still fit.
const BASE_TILE_PX = 64;
const ZOOM_MIN = 0.0625;
const ZOOM_MAX = 4.0;
// A press that moves fewer than this many pixels total is treated as a
// click, not a drag — avoids eating clicks whose pointer jittered a px.
const CLICK_DRAG_THRESHOLD = 4;
// Inset so the fitted world doesn't kiss the frame edge.
const FIT_PAD = 24;

function pixelToTile(
  px: number, py: number,
  snap: { cameraX: number; cameraY: number; tilePx: number },
): { x: number; y: number } {
  return {
    x: Math.floor((px - snap.cameraX) / snap.tilePx),
    y: Math.floor((py - snap.cameraY) / snap.tilePx),
  };
}

interface HoverState {
  agent: Agent;
  colony: Colony | undefined;
  screenX: number;
  screenY: number;
}

export function WorldCanvas() {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<Renderer | null>(null);
  const rafRef = useRef<number | null>(null);
  const snapRef = useRef<FrameSnapshot | null>(null);
  const dragRef = useRef<{
    active: boolean;
    startX: number;
    startY: number;
    lastX: number;
    lastY: number;
    totalMoved: number;
  } | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);
  const lastMoveTsRef = useRef(0);
  // Track whether the user has manually adjusted the view (wheel-zoom
  // *or* pan) since the last world-load. If they have, don't clobber
  // their view when the frame resizes — only auto-fit on world change.
  // Both wheel and pan flip this flag; they're symmetric forms of
  // "user changed the camera" and should be treated the same way.
  const userAdjustedRef = useRef(false);
  // Record the world id so we can distinguish "same world, user zoomed"
  // from "new world, re-fit". Signature includes seed so that two
  // generations with identical dims but different seeds count as new
  // worlds. If the user regenerates with *identical* inputs (same
  // seed + same dims) the world is byte-for-byte the same, so keeping
  // their view is correct.
  const fittedWorldSigRef = useRef<string | null>(null);
  // Tracks the last server_time_ms we pushed into the renderer's
  // interpolation buffer. Without this, any change in the snap-building
  // useEffect deps (zoom, pan, selection) re-pushes the same snapshot
  // and evicts the older one — InterpBuffer ends up holding two copies
  // of the same instant, span=0, and every agent snaps to target until
  // the next genuine tick arrives. Dedup by server timestamp here.
  const lastIngestedServerMsRef = useRef<number>(-1);
  // Per-agent recent d20 roll tracker. Populated from incoming `foraged`
  // events; the renderer flashes a chip above the agent for a short
  // window after each roll. Stored in a ref because the data is purely
  // visual feedback — no need to reactively re-render React on every
  // poll/SSE message; the rAF loop will pick up fresh values via the
  // FrameSnapshot we hand to drawFrame.
  const recentForageRollsRef = useRef<Map<number, { roll: number; receivedAtMs: number; tick: number }>>(new Map());

  const sim = useSimulation();
  const world = useWorld();
  const agents = useAgents();
  const colonies = useColonies();
  const { snapshot: streamSnap } = useWorldStream();
  const zoom = useViewStore((s) => s.zoom);
  const cameraX = useViewStore((s) => s.cameraX);
  const cameraY = useViewStore((s) => s.cameraY);
  const selectedAgentId = useViewStore((s) => s.selectedAgentId);
  const selectedTile = useViewStore((s) => s.selectedTile);
  const pan = useViewStore((s) => s.pan);
  const setCamera = useViewStore((s) => s.setCamera);
  const setZoom = useViewStore((s) => s.setZoom);
  const selectAgent = useViewStore((s) => s.selectAgent);
  const selectTile = useViewStore((s) => s.selectTile);

  const tilePx = BASE_TILE_PX * zoom;

  // Keep the snapshot ref in sync with the latest server + view state.
  // Prefer SSE stream data when available; fall back to poll-based queries.
  useEffect(() => {
    if (!world.data) {
      snapRef.current = null;
      return;
    }
    const effectiveAgents = streamSnap?.agents ?? agents.data ?? [];
    const effectiveSim = streamSnap?.sim ?? sim.data;
    const effectiveColonies = streamSnap?.colonies ?? colonies.data ?? [];

    // Pull any new d20 forage rolls out of the event stream so the
    // renderer can flash a chip above the rolling agent. Dedup by
    // (agent_id, tick) — a single forage event may appear in
    // consecutive snapshots; without the dedup the chip's receivedAtMs
    // resets each poll and the chip "sticks" forever instead of fading.
    const events = streamSnap?.events ?? [];
    if (events.length > 0) {
      const nowMs = performance.now();
      for (const ev of events) {
        if (ev.type !== 'foraged' || ev.agent_id == null) continue;
        const data = ev.data as { roll?: number } | null | undefined;
        const roll = data?.roll;
        if (typeof roll !== 'number') continue;
        const prev = recentForageRollsRef.current.get(ev.agent_id);
        if (prev && prev.tick === ev.tick) continue;
        recentForageRollsRef.current.set(ev.agent_id, {
          roll,
          receivedAtMs: nowMs,
          tick: ev.tick,
        });
      }
    }

    snapRef.current = {
      width: world.data.width,
      height: world.data.height,
      tiles: world.data.tiles,
      agents: effectiveAgents,
      colonies: effectiveColonies,
      tilePx,
      cameraX,
      cameraY,
      selectedAgentId,
      selectedTile,
      // Re-read per snapshot update rather than once at mount —
      // the OS preference can toggle while the app is running, and
      // the extra matchMedia call is cheap.
      reducedMotion: isReducedMotion(),
      currentTick: effectiveSim?.tick ?? 0,
      serverNowMs: effectiveSim?.server_time_ms,
      phase: effectiveSim?.phase,
      recentForageRolls: recentForageRollsRef.current,
    };
    if (
      rendererRef.current
      && effectiveSim?.server_time_ms != null
      && effectiveSim.server_time_ms !== lastIngestedServerMsRef.current
    ) {
      lastIngestedServerMsRef.current = effectiveSim.server_time_ms;
      rendererRef.current.ingestSnapshot?.({
        serverTimeMs: effectiveSim.server_time_ms,
        tick: effectiveSim.tick,
        agents: effectiveAgents.map((a: { id: number; x: number; y: number }) => ({ id: a.id, x: a.x, y: a.y })),
      });
    }
  }, [world.data, agents.data, colonies.data, tilePx, cameraX, cameraY, selectedAgentId, selectedTile, sim.data, streamSnap]);

  // Auto-fit on world-load and observe-frame resize.
  useEffect(() => {
    if (!hostRef.current || !world.data) return;
    // .world-canvas wrapper fills .observe__frame via `position:absolute;
    // inset:0`, so its bounding rect === the stage dimensions. Measuring
    // this wrapper instead of the frame means the fit math doesn't depend
    // on ancestor CSS tricks we might forget about later.
    const frame = hostRef.current.parentElement;
    if (!frame) return;

    const fit = () => {
      const w = world.data!.width;
      const h = world.data!.height;
      // Seed is part of the signature so a regen with a different seed
      // but same dimensions is treated as a new world. `seed` is
      // user-nullable so coalesce to '∅' for a stable key.
      const sig = `${w}x${h}:${sim.data?.seed ?? '∅'}`;
      const frameRect = frame.getBoundingClientRect();
      const availW = Math.max(100, frameRect.width - FIT_PAD * 2);
      const availH = Math.max(100, frameRect.height - FIT_PAD * 2);
      const worldPxW = w * BASE_TILE_PX;
      const worldPxH = h * BASE_TILE_PX;
      const fitZoom = Math.min(availW / worldPxW, availH / worldPxH);
      const clampedZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, fitZoom));
      // On a new world (different sig), always re-fit. On the same
      // world, only auto-fit if the user hasn't manually zoomed.
      const newWorld = fittedWorldSigRef.current !== sig;
      if (newWorld) {
        userAdjustedRef.current = false;
        fittedWorldSigRef.current = sig;
      }
      if (!newWorld && userAdjustedRef.current) return;
      setZoom(clampedZoom);
      const tilePxFit = BASE_TILE_PX * clampedZoom;
      // Centre the world in the frame.
      setCamera(
        (frameRect.width - w * tilePxFit) / 2,
        (frameRect.height - h * tilePxFit) / 2,
      );
    };

    fit();
    const ro = new ResizeObserver(() => fit());
    ro.observe(frame);
    return () => ro.disconnect();
  }, [world.data, sim.data?.seed, setZoom, setCamera]);

  // Mount renderer once, start rAF loop, attach interaction listeners.
  useEffect(() => {
    if (!hostRef.current) return;
    const host = hostRef.current;
    const renderer = new Canvas2DRenderer();
    renderer.mount(host);
    rendererRef.current = renderer;

    const loop = () => {
      const snap = snapRef.current;
      if (snap && rendererRef.current) {
        const w = snap.width * snap.tilePx;
        const h = snap.height * snap.tilePx;
        rendererRef.current.resize(w, h);
        rendererRef.current.drawFrame(snap);
      }
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);

    const canvas = host.querySelector('canvas');
    if (!canvas) return;

    // Pointer events + setPointerCapture. The browser routes every
    // pointermove/pointerup to the capturing element until the pointer
    // is released, regardless of where it travels — even outside the
    // viewport, over the OS taskbar, or into another window. This
    // fully covers the "zombie drag" case: no more window-level
    // fallback listeners, no more blur-based guards. `lostpointercapture`
    // fires unconditionally when capture ends, so dragRef clears on
    // every terminating path (release, cancel, focus loss, drag-drop
    // sequence). See §9.29-F2 for the audit trail.
    const onPointerDown = (e: PointerEvent) => {
      setHover(null);               // drag-start cancels hover
      // Primary button only; ignore right-click/middle so they don't
      // start a pan that the user doesn't expect.
      if (e.button !== 0) return;
      canvas.setPointerCapture(e.pointerId);
      dragRef.current = {
        active: true,
        startX: e.clientX,
        startY: e.clientY,
        lastX: e.clientX,
        lastY: e.clientY,
        totalMoved: 0,
      };
    };

    const onPointerMove = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d || !d.active) return;
      const dx = e.clientX - d.lastX;
      const dy = e.clientY - d.lastY;
      d.lastX = e.clientX;
      d.lastY = e.clientY;
      d.totalMoved += Math.abs(dx) + Math.abs(dy);
      if (d.totalMoved > CLICK_DRAG_THRESHOLD) {
        pan(dx, dy);
        // Pan is a user adjustment — symmetric with wheel-zoom. Without
        // this, panning then resizing the frame would recentre the
        // camera and eat the user's pan.
        userAdjustedRef.current = true;
      }
    };

    const onPointerUp = (e: PointerEvent) => {
      const d = dragRef.current;
      dragRef.current = null;
      if (!d) return;
      if (d.totalMoved <= CLICK_DRAG_THRESHOLD) {
        const rect = canvas.getBoundingClientRect();
        const localX = e.clientX - rect.left;
        const localY = e.clientY - rect.top;
        const snap = snapRef.current;
        if (!snap) return;
        const worldX = (localX - snap.cameraX) / snap.tilePx;
        const worldY = (localY - snap.cameraY) / snap.tilePx;
        const hit = pickAgent(snap.agents, worldX, worldY);
        if (hit) {
          selectAgent(hit.id);
          return;
        }
        // Fallback: pick the tile under the cursor if it has something
        // worth inspecting (crop or food). Click on bare grass clears
        // any prior selection — empty click = deselect, same as agents.
        const tile = pickInspectableTile(snap, worldX, worldY);
        if (tile) {
          selectTile({ x: tile.x, y: tile.y });
        } else {
          selectAgent(null);
        }
      }
    };

    // lostpointercapture is the single source of truth for "drag is
    // over" — fires on pointerup AND on any implicit capture loss
    // (focus change, pointercancel, element removal). Clearing here
    // means a dragRef left behind by any terminating path gets reset.
    const onLostCapture = () => {
      dragRef.current = null;
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const localX = e.clientX - rect.left;
      const localY = e.clientY - rect.top;
      const snap = snapRef.current;
      if (!snap) return;
      const worldX = (localX - snap.cameraX) / snap.tilePx;
      const worldY = (localY - snap.cameraY) / snap.tilePx;
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      const { zoom: currentZoom } = useViewStore.getState();
      const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, currentZoom * factor));
      setZoom(newZoom);
      const newTilePx = BASE_TILE_PX * newZoom;
      setCamera(localX - worldX * newTilePx, localY - worldY * newTilePx);
      userAdjustedRef.current = true;
    };

    const onPointerMoveHover = (e: PointerEvent) => {
      if (dragRef.current) {
        setHover(null);
        return;
      }
      const now = performance.now();
      if (now - lastMoveTsRef.current < 16) return;    // ~60fps throttle
      lastMoveTsRef.current = now;

      const snap = snapRef.current;
      if (!snap) return;

      const rect = canvas.getBoundingClientRect();
      const localX = e.clientX - rect.left;
      const localY = e.clientY - rect.top;
      const tile = pixelToTile(localX, localY, snap);

      const agent = snap.agents.find(
        a => a.alive && a.x === tile.x && a.y === tile.y,
      );
      if (!agent) {
        setHover(null);
        return;
      }
      const colony = snap.colonies.find(c => c.id === agent.colony_id);
      setHover({
        agent,
        colony,
        screenX: e.clientX,
        screenY: e.clientY,
      });
    };

    const onPointerLeave = () => setHover(null);

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointermove', onPointerMoveHover);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onLostCapture);
    canvas.addEventListener('lostpointercapture', onLostCapture);
    canvas.addEventListener('pointerleave', onPointerLeave);
    canvas.addEventListener('wheel', onWheel, { passive: false });

    // selectTile is referenced inside onPointerUp; keep deps tracked.
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointermove', onPointerMoveHover);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointercancel', onLostCapture);
      canvas.removeEventListener('lostpointercapture', onLostCapture);
      canvas.removeEventListener('pointerleave', onPointerLeave);
      canvas.removeEventListener('wheel', onWheel);
      rendererRef.current?.dispose();
      rendererRef.current = null;
    };
  }, [pan, setCamera, setZoom, selectAgent, selectTile]);

  const status = useMemo(() => {
    if (world.isLoading || agents.isLoading) return 'loading world…';
    if (world.error || agents.error) {
      const err = world.error ?? agents.error;
      if (err instanceof ApiError && err.status === 404) return null; // empty-state hero handles this
      return 'connection error';
    }
    return null;
  }, [world.isLoading, agents.isLoading, world.error, agents.error]);

  return (
    <div className="world-canvas">
      <div
        ref={hostRef}
        className="world-canvas__host"
        role="img"
        aria-label="Colony simulation map — pan with drag, zoom with wheel, click to select an agent or tile"
      />
      {status && <div className="overlay">{status}</div>}
      {hover && (
        <AgentTooltip
          agent={hover.agent}
          colony={hover.colony}
          screenX={hover.screenX}
          screenY={hover.screenY}
        />
      )}
    </div>
  );
}

// Square hit-test against the agent body. Agents are drawn as circles
// centred on the tile centre; a hit region slightly larger than the
// body is generous without making nearby tiles clickable-through.
function pickAgent(
  list: { id: number; x: number; y: number; alive: boolean }[],
  worldX: number,
  worldY: number,
) {
  for (const a of list) {
    const cx = a.x + 0.5;
    const cy = a.y + 0.5;
    if (Math.abs(worldX - cx) < 0.45 && Math.abs(worldY - cy) < 0.45) {
      return a;
    }
  }
  return null;
}

// Tile picker for the inspector fallback: only tiles with a crop or a
// food resource are selectable. Plain grass/sand/stone tiles are not —
// clicking bare ground should deselect, not open an empty panel.
function pickInspectableTile(
  snap: FrameSnapshot,
  worldX: number,
  worldY: number,
) {
  if (worldX < 0 || worldY < 0) return null;
  const tx = Math.floor(worldX);
  const ty = Math.floor(worldY);
  if (tx >= snap.width || ty >= snap.height) return null;
  const row = snap.tiles[ty];
  if (!row) return null;
  const tile = row[tx];
  if (!tile) return null;
  const hasCrop = tile.crop_state !== 'none';
  const hasFood = tile.resource_type === 'food' && tile.resource_amount > 0;
  if (!hasCrop && !hasFood) return null;
  return tile;
}
