"use client";

import { FormEvent, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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

type ChartPoint = {
  x: string;
  y: number;
  series?: string | null;
};

type ChartSuggestion = {
  title: string;
  chart_type: "line" | "bar" | "area" | "pie";
  x_key: string;
  y_key: string;
  series_key: string | null;
  data: ChartPoint[];
  source_agents: string[];
  why_this_chart: string;
  confidence: number;
};

type ChatResponse = {
  question: string;
  answer: string;
  planner_mode: "llm" | "fallback" | "unknown";
  planner_debug?: Record<string, unknown>;
  chart_debug?: Record<string, unknown>;
  plan: PlanStep[];
  agent_results: AgentResult[];
  traces: AgentTrace[];
  chart_suggestions: ChartSuggestion[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function renderInlineMarkdown(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-zinc-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}

function renderAnswerMarkdown(text: string) {
  return text.split("\n").map((line, idx) => {
    if (line.startsWith("### ")) {
      return (
        <h3 key={idx} className="text-lg font-semibold text-zinc-900">
          {renderInlineMarkdown(line.replace("### ", ""))}
        </h3>
      );
    }
    if (line.startsWith("#### ")) {
      return (
        <h4 key={idx} className="mt-2 text-base font-semibold text-zinc-800">
          {renderInlineMarkdown(line.replace("#### ", ""))}
        </h4>
      );
    }
    if (line.startsWith("- ")) {
      return (
        <li key={idx} className="ml-5 list-disc text-sm leading-6 text-zinc-700">
          {renderInlineMarkdown(line.replace("- ", ""))}
        </li>
      );
    }
    if (!line.trim()) {
      return <div key={idx} className="h-2" />;
    }
    return (
      <p key={idx} className="text-sm leading-6 text-zinc-700">
        {renderInlineMarkdown(line)}
      </p>
    );
  });
}

const CHART_PALETTE = ["#6366f1", "#8b5cf6", "#06b6d4", "#14b8a6", "#22c55e", "#f59e0b", "#f97316", "#ef4444"];

function ChartCard({ chart }: { chart: ChartSuggestion }) {
  const hasSeries = chart.data.some((item) => item.series);
  const typeBadgeStyle: Record<ChartSuggestion["chart_type"], string> = {
    line: "bg-sky-100 text-sky-700",
    area: "bg-cyan-100 text-cyan-700",
    bar: "bg-violet-100 text-violet-700",
    pie: "bg-emerald-100 text-emerald-700",
  };

  return (
    <article className="rounded-2xl border border-indigo-100 bg-gradient-to-b from-white to-indigo-50/40 p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-zinc-900">{chart.title}</h3>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${typeBadgeStyle[chart.chart_type]}`}>
            {chart.chart_type}
          </span>
          <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
            conf {chart.confidence.toFixed(2)}
          </span>
        </div>
      </div>
      <p className="mt-2 text-xs leading-5 text-zinc-600">{chart.why_this_chart}</p>

      <div className="mt-4 h-64 w-full rounded-xl border border-indigo-100 bg-white/80 p-2">
        <ResponsiveContainer width="100%" height="100%">
          {chart.chart_type === "line" ? (
            <LineChart data={chart.data}>
              <CartesianGrid strokeDasharray="4 4" stroke="#e4e4e7" />
              <XAxis dataKey="x" tick={{ fontSize: 11, fill: "#52525b" }} />
              <YAxis tick={{ fontSize: 11, fill: "#52525b" }} />
              <Tooltip contentStyle={{ borderRadius: 12, borderColor: "#c7d2fe" }} />
              {hasSeries ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
              <Line type="monotone" dataKey="y" stroke="#6366f1" strokeWidth={3} dot={{ r: 2 }} activeDot={{ r: 4 }} />
            </LineChart>
          ) : chart.chart_type === "area" ? (
            <AreaChart data={chart.data}>
              <CartesianGrid strokeDasharray="4 4" stroke="#e4e4e7" />
              <XAxis dataKey="x" tick={{ fontSize: 11, fill: "#52525b" }} />
              <YAxis tick={{ fontSize: 11, fill: "#52525b" }} />
              <Tooltip contentStyle={{ borderRadius: 12, borderColor: "#a5f3fc" }} />
              {hasSeries ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
              <Area type="monotone" dataKey="y" stroke="#06b6d4" fill="#67e8f9" fillOpacity={0.55} />
            </AreaChart>
          ) : chart.chart_type === "pie" ? (
            <PieChart>
              <Tooltip contentStyle={{ borderRadius: 12, borderColor: "#bbf7d0" }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Pie data={chart.data} dataKey="y" nameKey="x" outerRadius={90} innerRadius={45} label>
                {chart.data.map((entry, idx) => (
                  <Cell key={`${entry.x}-${idx}`} fill={CHART_PALETTE[idx % CHART_PALETTE.length]} />
                ))}
              </Pie>
            </PieChart>
          ) : (
            <BarChart data={chart.data}>
              <CartesianGrid strokeDasharray="4 4" stroke="#e4e4e7" />
              <XAxis dataKey="x" tick={{ fontSize: 11, fill: "#52525b" }} />
              <YAxis tick={{ fontSize: 11, fill: "#52525b" }} />
              <Tooltip contentStyle={{ borderRadius: 12, borderColor: "#ddd6fe" }} />
              {hasSeries ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
              <Bar dataKey="y" fill="#8b5cf6" radius={[6, 6, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>

      <p className="mt-3 text-[11px] text-zinc-500">
        Sources: {chart.source_agents.join(", ") || "n/a"}
      </p>
    </article>
  );
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
  const chartSuggestions = response?.chart_suggestions ?? [];

  return (
    <div className="min-h-screen bg-gradient-to-b from-indigo-50 via-white to-cyan-50 px-6 py-8">
      <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <section className="rounded-2xl border border-indigo-100 bg-white/90 p-6 shadow-sm backdrop-blur-sm">
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
            <section className="rounded-2xl border border-violet-100 bg-gradient-to-b from-white to-violet-50/40 p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-zinc-900">Final Answer</h2>
              <div className="mt-3">{renderAnswerMarkdown(response.answer)}</div>
            </section>

            {chartSuggestions.length > 0 ? (
              <section className="rounded-2xl border border-indigo-100 bg-gradient-to-b from-indigo-50/70 via-white to-cyan-50/70 p-6 shadow-sm">
                <h2 className="text-lg font-semibold text-zinc-900">Visual Insights</h2>
                <p className="mt-1 text-xs text-zinc-600">
                  Model-selected charts based on orchestrated agent evidence.
                </p>
                <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {chartSuggestions.map((chart, idx) => (
                    <ChartCard key={`${chart.title}-${idx}`} chart={chart} />
                  ))}
                </div>
              </section>
            ) : null}

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
