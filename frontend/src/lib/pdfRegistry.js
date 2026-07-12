import { API, TOKEN_KEY } from "@/lib/api";

// Lightweight client-side registry of generated Ananta PDFs so the user can find,
// re-open, delete or ask the AI to analyse them from Workspace › AI Analytics.
const KEY = "ananta_pdfs";
const EVT = "ananta:pdfs-changed";

export function listPdfs() {
    try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}

export function registerPdf(entry) {
    const list = listPdfs();
    list.unshift({ id: `${Date.now()}`, ts: Date.now(), ...entry });
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, 50)));
    window.dispatchEvent(new Event(EVT));
}

export function removePdf(id) {
    localStorage.setItem(KEY, JSON.stringify(listPdfs().filter((p) => p.id !== id)));
    window.dispatchEvent(new Event(EVT));
}

export const PDFS_EVENT = EVT;

/**
 * Authenticated PDF download with live progress. Owner-protected endpoints (e.g. lab-run
 * PDFs) 401 with a plain window.open() because the Bearer token can't be attached — this
 * fetches with the token and streams the body so callers can show a progress %.
 * onProgress(pct|null, receivedBytes): pct is null while the server is still generating
 * (no Content-Length yet) or when the length is unknown.
 */
export async function downloadPdf(rawUrl, filename, onProgress) {
    const url = rawUrl.startsWith("http") ? rawUrl : `${API}${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`;
    const token = localStorage.getItem(TOKEN_KEY);
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) {
        if (res.status === 401 || res.status === 403) throw new Error("Owner login required to download this PDF");
        throw new Error(`Download failed (${res.status})`);
    }
    const total = Number(res.headers.get("content-length")) || 0;
    const reader = res.body?.getReader?.();
    let blob;
    if (reader) {
        const chunks = [];
        let received = 0;
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
            received += value.length;
            onProgress?.(total ? Math.min(99, Math.round((received / total) * 100)) : null, received);
        }
        blob = new Blob(chunks, { type: "application/pdf" });
    } else {
        blob = await res.blob();
    }
    onProgress?.(100, blob.size);
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = filename || "ananta.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 4000);
}
