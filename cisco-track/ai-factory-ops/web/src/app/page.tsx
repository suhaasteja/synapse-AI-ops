"use client";

import { FormEvent, useMemo, useState } from "react";

type PlanStep = {
  agent_name: string;
  reason: string;
  sub_query: string;
};

type AgentResult = {
  agent_name: string;
  summary: string;
  confidence: number;
  evidence: string[];
};

type AgentTrace = {
  agent_name: string;
  routed_reason: string;
  query_used: string;
  sql_executed: string;
  rows_scanned: number;
  elapsed_ms: number;
  notes: string[];
};

type ChatResponse = {
  question: string;
  answer: string;
  planner_mode: "llm" | "fallback" | "unknown";
  plan: PlanStep[];
  agent_results: AgentResult[];
  traces: AgentTrace[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function renderAnswerMarkdown(text: string) {
  return text.split("\n").map((line, idx) => {
    if (line.startsWith("### ")) {
      return (
        <h3 key={idx} className="text-lg font-semibold text-zinc-900">
          {line.replace("### ", "")}
        </h3>
      );
    }
    if (line.startsWith("#### ")) {
      return (
        <h4 key={idx} className="mt-2 text-base font-semibold text-zinc-800">
          {line.replace("#### ", "")}
        </h4>
      );
    }
    if (line.startsWith("- ")) {
      return (
        <li key={idx} className="ml-5 list-disc text-sm leading-6 text-zinc-700">
          {line.replace("- ", "")}
        </li>
      );
    }
    if (!line.trim()) {
      return <div key={idx} className="h-2" />;
    }
    return (
      <p key={idx} className="text-sm leading-6 text-zinc-700">
        {line}
      </p>
    );
  });
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [activeTraceTab, setActiveTraceTab] = useState("");

  const traceTabs = useMemo(() => response?.traces ?? [], [response]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (!res.ok) {
        throw new Error(`Backend error: ${res.status}`);
      }

      const payload = (await res.json()) as ChatResponse;
      setResponse(payload);
      if (payload.traces.length > 0) {
        setActiveTraceTab(payload.traces[0].agent_name);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  const activeTrace = traceTabs.find((trace) => trace.agent_name === activeTraceTab) ?? null;

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-50 via-white to-zinc-100 px-6 py-8">
      <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <section className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
            AI Factory Ops Multi-Agent Chat
          </h1>
          <p className="mt-2 text-sm text-zinc-600">
            Ask one question. The orchestrator routes to CSV specialist agents, then returns findings with full traces.
          </p>

          <form onSubmit={onSubmit} className="mt-5 flex flex-col gap-3 sm:flex-row">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g., Why are latency and critical alerts high?"
              className="h-12 flex-1 rounded-xl border border-zinc-300 px-4 text-sm text-zinc-900 placeholder:text-zinc-400 outline-none ring-indigo-200 focus:ring-2"
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="h-12 rounded-xl bg-indigo-600 px-5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Analyzing..." : "Ask Orchestrator"}
            </button>
          </form>

          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        </section>

        {response ? (
          <>
            <section className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-zinc-900">Final Answer</h2>
              <div className="mt-3">{renderAnswerMarkdown(response.answer)}</div>
            </section>

            <section className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
              <details>
                <summary className="cursor-pointer text-base font-semibold text-zinc-900">
                  Diagnostics (Planner, Agent Summaries, Traces)
                </summary>

                <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-zinc-900">Orchestrator Plan</h3>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                          response.planner_mode === "llm"
                            ? "bg-emerald-100 text-emerald-700"
                            : response.planner_mode === "fallback"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-zinc-100 text-zinc-700"
                        }`}
                      >
                        planner: {response.planner_mode}
                      </span>
                    </div>
                    <ul className="mt-3 space-y-3">
                      {response.plan.map((step, idx) => (
                        <li key={`${step.agent_name}-${idx}`} className="rounded-lg border border-zinc-200 bg-white p-3">
                          <p className="text-sm font-medium text-zinc-800">{step.agent_name}</p>
                          <p className="mt-1 text-xs text-zinc-600">{step.reason}</p>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                    <h3 className="text-sm font-semibold text-zinc-900">Agent Summaries</h3>
                    <ul className="mt-3 space-y-3">
                      {response.agent_results.map((agent) => (
                        <li key={agent.agent_name} className="rounded-lg border border-zinc-200 bg-white p-3">
                          <div className="flex items-center justify-between">
                            <p className="text-sm font-medium text-zinc-800">{agent.agent_name}</p>
                            <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
                              conf {agent.confidence.toFixed(2)}
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-zinc-700">{agent.summary}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="mt-6">
                  <h3 className="text-sm font-semibold text-zinc-900">Sub-Agent Traces</h3>
                  <div className="mt-3 mb-4 flex flex-wrap gap-2">
                    {traceTabs.map((trace) => (
                      <button
                        key={trace.agent_name}
                        onClick={() => setActiveTraceTab(trace.agent_name)}
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                          activeTraceTab === trace.agent_name
                            ? "bg-indigo-600 text-white"
                            : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
                        }`}
                      >
                        {trace.agent_name}
                      </button>
                    ))}
                  </div>

                  {activeTrace ? (
                    <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-700">
                      <p><span className="font-semibold">Routed reason:</span> {activeTrace.routed_reason}</p>
                      <p className="mt-2"><span className="font-semibold">Query:</span> {activeTrace.query_used}</p>
                      <p className="mt-2"><span className="font-semibold">Rows scanned:</span> {activeTrace.rows_scanned}</p>
                      <p className="mt-2"><span className="font-semibold">Elapsed:</span> {activeTrace.elapsed_ms} ms</p>
                      <p className="mt-2 font-semibold">SQL executed</p>
                      <pre className="mt-1 overflow-x-auto rounded bg-zinc-900 p-3 text-[11px] text-zinc-100">
                        {activeTrace.sql_executed}
                      </pre>
                      {activeTrace.notes.length > 0 ? (
                        <>
                          <p className="mt-3 font-semibold">Notes</p>
                          <ul className="mt-1 list-disc space-y-1 pl-5">
                            {activeTrace.notes.map((note, idx) => (
                              <li key={idx}>{note}</li>
                            ))}
                          </ul>
                        </>
                      ) : null}
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-600">No trace selected.</p>
                  )}
                </div>
              </details>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
