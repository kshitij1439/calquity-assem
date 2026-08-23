"use client";

import Link from "next/link";
import dynamic from "next/dynamic";

const MascotViewport = dynamic(() => import("./components/MascotViewport"), {
  ssr: false,
});

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-950 flex flex-col items-center justify-center gap-8 p-8">
      <div className="text-center space-y-4 flex flex-col items-center">
        <div className="w-28 h-28 relative flex items-center justify-center rounded-3xl bg-indigo-950/40 border border-indigo-500/30 shadow-xl shadow-indigo-500/10 overflow-hidden mb-2">
          <MascotViewport />
        </div>
        <div className="flex items-center justify-center gap-3">
          <h1 className="text-4xl font-bold text-white tracking-tight">ParcelPilot</h1>
        </div>
        <p className="text-gray-400 text-lg max-w-md">
          Internal AI support agent for operations and customer success teams.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-2xl">
        <Link href="/chat">
          <div className="group bg-gray-900 border border-gray-800 rounded-2xl p-6 hover:border-indigo-500 hover:bg-gray-800 transition-all duration-200 cursor-pointer">
            <div className="w-10 h-10 bg-indigo-500/20 rounded-xl flex items-center justify-center mb-4 group-hover:bg-indigo-500/30 transition-colors">
              <span className="text-indigo-400 text-xl">💬</span>
            </div>
            <h2 className="text-white font-semibold text-lg mb-2">Support Chat</h2>
            <p className="text-gray-400 text-sm">
              Ask questions about orders, policies, contracts, and SLAs. Get AI-powered answers with source citations.
            </p>
          </div>
        </Link>

        <Link href="/dashboard">
          <div className="group bg-gray-900 border border-gray-800 rounded-2xl p-6 hover:border-purple-500 hover:bg-gray-800 transition-all duration-200 cursor-pointer">
            <div className="w-10 h-10 bg-purple-500/20 rounded-xl flex items-center justify-center mb-4 group-hover:bg-purple-500/30 transition-colors">
              <span className="text-purple-400 text-xl">📊</span>
            </div>
            <h2 className="text-white font-semibold text-lg mb-2">Issue Dashboard</h2>
            <p className="text-gray-400 text-sm">
              Proactive SLA breach detection, recurring known issues, and cross-customer spike alerts.
            </p>
          </div>
        </Link>
      </div>

      <p className="text-gray-600 text-xs">
        Snapshot reference: 2026-08-16 11:00 IST
      </p>
    </main>
  );
}
