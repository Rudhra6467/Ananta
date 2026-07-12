import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

// Renders a page's primary action into the shared, scroll-through top-header slot
// (#header-action-slot lives in AppShell's context row). Keeps the button reactive to
// page state while freeing a full row of vertical space on screen.
export default function HeaderActionPortal({ children }) {
    const [el, setEl] = useState(null);
    useEffect(() => {
        let raf;
        const find = () => {
            const node = document.getElementById("header-action-slot");
            if (node) setEl(node);
            else raf = requestAnimationFrame(find);
        };
        find();
        return () => { if (raf) cancelAnimationFrame(raf); };
    }, []);
    return el ? createPortal(children, el) : null;
}
