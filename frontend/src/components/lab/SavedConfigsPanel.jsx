import { useState, useEffect, useCallback } from "react";
import { Layers, Star, Trash2, Loader2, Save, Plus, ChevronDown, ChevronRight, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import HelpHint from "@/components/lab/HelpHint";

const STRATS = [
    { id: "hunter", label: "Hunter" },
    { id: "squeeze", label: "Volatility Squeeze" },
    { id: "continuation", label: "Continuation" },
];
const ORIGIN_CLS = {
    optimizer: "text-atlas-cyan border-atlas-cyan/30 bg-atlas-cyan/10",
    builtin: "text-atlas-textTertiary border-atlas-border",
    user: "text-violet-400 border-violet-500/30 bg-violet-500/10",
};

// Saved Configs — surfaces the versioned strategy_configs (created by the lab-bridge or
// by hand), with rating, delete and a schema-driven dynamic parameter editor (Phase 2).
export default function SavedConfigsPanel({ isOwner, only }) {
    const [schemas, setSchemas] = useState({}); // key -> schema
    const [configs, setConfigs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [openId, setOpenId] = useState(null);
    const strats = only ? STRATS.filter((s) => s.id === only) : STRATS;

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [reg, cfg] = await Promise.all([api.strategyRegistry(), api.strategyConfigs()]);
            const map = {};
            (reg.strategies || []).forEach((s) => { map[s.key] = s; });
            setSchemas(map);
            setConfigs(cfg.configs || []);
        } catch (e) {
            toast.error("Failed to load configs", { description: String(e?.message || e) });
        } finally { setLoading(false); }
    }, []);

    useEffect(() => { load(); }, [load]);

    const rate = async (cfg, stars) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try {
            await api.strategyConfigUpdate(cfg.id, { rating: { ...(cfg.rating || {}), stars } });
            setConfigs((cs) => cs.map((c) => (c.id === cfg.id ? { ...c, rating: { ...(c.rating || {}), stars } } : c)));
        } catch (e) { toast.error("Rating failed", { description: String(e?.response?.data?.detail || e?.message) }); }
    };

    const remove = async (cfg) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        if (!window.confirm(`Delete config "${cfg.name}"? This cannot be undone.`)) return;
        try {
            await api.strategyConfigDelete(cfg.id);
            setConfigs((cs) => cs.filter((c) => c.id !== cfg.id));
            toast.success("Config deleted");
        } catch (e) { toast.error("Delete failed", { description: String(e?.response?.data?.detail || e?.message) }); }
    };

    const createFor = async (key) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try {
            const res = await api.strategyConfigCreate({ strategy_key: key, params: {}, origin: "user", name: `${schemas[key]?.name || key} · custom` });
            toast.success("Config created", { description: res.config.name });
            await load();
            setOpenId(res.config.id);
        } catch (e) { toast.error("Create failed", { description: String(e?.response?.data?.detail || e?.message) }); }
    };

    if (loading) {
        return <div className="panel border-atlas-border rounded-xl p-6 font-mono text-[11px] text-atlas-textSecondary flex items-center gap-2" data-testid="saved-configs-loading"><Loader2 className="w-4 h-4 animate-spin" /> LOADING SAVED CONFIGS</div>;
    }

    return (
        <div className="panel border-atlas-border rounded-xl overflow-hidden" data-testid="saved-configs-panel">
            <div className="px-4 py-3 border-b border-atlas-border flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-atlas-cyan" strokeWidth={2} />
                    <span className="font-heading font-medium text-atlas-text">Saved Configs</span>
                    <span className="font-mono text-[9px] uppercase tracking-widest text-atlas-textTertiary ml-1">{configs.length} versioned</span>
                </div>
                <button data-testid="saved-configs-refresh" onClick={load} className="text-atlas-textTertiary hover:text-atlas-text" title="Refresh">
                    <RotateCcw className="w-3.5 h-3.5" />
                </button>
            </div>

            <div className="p-4 space-y-4">
                {strats.map((st) => {
                    const rows = configs.filter((c) => c.strategy_key === st.id);
                    return (
                        <div key={st.id} data-testid={`saved-group-${st.id}`}>
                            <div className="flex items-center justify-between mb-2">
                                <div className="label-tag">{st.label} <span className="text-atlas-textTertiary">· {rows.length}</span></div>
                                <button data-testid={`create-config-${st.id}`} onClick={() => createFor(st.id)} disabled={!isOwner}
                                    className="flex items-center gap-1 font-mono text-[10px] text-atlas-cyan hover:text-cyan-300 disabled:opacity-40">
                                    <Plus className="w-3 h-3" /> NEW
                                </button>
                            </div>
                            {rows.length === 0 ? (
                                <div className="font-mono text-[10px] text-atlas-textTertiary py-2">No saved configs — promote a lab winner or create one.</div>
                            ) : (
                                <div className="space-y-2">
                                    {rows.map((c) => (
                                        <ConfigRow key={c.id} cfg={c} schema={schemas[c.strategy_key]} isOwner={isOwner}
                                            open={openId === c.id} onToggle={() => setOpenId(openId === c.id ? null : c.id)}
                                            onRate={rate} onDelete={remove} onSaved={(u) => setConfigs((cs) => cs.map((x) => (x.id === u.id ? u : x)))} />
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function Stars({ value = 0, onSet, disabled }) {
    return (
        <div className="flex items-center gap-0.5" data-testid="config-stars">
            {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} data-testid={`star-${n}`} disabled={disabled} onClick={() => onSet(n)}
                    className={`disabled:cursor-default ${disabled ? "" : "hover:scale-110 transition-transform"}`}>
                    <Star className={`w-3.5 h-3.5 ${n <= value ? "text-atlas-warning fill-atlas-warning" : "text-atlas-textTertiary"}`} />
                </button>
            ))}
        </div>
    );
}

function ConfigRow({ cfg, schema, isOwner, open, onToggle, onRate, onDelete, onSaved }) {
    const stars = cfg.rating?.stars ?? 0;
    const oc = ORIGIN_CLS[cfg.origin] || ORIGIN_CLS.user;
    return (
        <div className="border border-atlas-border rounded-lg" data-testid={`config-row-${cfg.id.slice(0, 8)}`}>
            <div className="flex items-center gap-2 px-3 py-2">
                <button onClick={onToggle} className="text-atlas-textTertiary hover:text-atlas-text" data-testid={`config-toggle-${cfg.id.slice(0, 8)}`}>
                    {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>
                <div className="min-w-0 flex-1">
                    <div className="font-mono text-xs text-atlas-text truncate">{cfg.name}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                        <span className={`font-mono text-[8px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${oc}`}>{cfg.origin}</span>
                        <span className="font-mono text-[9px] text-atlas-textTertiary">v{cfg.strategy_version} · {Object.keys(cfg.params || {}).length} overrides</span>
                    </div>
                </div>
                <Stars value={stars} disabled={!isOwner} onSet={(n) => onRate(cfg, n)} />
                {cfg.origin !== "builtin" && (
                    <button data-testid={`config-delete-${cfg.id.slice(0, 8)}`} onClick={() => onDelete(cfg)} disabled={!isOwner}
                        className="text-atlas-textTertiary hover:text-atlas-negative disabled:opacity-40 ml-1">
                        <Trash2 className="w-3.5 h-3.5" />
                    </button>
                )}
            </div>
            {open && <ConfigEditor cfg={cfg} schema={schema} isOwner={isOwner} onSaved={onSaved} />}
        </div>
    );
}

// Schema-driven dynamic parameter editor — renders inputs from the ParameterSchema,
// so tuning a strategy is configuration (no code changes).
function ConfigEditor({ cfg, schema, isOwner, onSaved }) {
    const [vals, setVals] = useState({});
    const [busy, setBusy] = useState(false);
    const params = schema?.params || [];

    useEffect(() => {
        const init = {};
        params.forEach((p) => { init[p.id] = cfg.params?.[p.id] ?? p.default; });
        setVals(init);
    }, [cfg.id, schema]);

    if (!schema) return <div className="px-3 pb-3 font-mono text-[10px] text-atlas-textTertiary">Schema unavailable for this strategy.</div>;

    // group params
    const groups = {};
    params.forEach((p) => { (groups[p.group] = groups[p.group] || []).push(p); });

    const setVal = (p, raw) => {
        let v = raw;
        if (p.type === "int") v = raw === "" ? "" : parseInt(raw, 10);
        else if (p.type === "float") v = raw === "" ? "" : parseFloat(raw);
        else if (p.type === "bool") v = raw;
        setVals((cur) => ({ ...cur, [p.id]: v }));
    };

    const save = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setBusy(true);
        try {
            // only send params that differ from the schema default (sparse overrides)
            const out = {};
            params.forEach((p) => {
                const v = vals[p.id];
                if (v !== "" && v != null && v !== p.default) out[p.id] = v;
            });
            const res = await api.strategyConfigUpdate(cfg.id, { params: out });
            toast.success("CONFIG SAVED", { description: `${Object.keys(out).length} override(s)` });
            onSaved?.(res.config);
        } catch (e) {
            toast.error("SAVE FAILED", { description: String(e?.response?.data?.detail?.errors?.join?.(", ") || e?.response?.data?.detail || e?.message) });
        } finally { setBusy(false); }
    };

    return (
        <div className="border-t border-atlas-border px-3 py-3 space-y-4" data-testid={`config-editor-${cfg.id.slice(0, 8)}`}>
            {Object.entries(groups).map(([g, ps]) => (
                <div key={g}>
                    <div className="label-tag mb-2">{g}</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {ps.map((p) => (
                            <div key={p.id} data-testid={`param-${p.id}`}>
                                <div className="flex items-center justify-between gap-2">
                                    <label className="font-mono text-[10px] text-atlas-textSecondary flex items-center gap-1">
                                        {p.label}{p.unit ? ` (${p.unit})` : ""}
                                        <HelpHint text={p.help} title={p.label} />
                                    </label>
                                    {vals[p.id] !== p.default && <span className="font-mono text-[8px] text-atlas-cyan">override</span>}
                                </div>
                                {p.type === "bool" ? (
                                    <select data-testid={`param-input-${p.id}`} value={String(vals[p.id])} onChange={(e) => setVal(p, e.target.value === "true")}
                                        className="w-full mt-1 bg-atlas-panel border border-atlas-border rounded px-2 py-1.5 font-mono text-xs text-atlas-text">
                                        <option value="true">ON</option><option value="false">OFF</option>
                                    </select>
                                ) : p.type === "enum" && (p.options || []).length ? (
                                    <select data-testid={`param-input-${p.id}`} value={vals[p.id]} onChange={(e) => setVal(p, e.target.value)}
                                        className="w-full mt-1 bg-atlas-panel border border-atlas-border rounded px-2 py-1.5 font-mono text-xs text-atlas-text">
                                        {p.options.map((o) => <option key={o} value={o}>{o}</option>)}
                                    </select>
                                ) : (
                                    <Input data-testid={`param-input-${p.id}`} type="number" value={vals[p.id] ?? ""} min={p.min} max={p.max} step={p.step || "any"}
                                        onChange={(e) => setVal(p, e.target.value)} className="atlas-input rounded-md font-mono mt-1 h-8 text-xs" />
                                )}
                                <div className="font-mono text-[8px] text-atlas-textTertiary mt-0.5">default {String(p.default)}{p.min != null ? ` · ${p.min}–${p.max}` : ""}</div>
                            </div>
                        ))}
                    </div>
                </div>
            ))}
            <div className="flex justify-end">
                <Button data-testid={`config-save-${cfg.id.slice(0, 8)}`} onClick={save} disabled={busy || !isOwner} size="sm" className="gap-1.5">
                    {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}{isOwner ? "SAVE PARAMS" : "READ-ONLY"}
                </Button>
            </div>
        </div>
    );
}
