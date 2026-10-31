"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type Reproduction = {
  id: string;
  result: {
    status: string;
    message?: string;
    commit_sha?: string;
    exit_code?: number | null;
    command?: string[];
    working_directory?: string;
    output?: string;
    output_truncated?: boolean;
  };
};

const labels: Record<string, string> = {
  queued: "等待执行", running: "复现中", passed: "测试通过", failed: "命令失败",
  timeout: "已超时", blocked: "环境阻塞", error: "执行异常", interrupted: "执行中断"
};

export function CIReproduction({ runId, failed }: { runId: string; failed: boolean }) {
  const [directory, setDirectory] = useState(".");
  const [target, setTarget] = useState("");
  const [history, setHistory] = useState<Reproduction[]>([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const rows = await apiGet<Reproduction[]>(`/api/workflow-runs/${runId}/reproductions`);
        if (stopped) return;
        setHistory(rows);
        setError("");
        if (rows.some((row) => ["queued", "running"].includes(row.result.status))) timer = setTimeout(refresh, 2000);
      } catch (failure) {
        if (!stopped) setError(failure instanceof Error ? failure.message : "读取复现记录失败");
      }
    }
    void refresh();
    return () => { stopped = true; clearTimeout(timer); };
  }, [runId, activeId]);

  const busy = submitting || history.some((row) => ["queued", "running"].includes(row.result.status));

  async function reproduce() {
    setSubmitting(true);
    setError("");
    try {
      const row = await apiPost<Reproduction>(`/api/workflow-runs/${runId}/reproductions`, {
        command: ["python", "-m", "pytest", "-q", ...(target.trim() ? [target.trim()] : [])],
        working_directory: directory.trim() || "."
      });
      setHistory((rows) => [row, ...rows]);
      setActiveId(row.id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "提交复现任务失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="mt-4 rounded-md border border-line bg-white p-4">
      <h4 className="text-sm font-semibold text-ink">CI 失败复现沙盒</h4>
      <p className="mt-2 text-xs leading-5 text-slate-500">在失败提交的隔离副本运行 pytest。环境默认禁网，依赖须由管理员预装。完成后可重新分析，将执行结果加入排障证据。</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-slate-600">工作目录
          <input value={directory} onChange={(event) => setDirectory(event.target.value)} disabled={busy} placeholder="例如 backend" className="mt-1 w-full rounded-md border border-line px-3 py-2" />
        </label>
        <label className="text-xs text-slate-600">测试文件或用例（选填）
          <input value={target} onChange={(event) => setTarget(event.target.value)} disabled={busy} placeholder="tests/test_api.py::test_example" className="mt-1 w-full rounded-md border border-line px-3 py-2" />
        </label>
      </div>
      <button onClick={reproduce} disabled={!failed || busy} className="mt-3 rounded-md bg-accent px-3 py-2 text-xs font-medium text-white disabled:opacity-50">{busy ? "正在复现…" : "在沙盒中复现失败"}</button>
      {error && <p role="alert" className="mt-3 text-xs text-rose-700">{error}</p>}
      <div className="mt-3 space-y-3">
        {history.map(({ id, result }) => (
          <details key={id} open={id === history[0]?.id} className="rounded-md border border-line bg-panel p-3 text-xs">
            <summary className="cursor-pointer font-medium">{labels[result.status] || result.status} · {result.commit_sha?.slice(0, 8)} {result.exit_code != null ? `· 退出码 ${result.exit_code}` : ""}</summary>
            <p className="mt-2 leading-5">{result.message}</p>
            <p className="mt-1 break-all text-slate-500">{result.working_directory} / {result.command?.join(" ")}</p>
            {result.output && <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-slate-950 p-3 text-slate-100">{result.output}</pre>}
            {result.output_truncated && <p className="mt-2 text-amber-700">输出超过限制，仅展示前 64 KiB。</p>}
          </details>
        ))}
      </div>
    </section>
  );
}
