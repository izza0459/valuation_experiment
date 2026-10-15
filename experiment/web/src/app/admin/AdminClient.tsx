"use client";

/** Admin (design brief S8): the masters the rest of the app reads from. */

import { useState } from "react";
import Link from "next/link";
import { Tabs } from "@/design-system";
import { BanksPanel } from "@/components/admin/BanksPanel";
import { LibraryPanel } from "@/components/admin/LibraryPanel";
import { PresetsPanel } from "@/components/admin/PresetsPanel";
import { TemplatesPanel } from "@/components/admin/TemplatesPanel";
import { UsersPanel } from "@/components/admin/UsersPanel";
import { PageHead, Shell } from "@/components/vp/ui";
import { useMe } from "@/lib/auth";

const PANELS = {
  "Users & valuers": UsersPanel,
  Banks: BanksPanel,
  Dropdowns: PresetsPanel,
  "Text library": LibraryPanel,
  "Report templates": TemplatesPanel,
} as const;

type PanelName = keyof typeof PANELS;

export function AdminClient() {
  const { data: me } = useMe();
  const [tab, setTab] = useState<PanelName>("Users & valuers");

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

  const Panel = PANELS[tab];
  return (
    <Shell>
      <PageHead title="Admin" sub="Users, banks and the lists the forms and reports draw on." />
      <div style={{ marginBottom: 16 }}>
        <Tabs items={Object.keys(PANELS)} active={tab} onChange={(label) => setTab(label as PanelName)} />
      </div>
      <Panel />
    </Shell>
  );
}
