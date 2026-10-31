"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(true);

  async function check() {
    setChecking(true);
    try {
      await apiGet("/api/auth/me");
      setReady(true);
      setError("");
    } catch (err) {
      setReady(false);
      setError(err instanceof Error ? err.message : "连接失败，请重试");
    } finally {
      setChecking(false);
    }
  }
  useEffect(() => { void check(); }, []);

  if (ready) return <>
    <div className="flex justify-end px-4 pt-2"><button className="text-xs text-slate-500" onClick={() => {
      sessionStorage.removeItem("codepilot-access-token");
      setToken("");
      setReady(false);
    }}>切换访问凭据</button></div>
    {children}
  </>;
  return <main className="mx-auto mt-24 max-w-md rounded-xl border bg-white p-6">
    <h1 className="mb-4 text-xl font-semibold">连接 CodePilot</h1>
    <p className="mb-4 text-sm text-slate-600">使用管理员提供的个人访问令牌。令牌仅保留在当前浏览器标签页会话中。</p>
    <form onSubmit={(event) => {
      event.preventDefault();
      sessionStorage.setItem("codepilot-access-token", token.trim());
      void check();
    }}>
      <input aria-label="个人访问令牌" type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} className="w-full rounded border p-2" />
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <button disabled={checking} className="mt-4 rounded bg-teal-700 px-4 py-2 text-white">{checking ? "正在连接…" : "连接 / 重试"}</button>
    </form>
  </main>;
}
