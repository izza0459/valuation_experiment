"use client";

/**
 * The valuations look on top of the vendored components, which stay
 * unmodified (they set their styles inline, so a theme file can't reach
 * weight, corners or per-variant colour). index.ts exports these in their
 * place.
 *
 * Buttons, as on Bayut: bold labels, 8px corners; primary solid teal,
 * outline (secondary) pale teal with teal text, ghost a bold teal text
 * button, danger bold red text. Avatars get a steady colour per person.
 */

import React from "react";
import { Avatar as BaseAvatar } from "./components/core/Avatar.jsx";
import { Button as BaseButton } from "./components/core/Button.jsx";

type ButtonProps = React.ComponentProps<typeof BaseButton>;

const SIZES: Record<string, React.CSSProperties> = {
  sm: { height: 30, padding: "0 12px", fontSize: 13 },
  md: { height: 34, padding: "0 16px", fontSize: 14 },
  lg: { height: 40, padding: "0 20px", fontSize: 15 },
};

const VARIANTS: Record<string, React.CSSProperties> = {
  outline: { background: "var(--accent-tint)", color: "var(--text-accent)", borderColor: "var(--accent-tint)" },
  danger: { background: "transparent", color: "var(--red-600)", borderColor: "transparent" },
};

export function Button({ variant = "primary", size = "md", style, ...rest }: ButtonProps) {
  return (
    <BaseButton
      variant={variant}
      size={size}
      style={{ fontWeight: 700, borderRadius: 8, ...SIZES[size as string], ...VARIANTS[variant as string], ...style }}
      {...rest}
    />
  );
}

// Distinct, readable on white text; one per person, always the same.
const AVATAR_COLOURS = ["#006169", "#2563a8", "#9a6100", "#6d4fc4", "#1f8a4f", "#b4436c", "#4b5563", "#c2410c"];

export function avatarColour(name: string): string {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLOURS[hash % AVATAR_COLOURS.length];
}

export function Avatar({ name = "", style, ...rest }: React.ComponentProps<typeof BaseAvatar>) {
  return <BaseAvatar name={name} style={{ background: avatarColour(name), fontWeight: 700, ...style }} {...rest} />;
}
