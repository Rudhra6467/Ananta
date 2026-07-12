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
