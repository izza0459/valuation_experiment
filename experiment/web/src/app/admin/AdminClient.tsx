"use client";

/** Admin (design brief S8): the masters the rest of the app reads from, one
 * section at a time from the list on the left (a dropdown on phones). */

import { useState } from "react";
import Link from "next/link";
import { Icon, Select } from "@/design-system";
import { BanksPanel } from "@/components/admin/BanksPanel";
import { EmailTemplatesPanel } from "@/components/admin/EmailTemplatesPanel";
import { LibraryPanel } from "@/components/admin/LibraryPanel";
import { PresetsPanel } from "@/components/admin/PresetsPanel";
import { TemplatesPanel } from "@/components/admin/TemplatesPanel";
import { UsersPanel } from "@/components/admin/UsersPanel";
import { PageHead, Shell } from "@/components/vp/ui";
import { useAdminList } from "@/lib/admin";
import { useMe } from "@/lib/auth";

const SECTIONS = [
  { key: "users", label: "Users & team", icon: "users", Panel: UsersPanel, group: "People" },
  { key: "banks", label: "Banks", icon: "landmark", Panel: BanksPanel, group: "Clients" },
  { key: "emails", label: "Email templates", icon: "mail", Panel: EmailTemplatesPanel, group: "Clients" },
  { key: "dropdowns", label: "Dropdowns", icon: "list", Panel: PresetsPanel, group: "Forms & reports" },
  { key: "library", label: "Text library", icon: "book-open", Panel: LibraryPanel, group: "Forms & reports" },
  { key: "templates", label: "Report templates", icon: "file-text", Panel: TemplatesPanel, group: "Forms & reports" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

export function AdminClient() {
  const { data: me } = useMe();
  const [key, setKey] = useState<SectionKey>("users");
  const { data: users } = useAdminList<{ access_request: string }>("users/");
  const waiting = (users ?? []).filter((u) => u.access_request === "pending").length;

  if (me?.authenticated && !me.user.is_admin) {
    return (
      <Shell>
        <div className="card" style={{ textAlign: "center", padding: "60px 24px" }}>
          <div style={{ fontSize: 17 }}>Only an admin can open this page.</div>
          <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 6 }}>
            <Link href="/jobs">Back to jobs</Link>
          </div>
        </div>
      </Shell>
    );
  }

  const section = SECTIONS.find((s) => s.key === key) ?? SECTIONS[0];
  const Panel = section.Panel;
  const groups = [...new Set(SECTIONS.map((s) => s.group))];
  return (
    <Shell>
      <PageHead title="Admin" sub={section.label} tip="Users, banks and the lists the forms and reports draw on." />
      <div className="admin-layout">
        <nav className="admin-nav hide-app" aria-label="Admin sections">
          {groups.map((group) => (
            <div key={group}>
              <div className="admin-nav-group">{group}</div>
              {SECTIONS.filter((s) => s.group === group).map((s) => (
                <button key={s.key} type="button" className={s.key === key ? "on" : ""} onClick={() => setKey(s.key)}>
                  <Icon name={s.icon} size={17} />
                  <span style={{ flex: 1 }}>{s.label}</span>
                  {s.key === "users" && waiting > 0 && <span className="admin-badge">{waiting}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="show-app" style={{ marginBottom: 12 }}>
          <Select
            value={key}
            options={SECTIONS.map((s) => ({
              value: s.key,
              label: s.key === "users" && waiting ? `${s.label} (${waiting} waiting)` : s.label,
            }))}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setKey(e.target.value as SectionKey)}
          />
        </div>
        <div style={{ minWidth: 0 }}>
          <Panel />
        </div>
      </div>
    </Shell>
  );
}
