import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// Sprite atlas imports the tiny-swords PNG pack from ../assets, which is
// gitignored (itch.io pack, not redistributable in-repo). CI checkout
// therefore lacks the files, and vite's import-analysis fails at transform
// time before any test runs. Stub the module so the renderer sees
// `sprites === null` and exercises the procedural fallback path — which
// is already the code path the render tests rely on in jsdom.
vi.mock('../render/spriteAtlas', () => ({
  loadSprites: () => new Promise(() => {}),
}));

afterEach(() => {
  cleanup();
});
