# Task: Wire a Project Membership Graph

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's unit-test tree we need a small "project membership" graph module that wires people, projects, and a self-referential team hierarchy on the shared test `Sequelize` instance. Unit tests in this package run against the default dialect without opening a real database connection, so the relationships and their generated accessors/foreign keys can all be inspected in-process.

## Files to Create/Modify
- `packages/core/test/unit/associations/project-membership.ts` (new) — the module that defines and wires the models and exports a factory.
- `packages/core/test/unit/associations/project-membership.test.ts` (new) — the unit test that exercises the wiring.

## Requirements

### Module shape
- The module must export a single function `defineMembership(sequelize)` that accepts a `Sequelize` instance, defines all models and their relationships on it, and returns `{ Person, Project, Team }`.
- Everything must be defined on the passed-in instance only; two separate calls on two distinct instances must yield fully independent model sets.

### Models
- **Person** — fields: `username` (text, required, unique).
- **Project** — fields: `name` (text, required).
- **Team** — fields: `name` (text, required).

### Relationships
- A **Person** may participate in many **Projects** and a **Project** may have many **People**, linked through a junction relation named `Memberships`. From a person, the related projects must be reachable under the accessor name `projects`; from a project, the related people must be reachable under the accessor name `members`.
- A **Team** is self-referential: a team may have many child teams and at most one parent team. The children must be reachable under the accessor name `childTeams` and the parent under the accessor name `parentTeam`. The foreign key linking a child team to its parent must be the column `parentTeamId`.
- Each **Project** belongs to exactly one owning **Team**, and a **Team** may own many **Projects**. The owning team must be reachable from a project under the accessor name `owningTeam`, and the projects from a team under the accessor name `ownedProjects`. The foreign key must be the column `owningTeamId`.

### Edge cases and constraints
- Self-association on **Team** must not collide: the parent and child accessors must both exist and be distinct.
- The junction relation must produce working association accessors on both `Person` and `Project`.
- A naive implementation that defines models but skips wiring the relationships must fail the tests.

### Expected Functionality
- Inspecting `Person` associations -> a `projects` association targeting `Project` routed through `Memberships`.
- Inspecting `Project` associations -> a `members` association targeting `Person` routed through `Memberships`, and an `owningTeam` association targeting `Team` with foreign key `owningTeamId`.
- Inspecting `Team` associations -> a `childTeams` association and a `parentTeam` association both targeting `Team`, with the child→parent link using foreign key `parentTeamId`; plus an `ownedProjects` association targeting `Project`.

## Acceptance Criteria
- A new self-contained unit test `packages/core/test/unit/associations/project-membership.test.ts` exists and asserts: the person↔project many-to-many (accessor names + junction), the team self-reference (both accessor names + `parentTeamId`), and the project↔team ownership (accessor names + `owningTeamId`).
- The implementation lives in `packages/core/test/unit/associations/project-membership.ts` and is imported by the test.
- All assertions are objectively verifiable in-process without a live database server.
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/unit/associations/project-membership.test.ts"
  ```
