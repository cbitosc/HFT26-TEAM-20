import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Lock, Rocket } from "lucide-react";
import { useStartRun } from "../api/hooks";
import { ErrorBox } from "../components/ErrorBox";
import { CopyButton } from "../components/CopyButton";
import type {
  CheckKind,
  CheckUpload,
  CreateTaskRequest,
  SuiteUpload,
  TestUpload,
} from "../api/types";

const EXAMPLE_ARGS = "([(1, 3), (2, 6)],)";

interface TestRow {
  key: string;
  id: string;
  description: string;
  kind: CheckKind;
  args: string;
  expected: string;
}

let rowCounter = 0;
function makeRow(idPrefix: string): TestRow {
  rowCounter += 1;
  return {
    key: `${idPrefix}-${rowCounter}`,
    id: `${idPrefix}${rowCounter}`,
    description: "",
    kind: "returns",
    args: "",
    expected: "",
  };
}

function expectedNeeded(kind: CheckKind): boolean {
  return kind !== "unchanged_input";
}

function expectedLabel(kind: CheckKind): string {
  switch (kind) {
    case "returns":
      return "Expected (Python literal, e.g. 4)";
    case "raises":
      return "Exception name (e.g. ValueError)";
    case "all_items_of_type":
      return "Type name (e.g. int)";
    case "unchanged_input":
      return "(not used for unchanged_input)";
  }
}

function toCheck(row: TestRow): CheckUpload {
  const check: CheckUpload = { kind: row.kind, args: row.args };
  if (expectedNeeded(row.kind)) check.expected = row.expected;
  return check;
}

function toTest(row: TestRow): TestUpload {
  return { id: row.id, description: row.description, checks: [toCheck(row)] };
}

export function NewTask() {
  const navigate = useNavigate();
  const startRun = useStartRun();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("python");
  const [entrypoint, setEntrypoint] = useState("");
  const [starterCode, setStarterCode] = useState("");

  const [arity, setArity] = useState("1");
  const [smokeArgs, setSmokeArgs] = useState("(1,)");
  const [smokeType, setSmokeType] = useState("int");

  const [publicTests, setPublicTests] = useState<TestRow[]>([makeRow("pub")]);
  const [hiddenTests, setHiddenTests] = useState<TestRow[]>([makeRow("hid")]);

  const [confirming, setConfirming] = useState(false);

  const formValid = useMemo(() => {
    return (
      title.trim().length > 0 &&
      description.trim().length > 0 &&
      language.trim().length > 0 &&
      entrypoint.trim().length > 0 &&
      publicTests.length > 0 &&
      hiddenTests.length > 0 &&
      publicTests.every((t) => t.id.trim() && t.args.trim()) &&
      hiddenTests.every((t) => t.id.trim() && t.args.trim())
    );
  }, [title, description, language, entrypoint, publicTests, hiddenTests]);

  function buildRequest(): CreateTaskRequest {
    const suite: SuiteUpload = {
      entrypoint: entrypoint.trim(),
      language: language.trim() || "python",
      description: description.trim(),
      contract: {
        arity: Number(arity),
        smoke_args: smokeArgs.trim(),
        smoke_type: smokeType.trim(),
      },
      public_tests: publicTests.map(toTest),
      hidden_tests: hiddenTests.map(toTest),
    };
    return {
      title: title.trim(),
      description: description.trim(),
      language: language.trim() || null,
      starter_code: starterCode.trim() ? starterCode : null,
      suite,
    };
  }

  function onConfirmStart() {
    startRun.mutate(buildRequest());
  }

  // After submit: show ONLY counts and hashes. Hidden test contents never
  // round-trip back into the UI.
  if (startRun.isSuccess) {
    const { task, executionId } = startRun.data;
    const s = task.suite;
    return (
      <section>
        <div className="panel">
          <h2>Run started</h2>
          <p className="hint">
            The suite commitment has been recorded. Hidden test contents are
            sealed and are not shown — only counts and hashes.
          </p>
          {s && (
            <dl className="kv">
              <dt>Suite id</dt>
              <dd>{s.id}</dd>
              <dt>Source</dt>
              <dd>{s.source}</dd>
              <dt>Public tests</dt>
              <dd>{s.public_test_count}</dd>
              <dt>Hidden tests</dt>
              <dd>{s.hidden_test_count}</dd>
              <dt>Suite hash</dt>
              <dd>{s.suite_hash}</dd>
              <dt>Public suite hash</dt>
              <dd>{s.public_suite_hash}</dd>
              <dt>Hidden suite hash</dt>
              <dd>{s.hidden_suite_hash}</dd>
            </dl>
          )}
          <div className="row" style={{ marginTop: "var(--s-4)" }}>
            <button
              type="button"
              className="primary"
              onClick={() => navigate(`/executions/${executionId}`)}
            >
              Open run
            </button>
            <Link to="/">
              <button type="button">Back to home</button>
            </Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setConfirming(true);
        }}
      >
        {startRun.isError && !confirming && (
          <div className="panel">
            <ErrorBox error={startRun.error} />
          </div>
        )}

        <div className="panel">
          <div className="field">
            <label htmlFor="title">Title</label>
            <input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Merge intervals"
            />
          </div>

          <div className="form-grid">
            {/* Left column: the task */}
            <div>
              <div className="field">
                <label htmlFor="description">Description</label>
                <textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Implement merge_intervals(intervals)."
                />
              </div>

              <div className="row">
                <div className="field">
                  <label htmlFor="language">Language</label>
                  <input
                    id="language"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="entrypoint">Entry function</label>
                  <input
                    id="entrypoint"
                    value={entrypoint}
                    onChange={(e) => setEntrypoint(e.target.value)}
                    placeholder="merge_intervals"
                  />
                </div>
              </div>

              <fieldset className="test-row">
                <legend className="hint">Contract (smoke check)</legend>
                <div className="row">
                  <div className="field">
                    <label htmlFor="arity">Arity (0–10)</label>
                    <input
                      id="arity"
                      type="number"
                      min={0}
                      max={10}
                      value={arity}
                      onChange={(e) => setArity(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="smokeArgs">Smoke args (literal tuple)</label>
                    <input
                      id="smokeArgs"
                      value={smokeArgs}
                      onChange={(e) => setSmokeArgs(e.target.value)}
                      placeholder="([(1, 2)],)"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="smokeType">Smoke return type</label>
                    <input
                      id="smokeType"
                      value={smokeType}
                      onChange={(e) => setSmokeType(e.target.value)}
                      placeholder="list"
                    />
                  </div>
                </div>
              </fieldset>

              <div className="field">
                <label htmlFor="starter">Starter code (optional)</label>
                <textarea
                  id="starter"
                  className="editor"
                  value={starterCode}
                  onChange={(e) => setStarterCode(e.target.value)}
                  placeholder={"def merge_intervals(intervals):\n    ..."}
                />
              </div>
            </div>

            {/* Right column: the tests */}
            <div>
              <div className="example">
                <span>
                  Args are a Python-literal tuple, e.g. <code>{EXAMPLE_ARGS}</code>
                </span>
                <CopyButton value={EXAMPLE_ARGS} label="example args" />
              </div>
              <p className="warn-note" style={{ marginTop: "var(--s-3)" }}>
                This form allows exactly one check per test. The backend supports
                up to 20 checks per test; richer multi-check suites must be
                created via the API directly.
              </p>

              <div className="panel" style={{ marginBottom: "var(--s-4)" }}>
                <div className="card-head">
                  <h3>Public tests</h3>
                </div>
                <p className="hint">Public tests may be shown to agents and clients.</p>
                <TestEditor rows={publicTests} setRows={setPublicTests} idPrefix="pub" />
              </div>

              <div className="panel glow-transition glow-purple">
                <div className="card-head">
                  <h3>Hidden tests</h3>
                  <span className="lock-note">
                    <Lock size={13} /> Write-only: never shown again
                  </span>
                </div>
                <p className="hint">
                  Hidden tests are sealed at rest and never revealed. After you
                  start the run, only counts and hashes are shown.
                </p>
                <TestEditor rows={hiddenTests} setRows={setHiddenTests} idPrefix="hid" />
              </div>
            </div>
          </div>

          <div style={{ marginTop: "var(--s-5)" }}>
            <button type="submit" className="primary" disabled={!formValid}>
              <Rocket size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
              Start Run
            </button>
            {!formValid && (
              <p className="hint">
                Start Run needs a title, description, language, entry function,
                and at least one public and one hidden test (each with an id and
                args).
              </p>
            )}
          </div>
        </div>
      </form>

      {confirming && (
        <div className="modal-backdrop">
          <div className="modal" role="dialog" aria-label="Confirm run" aria-modal="true">
            <h2 style={{ margin: 0 }}>Confirm run</h2>
            {startRun.isError && <ErrorBox error={startRun.error} />}
            <p style={{ margin: 0 }}>
              When you confirm, the suite is uploaded and its{" "}
              <strong>suite hash</strong> and{" "}
              <strong>evaluator configuration</strong> are recorded as the
              execution&apos;s commitment <strong>before any code is generated</strong>.
              Hidden tests are encrypted at rest and never displayed. This cannot
              be edited once the run starts.
            </p>
            <ul className="hint" style={{ margin: 0 }}>
              <li>suite hash, public suite hash, hidden suite hash</li>
              <li>evaluator configuration hash, scoring rule version, delta</li>
            </ul>
            <div className="row">
              <button
                type="button"
                className="primary"
                onClick={onConfirmStart}
                disabled={startRun.isPending}
              >
                {startRun.isPending ? "Starting…" : "Confirm and start"}
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={startRun.isPending}
              >
                Back
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function TestEditor({
  rows,
  setRows,
  idPrefix,
}: {
  rows: TestRow[];
  setRows: React.Dispatch<React.SetStateAction<TestRow[]>>;
  idPrefix: string;
}) {
  function update(key: string, patch: Partial<TestRow>) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }
  function remove(key: string) {
    setRows((prev) => prev.filter((r) => r.key !== key));
  }

  return (
    <div>
      {rows.map((row) => (
        <div className="test-row" key={row.key}>
          <div className="row">
            <div className="field">
              <label>Test id</label>
              <input
                value={row.id}
                onChange={(e) => update(row.key, { id: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Description</label>
              <input
                value={row.description}
                onChange={(e) => update(row.key, { description: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Check kind</label>
              <select
                value={row.kind}
                onChange={(e) =>
                  update(row.key, { kind: e.target.value as CheckKind })
                }
              >
                <option value="returns">returns</option>
                <option value="raises">raises</option>
                <option value="unchanged_input">unchanged_input</option>
                <option value="all_items_of_type">all_items_of_type</option>
              </select>
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Args (literal tuple)</label>
              <input
                className="mono"
                value={row.args}
                onChange={(e) => update(row.key, { args: e.target.value })}
                placeholder="([(1, 3), (2, 6)],)"
              />
            </div>
            <div className="field">
              <label>{expectedLabel(row.kind)}</label>
              <input
                className="mono"
                value={row.expected}
                disabled={!expectedNeeded(row.kind)}
                onChange={(e) => update(row.key, { expected: e.target.value })}
                placeholder="[(1, 6)]"
              />
            </div>
          </div>
          <button
            type="button"
            className="danger"
            onClick={() => remove(row.key)}
            disabled={rows.length <= 1}
          >
            Remove test
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => setRows((prev) => [...prev, makeRow(idPrefix)])}
      >
        + Add test
      </button>
    </div>
  );
}
