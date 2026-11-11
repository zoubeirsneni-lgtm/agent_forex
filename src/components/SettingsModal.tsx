import { X } from 'lucide-react';

export type MarketSourceMode = 'live' | 'mt5_bridge' | 'mt5_offline';
export type LlmTestMode = 'real' | 'test_confirme' | 'test_refuse' | 'test_429';

export interface DashboardSettings {
  marketSource: MarketSourceMode;
  mt5BridgeUrl: string;
  llmRouterUrl: string;
  llmApiKey: string;
  llmTestMode: LlmTestMode;
}

interface SettingsModalProps {
  open: boolean;
  settings: DashboardSettings;
  onChange: (next: DashboardSettings) => void;
  onClose: () => void;
}

export function SettingsModal({ open, settings, onChange, onClose }: SettingsModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Paramètres du dashboard"
    >
      <div className="w-full max-w-lg rounded-2xl border border-[#1e2633] bg-[#0f131a] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#1e2633] px-6 py-4">
          <h2 className="text-lg font-bold text-slate-100">Paramètres de connexion</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#1e2633] bg-[#090c11] text-slate-300 hover:text-white cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 p-6">
          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">
              Source des données Forex (Exness-MT5Trial16)
            </label>
            <select
              value={settings.marketSource}
              onChange={(e) =>
                onChange({ ...settings, marketSource: e.target.value as MarketSourceMode })
              }
              className="w-full rounded-lg border border-[#1e2633] bg-[#07090d] px-3 py-2.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
            >
              <option value="live">Flux marché temps réel</option>
              <option value="mt5_bridge">Bridge MT5 local personnalisé</option>
              <option value="mt5_offline">Tester MT5 injoignable (affiche WAIT partout)</option>
            </select>
          </div>

          {settings.marketSource === 'mt5_bridge' && (
            <div>
              <label className="mb-2 block text-xs font-semibold text-slate-300">
                URL du Bridge MT5 local
              </label>
              <input
                type="text"
                value={settings.mt5BridgeUrl}
                onChange={(e) => onChange({ ...settings, mt5BridgeUrl: e.target.value })}
                placeholder="http://127.0.0.1:8765"
                className="w-full rounded-lg border border-[#1e2633] bg-[#07090d] px-3 py-2 font-mono text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
              />
            </div>
          )}

          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">
              Endpoint Routeur LLM local
            </label>
            <input
              type="text"
              value={settings.llmRouterUrl}
              onChange={(e) => onChange({ ...settings, llmRouterUrl: e.target.value })}
              className="w-full rounded-lg border border-[#1e2633] bg-[#07090d] px-3 py-2 font-mono text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">
              Clé API Routeur LLM
            </label>
            <input
              type="password"
              value={settings.llmApiKey}
              onChange={(e) => onChange({ ...settings, llmApiKey: e.target.value })}
              className="w-full rounded-lg border border-[#1e2633] bg-[#07090d] px-3 py-2 font-mono text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-2 block text-xs font-semibold text-slate-300">
              Comportement validation LLM (EURUSDm 1m/3m ≥ 6/8)
            </label>
            <select
              value={settings.llmTestMode}
              onChange={(e) =>
                onChange({ ...settings, llmTestMode: e.target.value as LlmTestMode })
              }
              className="w-full rounded-lg border border-[#1e2633] bg-[#07090d] px-3 py-2.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
            >
              <option value="real">Appel réel vers routeur LLM local</option>
              <option value="test_confirme">Simuler verdict CONFIRMÉ (tester Popup Géant)</option>
              <option value="test_refuse">Simuler verdict REFUSÉ</option>
              <option value="test_429">Simuler erreur 429 (ERREUR LLM pendant 60s)</option>
            </select>
          </div>
        </div>

        <div className="flex justify-end border-t border-[#1e2633] bg-[#090c11] px-6 py-3.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-500 cursor-pointer"
          >
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  );
}
