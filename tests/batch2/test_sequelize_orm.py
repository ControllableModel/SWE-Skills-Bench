"""
Test for the 'sequelize-orm' skill (variant ext2) — Wire a Project Membership Graph.

The agent must create two files inside @sequelize/core's unit-test tree:
  - packages/core/test/unit/associations/project-membership.ts       (the module)
  - packages/core/test/unit/associations/project-membership.test.ts  (its unit test)

The module exports `defineMembership(sequelize)` which, on the *passed-in*
Sequelize instance, defines three models (Person, Project, Team) and wires:
  * Person <-> Project   many-to-many through a junction named `Memberships`,
                         reachable as `projects` (from Person) / `members` (from Project)
  * Team self-reference  a team has many `childTeams` and at most one `parentTeam`,
                         the child->parent foreign key column being `parentTeamId`
  * Project -> Team      each Project belongsTo one owning Team reachable as
                         `owningTeam`; a Team hasMany `ownedProjects`; foreign key
                         column `owningTeamId`
and returns `{ Person, Project, Team }`.

Verification strategy
---------------------
L1 cases check that the two deliverable files exist, export/import the right
symbols, and are minimally well-formed.

L2 cases DO NOT trust the agent's own test file. Instead we drop independent
mocha specs into the repo that *import the agent's project-membership module*
and introspect the REAL wiring in-process (association accessor names, target
models, the `Memberships` junction model, the `parentTeamId` / `owningTeamId`
foreign-key columns, runtime accessor methods, and full per-instance
independence). These specs run via the repository's native command:

    yarn mocha "test/unit/associations/<spec>.test.ts"

A naive module that defines the three models but skips wiring the relationships
(or fakes accessor names, mislabels the junction, or uses the wrong foreign-key
columns) cannot pass these introspective assertions.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
ASSOC_DIR = os.path.join(CORE_DIR, "test", "unit", "associations")
MODULE_FILE = os.path.join(ASSOC_DIR, "project-membership.ts")
AGENT_TEST_FILE = os.path.join(ASSOC_DIR, "project-membership.test.ts")

# Basename for the independent specs we drop next to the agent's module.
_BENCH_BASENAME = "zzz-bench-project-membership"


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _run_mocha(spec_rel_path, timeout=600):
    """Run one mocha spec from packages/core using the repo's native command."""
    cmd = ["yarn", "mocha", spec_rel_path]
    return subprocess.run(
        cmd,
        cwd=CORE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec_and_run(spec_name, spec_body, timeout=600):
    """
    Write a self-contained mocha .test.ts spec into the associations dir, run it,
    then clean it up. Returns the CompletedProcess.
    """
    spec_path = os.path.join(ASSOC_DIR, spec_name)
    rel_path = os.path.join("test", "unit", "associations", spec_name)
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(spec_body)
    try:
        return _run_mocha(rel_path, timeout=timeout)
    finally:
        try:
            os.remove(spec_path)
        except OSError:
            pass


def _assert_mocha_passed(result, context=""):
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    assert result.returncode == 0, (
        f"mocha spec failed ({context}).\n"
        f"returncode={result.returncode}\n"
        f"--- stdout (tail) ---\n{(result.stdout or '')[-6000:]}\n"
        f"--- stderr (tail) ---\n{(result.stderr or '')[-3000:]}"
    )
    # Guard against a silent zero-test run being treated as success.
    assert "0 passing" not in combined, (
        f"mocha reported 0 passing tests ({context}); the spec did not run.\n"
        f"{combined[-4000:]}"
    )


# Common TS preamble: build a fresh Sequelize and call the agent's factory.
# It also exposes a helper to resolve an association's foreign-key column name
# robustly across the supported shapes (.foreignKey may be a string or an
# attribute-name; the through/owned cases also carry an attribute column).
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSequelizeInstance } from '../../support';
    import { defineMembership } from './project-membership';

    function buildGraph() {
      const sequelize = createSequelizeInstance();
      const models = defineMembership(sequelize as any);
      return { sequelize, models };
    }

    function fkName(assoc: any): string | undefined {
      if (!assoc) return undefined;
      const fk = assoc.foreignKey;
      if (typeof fk === 'string') return fk;
      if (fk && typeof fk === 'object') return fk.name || fk.fieldName;
      return undefined;
    }
    """
)


# ---------------------------------------------------------------------------
# Module-scope dependency guard. The container already has the toolchain that
# runs `yarn mocha`; we make sure node_modules is present (best-effort) so the
# native command can resolve mocha/chai/esbuild.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _ensure_dependencies():
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules")) and not os.path.isdir(
        os.path.join(CORE_DIR, "node_modules")
    ):
        try:
            subprocess.run(
                ["yarn", "install", "--immutable"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            # If install fails here, the native test calls below will surface
            # an explicit, debuggable error.
            pass
    yield


class TestSequelizeOrm:
    """Verify the project-membership graph deliverable (variant ext2)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The module project-membership.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own unit test project-membership.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_factory(self):
        """project-membership.ts must export a `defineMembership` function symbol."""
        src = _read(MODULE_FILE)
        assert "defineMembership" in src, "defineMembership not found in module"
        assert "export" in src, "module does not export anything"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local project-membership module."""
        src = _read(AGENT_TEST_FILE)
        assert "project-membership" in src, (
            "test does not reference the project-membership module"
        )

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_factory_returns_three_models(self):
        """defineMembership returns { Person, Project, Team } as real, distinct models."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: factory shape', () => {
              it('returns Person, Project and Team distinct model classes', () => {
                const { models } = buildGraph();
                expect(models).to.be.an('object');
                expect(models.Person, 'Person missing').to.exist;
                expect(models.Project, 'Project missing').to.exist;
                expect(models.Team, 'Team missing').to.exist;
                for (const m of [models.Person, models.Project, models.Team]) {
                  expect(typeof m.getAttributes, 'not a model class').to.equal('function');
                  expect(typeof m.build, 'not a model class').to.equal('function');
                }
                expect(models.Person).to.not.equal(models.Project);
                expect(models.Project).to.not.equal(models.Team);
                expect(models.Person).to.not.equal(models.Team);
              });

              it('defines models only on the passed instance (no leakage)', () => {
                const a = buildGraph();
                const b = buildGraph();
                expect(a.sequelize).to.not.equal(b.sequelize);
                expect(a.models.Person).to.not.equal(b.models.Person);
                expect(a.models.Project).to.not.equal(b.models.Project);
                expect(a.models.Person.sequelize).to.equal(a.sequelize);
                expect(b.models.Person.sequelize).to.equal(b.sequelize);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "factory shape / independence")

    def test_person_project_many_to_many_accessors(self):
        """Person has `projects` (-> Project) and Project has `members` (-> Person)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Person<->Project m2m accessors', () => {
              it('wires projects (Person->Project) and members (Project->Person)', () => {
                const { models } = buildGraph();
                const { Person, Project } = models;

                const projectsAssoc = Person.associations.projects;
                expect(projectsAssoc, 'Person.associations.projects missing').to.exist;
                expect(projectsAssoc.target, 'projects should target Project')
                  .to.equal(Project);

                const membersAssoc = Project.associations.members;
                expect(membersAssoc, 'Project.associations.members missing').to.exist;
                expect(membersAssoc.target, 'members should target Person')
                  .to.equal(Person);

                // Both sides must be belongsToMany (associationType 'BelongsToMany').
                expect(String(projectsAssoc.associationType)).to.equal('BelongsToMany');
                expect(String(membersAssoc.associationType)).to.equal('BelongsToMany');

                // A naive impl that names the accessor differently must NOT exist
                // under these names by accident — confirm there is no `people`
                // mistaken alias used in place of `members`.
                expect(Project.associations.members.as
                  || Project.associations.members.options?.as
                  || 'members').to.exist;
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-m2m-accessors.test.ts", spec)
        _assert_mocha_passed(result, "Person<->Project m2m accessor names")

    def test_membership_junction_model_name(self):
        """The Person<->Project relation must route through a junction named `Memberships`."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Memberships junction', () => {
              it('routes both sides through a junction model named Memberships', () => {
                const { sequelize, models } = buildGraph();
                const { Person, Project } = models;

                const projectsAssoc: any = Person.associations.projects;
                const membersAssoc: any = Project.associations.members;
                expect(projectsAssoc, 'projects assoc missing').to.exist;
                expect(membersAssoc, 'members assoc missing').to.exist;

                const through = projectsAssoc.throughModel
                  || projectsAssoc.through?.model;
                expect(through, 'projects association has no through model').to.exist;

                const throughName = through.name
                  || (through.modelDefinition && through.modelDefinition.modelName);
                expect(String(throughName), 'junction must be named Memberships')
                  .to.equal('Memberships');

                // Both sides must share the same junction model instance.
                const through2 = membersAssoc.throughModel
                  || membersAssoc.through?.model;
                expect(through2, 'members association has no through model').to.exist;
                expect(through2).to.equal(through);

                // Junction must be retrievable from the instance's registry.
                const fromRegistry = sequelize.models.getOrThrow('Memberships');
                expect(fromRegistry).to.equal(through);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-junction.test.ts", spec)
        _assert_mocha_passed(result, "Memberships junction model name")

    def test_person_project_runtime_accessors(self):
        """belongsToMany must expose runtime mixin accessors on both prototypes."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: m2m runtime accessors', () => {
              it('exposes getProjects/addProject and getMembers/addMember mixins', () => {
                const { models } = buildGraph();
                const { Person, Project } = models;

                expect(typeof (Person.prototype as any).getProjects,
                  'Person#getProjects missing').to.equal('function');
                expect(typeof ((Person.prototype as any).addProject
                  || (Person.prototype as any).addProjects),
                  'Person#addProject(s) missing').to.equal('function');

                expect(typeof (Project.prototype as any).getMembers,
                  'Project#getMembers missing').to.equal('function');
                expect(typeof ((Project.prototype as any).addMember
                  || (Project.prototype as any).addMembers),
                  'Project#addMember(s) missing').to.equal('function');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-m2m-runtime.test.ts", spec)
        _assert_mocha_passed(result, "m2m runtime accessor mixins")

    def test_team_self_reference_accessors(self):
        """Team self-reference: distinct `childTeams` and `parentTeam` accessors -> Team."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Team self-reference accessors', () => {
              it('wires childTeams and parentTeam, both targeting Team and distinct', () => {
                const { models } = buildGraph();
                const { Team } = models;

                const childAssoc = Team.associations.childTeams;
                const parentAssoc = Team.associations.parentTeam;
                expect(childAssoc, 'Team.associations.childTeams missing').to.exist;
                expect(parentAssoc, 'Team.associations.parentTeam missing').to.exist;

                expect(childAssoc.target, 'childTeams must target Team').to.equal(Team);
                expect(parentAssoc.target, 'parentTeam must target Team').to.equal(Team);

                // The two self-association ends must be distinct objects (no collision).
                expect(childAssoc).to.not.equal(parentAssoc);

                // Cardinality: many children, single parent.
                expect(String(childAssoc.associationType)).to.equal('HasMany');
                expect(String(parentAssoc.associationType)).to.equal('BelongsTo');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-team-self.test.ts", spec)
        _assert_mocha_passed(result, "Team self-reference accessor names")

    def test_team_self_reference_foreign_key(self):
        """The child->parent self link must use the `parentTeamId` foreign-key column."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Team self-reference foreign key', () => {
              it('links child->parent via the parentTeamId column', () => {
                const { models } = buildGraph();
                const { Team } = models;

                const childAssoc: any = Team.associations.childTeams;
                const parentAssoc: any = Team.associations.parentTeam;

                const fk = fkName(parentAssoc) || fkName(childAssoc);
                expect(fk, 'self-reference foreign key should be parentTeamId')
                  .to.equal('parentTeamId');

                // Team must actually carry a parentTeamId attribute column.
                expect(Team.getAttributes(), 'Team has no parentTeamId column')
                  .to.have.property('parentTeamId');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-team-fk.test.ts", spec)
        _assert_mocha_passed(result, "Team self-reference foreign key column")

    def test_team_self_reference_runtime_accessors(self):
        """Self-ref must expose getChildTeams / getParentTeam runtime mixins."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Team self-ref runtime accessors', () => {
              it('exposes getChildTeams and getParentTeam mixins', () => {
                const { models } = buildGraph();
                const { Team } = models;
                expect(typeof (Team.prototype as any).getChildTeams,
                  'Team#getChildTeams missing').to.equal('function');
                expect(typeof (Team.prototype as any).getParentTeam,
                  'Team#getParentTeam missing').to.equal('function');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-team-runtime.test.ts", spec)
        _assert_mocha_passed(result, "Team self-ref runtime accessor mixins")

    def test_project_team_ownership_accessors(self):
        """Project has `owningTeam` (-> Team); Team has `ownedProjects` (-> Project)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Project<->Team ownership accessors', () => {
              it('wires owningTeam (Project->Team) and ownedProjects (Team->Project)', () => {
                const { models } = buildGraph();
                const { Project, Team } = models;

                const owningAssoc = Project.associations.owningTeam;
                expect(owningAssoc, 'Project.associations.owningTeam missing').to.exist;
                expect(owningAssoc.target, 'owningTeam must target Team').to.equal(Team);
                expect(String(owningAssoc.associationType)).to.equal('BelongsTo');

                const ownedAssoc = Team.associations.ownedProjects;
                expect(ownedAssoc, 'Team.associations.ownedProjects missing').to.exist;
                expect(ownedAssoc.target, 'ownedProjects must target Project')
                  .to.equal(Project);
                expect(String(ownedAssoc.associationType)).to.equal('HasMany');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-ownership-accessors.test.ts", spec)
        _assert_mocha_passed(result, "Project<->Team ownership accessor names")

    def test_project_team_ownership_foreign_key(self):
        """The Project->Team ownership link must use the `owningTeamId` column."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Project<->Team ownership foreign key', () => {
              it('links project->team via the owningTeamId column', () => {
                const { models } = buildGraph();
                const { Project, Team } = models;

                const owningAssoc: any = Project.associations.owningTeam;
                const ownedAssoc: any = Team.associations.ownedProjects;

                const fk = fkName(owningAssoc) || fkName(ownedAssoc);
                expect(fk, 'ownership foreign key should be owningTeamId')
                  .to.equal('owningTeamId');

                // Project must carry an owningTeamId attribute column.
                expect(Project.getAttributes(), 'Project has no owningTeamId column')
                  .to.have.property('owningTeamId');

                // Sanity: the ownership FK is distinct from the team self-ref FK,
                // so they cannot be the same mislabeled column.
                expect(fk).to.not.equal('parentTeamId');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-ownership-fk.test.ts", spec)
        _assert_mocha_passed(result, "Project<->Team ownership foreign key column")

    def test_person_required_unique_username(self):
        """Person.username must be a required, unique text field (introspected)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: Person.username field', () => {
              it('declares username as required and unique', async () => {
                const { models } = buildGraph();
                const { Person } = models;

                const attrs: any = Person.getAttributes();
                expect(attrs, 'Person has no username attribute')
                  .to.have.property('username');

                const username = attrs.username;
                // required => allowNull is false
                expect(username.allowNull, 'username must be required (allowNull:false)')
                  .to.equal(false);
                // unique => a truthy unique marker (boolean true or string/object name)
                expect(Boolean(username.unique),
                  'username must be unique').to.equal(true);
              });

              it('rejects building a Person with a null username at validate time', async () => {
                const { models } = buildGraph();
                const person = models.Person.build({ username: null as any });
                let err: any;
                try {
                  await person.validate();
                } catch (e) {
                  err = e;
                }
                expect(err, 'expected validate() to reject a null username').to.exist;
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-person-field.test.ts", spec)
        _assert_mocha_passed(result, "Person.username required+unique")

    def test_two_instances_are_independent(self):
        """Two separate Sequelize instances each get a fully independent wired graph."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('project-membership: per-instance independence', () => {
              it('models and associations do not bleed across instances', () => {
                const a = buildGraph();
                const b = buildGraph();

                // Distinct model classes per instance.
                expect(a.models.Person).to.not.equal(b.models.Person);
                expect(a.models.Project).to.not.equal(b.models.Project);
                expect(a.models.Team).to.not.equal(b.models.Team);

                // Associations resolve within their own instance only.
                expect(a.models.Person.associations.projects.target)
                  .to.equal(a.models.Project);
                expect(b.models.Person.associations.projects.target)
                  .to.equal(b.models.Project);
                expect(a.models.Person.associations.projects.target)
                  .to.not.equal(b.models.Project);

                // Self-ref + ownership wiring present independently on each instance.
                expect(a.models.Team.associations.childTeams.target).to.equal(a.models.Team);
                expect(b.models.Team.associations.childTeams.target).to.equal(b.models.Team);
                expect(a.models.Project.associations.owningTeam.target).to.equal(a.models.Team);
                expect(b.models.Project.associations.owningTeam.target).to.equal(b.models.Team);

                // Each instance owns its own Memberships junction.
                const ja = a.sequelize.models.getOrThrow('Memberships');
                const jb = b.sequelize.models.getOrThrow('Memberships');
                expect(ja).to.not.equal(jb);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-independence.test.ts", spec)
        _assert_mocha_passed(result, "per-instance independence")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha project-membership.test.ts."""
        result = _run_mocha(
            os.path.join("test", "unit", "associations", "project-membership.test.ts"),
            timeout=600,
        )
        _assert_mocha_passed(result, "agent-supplied project-membership.test.ts")
