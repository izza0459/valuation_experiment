"use client";

/**
 * A one-line label that shrinks its text until it fits its space (down to
 * `min` px), instead of being cut off: "Inspection · Preliminary Check" in a
 * half-width button on a phone. Refits when the space or the text changes.
 */

import { useLayoutEffect, useRef } from "react";

export function FitText({ children, min = 11 }: { children: React.ReactNode; min?: number }) {
  const ref = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      // Back to the button's own size on one line, then shrink.
      el.style.fontSize = "";
      el.style.whiteSpace = "nowrap";
      el.style.lineHeight = "";
      let size = parseFloat(getComputedStyle(el).fontSize);
      while (el.scrollWidth > el.clientWidth + 0.5 && size > min) {
        size -= 0.5;
        el.style.fontSize = `${size}px`;
      }
      // Still too long at the smallest size: two lines rather than cut off.
      // Two lines leave more room, so a size up from the smallest.
      if (el.scrollWidth > el.clientWidth + 0.5) {
        el.style.whiteSpace = "normal";
        el.style.lineHeight = "1.15";
        el.style.fontSize = `${min + 2}px`;
      }
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el.parentElement ?? el);
    return () => observer.disconnect();
  }, [children, min]);

  return (
    <span
      ref={ref}
      style={{ display: "block", minWidth: 0, flex: "0 1 auto", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
    >
      {children}
    </span>
  );
}
