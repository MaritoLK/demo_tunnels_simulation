# TUNNELS — Project Brief & Architecture Spec

## How We Work Together (READ THIS FIRST)

**Mauro is the developer. You are the mentor.** This is Mauro's personal project for a job interview and he needs to own every line of code — he will be presenting it and answering technical questions on it. Your role is to accelerate him, not replace him.

### Rules of engagement:
1. **Never write complete files or large blocks of code unprompted.** Instead, explain what needs to be built, why, and guide Mauro to write it himself.
2. **Explain the reasoning first.** Before any implementation step, explain *why* we're doing it this way — the design pattern, the trade-off, the alternative we're not choosing. Mauro learns by understanding the reasoning.
3. **Ask Mauro to make decisions.** When there's a genuine choice (e.g., "should agents prioritise hunger or energy when both are critical?"), present the options and let Mauro decide. Don't pick for him.
4. **Review his code, don't rewrite it.** When Mauro writes something, review it — point out issues, suggest improvements, explain edge cases. If something is wrong, explain why and let him fix it.
5. **Provide small code snippets only when asked**, or when demonstrating a specific pattern or syntax he hasn't seen before (e.g., "here's how SQLAlchemy relationships work"). Keep snippets short — 5-15 lines max.
6. **Follow the build order at the bottom of this document.** Don't skip ahead. Each step should be working and tested before moving to the next.
7. **Keep Mauro focused.** If he's going down a rabbit hole or over-engineering something, say so. The goal is a working MVP in 2 days, not a perfect system.
8. **Check understanding.** After explaining a concept, ask Mauro to explain it back or describe how he'd implement it before he starts coding. This ensures he can talk about it confidently in the interview.

### When Mauro asks for help:
- If he's stuck on syntax → give him the specific line or pattern
- If he's stuck on architecture → explain the options and trade-offs, let him choose
- If he's stuck on a bug → ask him what he's tried first, then guide him to the fix
- If he asks "just write it for me" → write it, but then walk through every line and make sure he understands it fully

### The interview context:
Mauro has an in-person interview at BUUK Infrastructure (a UK utilities company) where he must present this project for 15-30 minutes and answer questions on it. He's applying for a Senior Systems Developer role (Python/PostgreSQL/Flask/React). Every architectural decision in this project maps to skills on the job description. He needs to be able to explain: why the engine is decoupled from Flask, why events use JSONB, why polling instead of WebSockets, what indexes he chose and why, and how the system would scale.

---

## Overview
A real-time agent-based colony simulation. Autonomous agents spawn into a procedurally generated grid world, have needs that decay over time, make decisions based on a priority system, and produce emergent behaviour. The project demonstrates full-stack engineering: Flask API, PostgreSQL persistence, React canvas frontend, Docker Compose orchestration, GitHub Actions CI/CD, deployed to a live URL.

## Tech Stack
- **Backend**: Python 3.12, Flask, SQLAlchemy, python-dotenv
- **Database**: PostgreSQL 16 with PostGIS (for future spatial queries)
- **Frontend**: React 18 (Vite), HTML5 Canvas for grid rendering, Tailwind CSS
- **Containerisation**: Docker Compose (Flask, PostgreSQL, Nginx, React build)
- **CI/CD**: GitHub Actions (lint, test, build, deploy)
- **Deployment**: VPS (DigitalOcean/Hetzner) or similar cheap Linux box

---

## Project Structure

```
tunnels/
├── docker-compose.yml
├── .github/
│   └── workflows/
│       └── ci.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py          # Flask app factory
│   │   ├── config.py            # Environment-based config
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   ├── world.py
│   │   │   └── event.py
│   │   ├── routes/              # Flask blueprints (HTTP layer)
│   │   │   ├── __init__.py
│   │   │   ├── simulation.py    # /api/simulation/* endpoints
│   │   │   ├── agents.py        # /api/agents/* endpoints
│   │   │   └── world.py         # /api/world/* endpoints
│   │   ├── services/            # Business logic (no HTTP awareness)
│   │   │   ├── __init__.py
│   │   │   ├── simulation_service.py   # Tick loop, orchestration
│   │   │   ├── agent_service.py        # Agent decision-making
│   │   │   └── world_service.py        # World generation, tile queries
│   │   ├── engine/              # Core simulation engine (pure Python, no Flask dependency)
│   │   │   ├── __init__.py
│   │   │   ├── agent.py         # Agent class with state machine
│   │   │   ├── world.py         # World grid class
│   │   │   ├── actions.py       # Action definitions and resolution
│   │   │   └── needs.py         # Needs system (hunger, energy, social)
│   │   └── integrations/        # External system clients
│   │       ├── __init__.py
│   │       └── database.py      # DB session management
│   └── tests/
│       ├── test_engine.py       # Unit tests for simulation logic
│       ├── test_services.py     # Service layer tests
│       └── test_routes.py       # API endpoint tests
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx              # Main layout: grid + sidebar
│       ├── components/
│       │   ├── WorldCanvas.jsx  # HTML5 Canvas grid renderer
│       │   ├── AgentPanel.jsx   # Selected agent info
│       │   ├── EventLog.jsx     # Scrolling event feed
│       │   └── Controls.jsx     # Play/pause/speed/reset buttons
│       ├── hooks/
│       │   └── useSimulation.js # Polling hook for world state
│       └── api/
│           └── client.js        # Fetch wrapper for Flask API
├── nginx/
│   └── nginx.conf               # Reverse proxy config
└── README.md
```

---

## Database Schema

### agents
```sql
CREATE TABLE agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'idle',  -- idle, foraging, resting, exploring, socialising, dead
    hunger FLOAT NOT NULL DEFAULT 100.0,         -- 0-100, 0 = starvation
    energy FLOAT NOT NULL DEFAULT 100.0,         -- 0-100, 0 = exhaustion
    social FLOAT NOT NULL DEFAULT 100.0,         -- 0-100, 0 = isolation
    health FLOAT NOT NULL DEFAULT 100.0,         -- 0-100, 0 = death
    age INTEGER NOT NULL DEFAULT 0,              -- ticks alive
    alive BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_agents_alive ON agents (alive) WHERE alive = TRUE;
CREATE INDEX idx_agents_position ON agents (x, y);
```

### world_tiles
```sql
CREATE TABLE world_tiles (
    id SERIAL PRIMARY KEY,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    terrain VARCHAR(20) NOT NULL,       -- grass, water, forest, stone, sand
    resource_type VARCHAR(20),           -- food, wood, stone, null
    resource_amount FLOAT DEFAULT 0.0,   -- depletes when gathered, regenerates slowly
    UNIQUE(x, y)
);
CREATE INDEX idx_tiles_position ON world_tiles (x, y);
CREATE INDEX idx_tiles_resource ON world_tiles (resource_type) WHERE resource_type IS NOT NULL;
```

### events
```sql
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    tick INTEGER NOT NULL,
    agent_id INTEGER REFERENCES agents(id),
    event_type VARCHAR(30) NOT NULL,    -- moved, foraged, rested, socialised, starved, died, born
    description TEXT,
    data JSONB,                          -- flexible payload (e.g., {"from": [2,3], "to": [3,3], "hunger_before": 45.2})
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_events_tick ON events (tick);
CREATE INDEX idx_events_agent ON events (agent_id);
CREATE INDEX idx_events_type ON events (event_type);
```

### simulation_state
```sql
CREATE TABLE simulation_state (
    id SERIAL PRIMARY KEY,
    current_tick INTEGER NOT NULL DEFAULT 0,
    running BOOLEAN NOT NULL DEFAULT FALSE,
    speed FLOAT NOT NULL DEFAULT 1.0,     -- ticks per second
    world_width INTEGER NOT NULL,
    world_height INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## Simulation Engine Rules

### World Generation
- Grid size: 40x40 (configurable)
- Terrain types distributed via simple noise: ~60% grass, ~15% forest, ~10% water (impassable), ~10% stone, ~5% sand
- Food spawns on grass tiles (random, ~30% of grass tiles start with food)
- Wood available on forest tiles
- Stone available on stone tiles
- Resources regenerate slowly (1 unit per 20 ticks on depleted food tiles)

### Agent Needs (decay per tick)
- **Hunger**: -0.5 per tick. At 0, health drops -2.0 per tick. Eating food restores +30.
- **Energy**: -0.3 per tick. At 0, agent forced into resting state. Resting restores +5.0 per tick.
- **Social**: -0.1 per tick. At 0, no immediate penalty but affects decision weights. Socialising with adjacent agent restores +20.
- **Health**: Only decays from starvation or exhaustion. At 0, agent dies. Does not regenerate (for MVP).

### Agent Decision Tree (evaluated each tick)
Priority-based, highest priority wins:
1. **Health critical** (health < 20): rest if energy low, otherwise forage desperately (search radius doubles)
2. **Hunger critical** (hunger < 20): forage — find nearest food tile, move toward it, gather if adjacent
3. **Energy critical** (energy < 15): rest in place for 3-5 ticks
4. **Hunger moderate** (hunger < 50): forage
5. **Social low** (social < 30): move toward nearest agent, socialise if adjacent
6. **Default**: explore — move to a random adjacent walkable tile

### Movement
- Agents move 1 tile per tick (cardinal directions only: N/S/E/W)
- Water tiles are impassable
- Pathfinding: simple greedy (move toward target, avoid water). No A* needed for MVP.
- If target tile is occupied by another agent, stay in place or pick alternative

### Actions
- **Forage**: must be adjacent to a food tile with resource_amount > 0. Takes 1 tick. Reduces tile resource by 5, increases agent hunger by 30.
- **Rest**: agent stays in place. Takes 1 tick. Increases energy by 5.
- **Socialise**: must be adjacent to another living agent. Takes 1 tick. Both agents gain +20 social.
- **Explore**: move to random adjacent walkable tile.
- **Die**: when health reaches 0. Agent marked as dead, death event logged.

---

## API Endpoints

### Simulation Control
```
POST   /api/simulation/start          # Begin or resume simulation loop
POST   /api/simulation/pause          # Pause simulation
POST   /api/simulation/reset          # Reset world and agents
POST   /api/simulation/tick           # Advance one tick manually
GET    /api/simulation/state          # Current tick, running status, agent count, speed
PATCH  /api/simulation/speed          # { "speed": 2.0 } — change tick rate
```

### World State
```
GET    /api/world/state               # Full grid state (tiles + agent positions) for canvas rendering
GET    /api/world/tile/:x/:y          # Single tile details
GET    /api/world/stats               # Aggregate stats (total food, total agents alive, etc.)
```

### Agents
```
GET    /api/agents                    # List all living agents with current state
GET    /api/agents/:id                # Single agent details including needs
GET    /api/agents/:id/history        # Event history for a specific agent
```

### Events
```
GET    /api/events?tick=100&limit=50  # Recent events, filterable by tick range and type
GET    /api/events/summary            # Aggregate event counts by type for last N ticks
```

---

## API Response Format

### GET /api/world/state (called every 500ms by frontend)
```json
{
    "tick": 142,
    "running": true,
    "world": {
        "width": 40,
        "height": 40,
        "tiles": [
            {"x": 0, "y": 0, "terrain": "grass", "resource_type": "food", "resource_amount": 12.0},
            {"x": 1, "y": 0, "terrain": "water", "resource_type": null, "resource_amount": 0}
        ]
    },
    "agents": [
        {"id": 1, "name": "Agent-001", "x": 5, "y": 12, "state": "foraging", "hunger": 34.2, "energy": 78.0, "social": 65.0, "health": 100.0, "alive": true}
    ],
    "recent_events": [
        {"tick": 142, "agent_id": 1, "event_type": "foraged", "description": "Agent-001 gathered food at (5, 13)"}
    ]
}
```

Note: For performance, the /api/world/state endpoint should be optimised. Consider:
- Only sending tiles that have changed since last requested tick (delta updates)
- Or compressing the tile array into a flat format the frontend can parse quickly
- For MVP, sending the full state is fine for a 40x40 grid (1600 tiles + ~15 agents)

---

## Frontend Components

### WorldCanvas.jsx
- HTML5 Canvas, each tile = 16x16 pixels (40*16 = 640px square grid)
- Colour map: grass=#4ade80, forest=#166534, water=#3b82f6, stone=#9ca3af, sand=#fbbf24
- Food overlay: small yellow dot on tiles with food
- Agents: coloured circles (alive=white with state-coloured border, dead=red X)
- Click on agent to select → shows details in AgentPanel
- Smooth: requestAnimationFrame for rendering, polls /api/world/state every 500ms

### AgentPanel.jsx
- Shows selected agent's name, state, needs bars (hunger/energy/social/health as coloured bars)
- Shows agent's current action and age (ticks alive)

### EventLog.jsx
- Scrolling list of recent events, newest at top
- Colour-coded by type: death=red, foraged=green, socialised=blue, etc.
- Filterable by event type

### Controls.jsx
- Play / Pause button
- Speed slider (0.5x to 5x)
- Step (advance 1 tick manually)
- Reset button

---

## Docker Compose

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: tunnels
      POSTGRES_USER: tunnels
      POSTGRES_PASSWORD: ${DB_PASSWORD:-tunnels_dev}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tunnels"]
      interval: 5s
      timeout: 3s
      retries: 5

  flask:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://tunnels:${DB_PASSWORD:-tunnels_dev}@db:5432/tunnels
      FLASK_ENV: ${FLASK_ENV:-development}
    ports:
      - "5000:5000"
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend:/app  # hot reload in dev

  react:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - flask
    volumes:
      - ./frontend:/app
      - /app/node_modules

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - flask
      - react

volumes:
  pgdata:
```

---

## GitHub Actions CI Pipeline

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: tunnels_test
          POSTGRES_USER: tunnels
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r backend/requirements.txt
      - run: cd backend && python -m pytest tests/ -v
        env:
          DATABASE_URL: postgresql://tunnels:test@localhost:5432/tunnels_test

  frontend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: cd frontend && npm ci && npm run lint

  docker-build:
    runs-on: ubuntu-latest
    needs: [backend-test, frontend-lint]
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build
```

---

## Simulation Loop (Backend)

The simulation runs as a background thread in the Flask process (for MVP). On each tick:

```python
# Pseudocode for simulation_service.py
def run_tick(world, agents, tick_number):
    events = []
    
    # 1. Decay all agent needs
    for agent in agents:
        if not agent.alive:
            continue
        agent.hunger = max(0, agent.hunger - 0.5)
        agent.energy = max(0, agent.energy - 0.3)
        agent.social = max(0, agent.social - 0.1)
        
        # Starvation damage
        if agent.hunger <= 0:
            agent.health = max(0, agent.health - 2.0)
        
        # Exhaustion check
        if agent.energy <= 0:
            agent.state = 'resting'
        
        # Death check
        if agent.health <= 0:
            agent.alive = False
            agent.state = 'dead'
            events.append(Event(tick=tick_number, agent_id=agent.id, event_type='died', description=f'{agent.name} has died'))
            continue
        
        # 2. Agent makes decision
        action = decide_action(agent, world, agents)
        
        # 3. Execute action
        result = execute_action(agent, action, world, agents)
        events.append(result.event)
        
        # 4. Increment age
        agent.age += 1
    
    # 5. Resource regeneration
    regenerate_resources(world, tick_number)
    
    # 6. Persist state and events
    save_state(world, agents, events, tick_number)
    
    return events
```

---

## Key Design Decisions to Explain in Interview

1. **Engine decoupled from Flask**: The `engine/` package has zero Flask imports. It's pure Python. You could run the simulation from a CLI, a test, or a different web framework. This is deliberate — the simulation logic should be testable in isolation.

2. **Three-layer architecture**: Routes handle HTTP, services handle orchestration, engine handles domain logic. A route never touches the database directly or makes a decision about agent behaviour.

3. **Event sourcing pattern**: Every action generates an event stored in the database with a JSONB payload. This means you can replay history, generate narratives, build analytics, and debug behaviour — all from the event log. This is the foundation for future Gemma integration (feed events to Gemma, get narrative back).

4. **Background thread for simulation loop**: For MVP, a simple threading.Thread runs the tick loop. In production you'd use Celery or similar. Mention this trade-off — it shows you know the limitation and the proper solution.

5. **Polling vs WebSocket**: Frontend polls every 500ms for simplicity. Acknowledge that WebSocket would be better for real-time and explain why you chose polling (faster to implement, sufficient for demo, and you can always swap it later because the API contract stays the same).

6. **Extensibility for future features**: The agent decision tree is a function that can be swapped for a behaviour tree, utility AI, or LLM-based decision-making. The event system enables narrative generation. The tile/resource system supports new resource types. The agent model supports new needs. None of these require architectural changes — just additions.

---

## Future Vision (Talk About at Interview)

- **Custom civilisations**: agents grouped by civ_id, each civ has traits (e.g., "efficient foragers" = -20% hunger decay, "builders" = can construct shelters)
- **Hero units**: named agents with unique abilities and skill trees
- **Buildings**: agents can construct shelters (restore health), farms (produce food), walls (block movement)
- **Inter-civ interaction**: trade, diplomacy, conflict
- **Gemma integration**: 
  - Narrator: reads event log and generates a story each epoch
  - Advisor: chat interface where you ask "Why did Agent-007 die?" and Gemma queries the event history
  - Decision-making: complex agents consult Gemma for ambiguous situations
- **Customisation UI**: players design their own civs, set trait points, name their heroes

---

## Getting Started with Claude Code

Suggested order of implementation:

1. Set up project structure and Docker Compose (get all services running)
2. Database models and migrations (SQLAlchemy models, create tables)
3. Engine: World class with procedural generation
4. Engine: Agent class with needs and decision tree
5. Engine: Simulation tick loop
6. Flask routes: world state, simulation control, agent endpoints
7. Services: wire engine to database persistence
8. Tests: engine unit tests (agent decisions, need decay, death conditions)
9. Frontend: WorldCanvas with polling
10. Frontend: Controls, AgentPanel, EventLog
11. GitHub Actions CI
12. Deploy

Each step is independently testable. Don't move to step N+1 until step N works.
