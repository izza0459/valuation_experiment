"use client";

import { useState } from "react";
import { Button, Icon, Input, Select, Table, Tag } from "@/design-system";
import { MultiDropdown } from "@/components/vp/FieldInput";
import { F, Tip, Toggle } from "@/components/vp/ui";
import { flattenErrors, emptyToNull, useAdminList, useAdminSave } from "@/lib/admin";
import { ROLE_LABELS } from "@/lib/auth";
import { Empty, FormDialog, Grid, muted } from "./parts";

type Licence = { state: "valid" | "expiring" | "expired" | "missing"; days_left: number | null };
type Profile = {
  rera_registration_no: string;
  rics_membership_no: string;
  qualifications: string;
  title: string;
  rera_licence_expiry: string | null;
};
type User = {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  roles: string[];
  is_active: boolean;
  valuer_profile: Profile | null;
  licence: Licence;
  manager: number | null;
  manager_name: string;
  team_size: number;
  access_request: "" | "pending" | "declined";
  access_requested_at: string | null;
};

const BLANK: Profile = {
  rera_registration_no: "",
  rics_membership_no: "",
  qualifications: "",
  title: "",
  rera_licence_expiry: "",
};

export function licenceTag(l: Licence) {
  if (l.state === "valid") return <Tag tone="green">Valid · {l.days_left}d</Tag>;
  if (l.state === "expiring") return <Tag tone="amber">Expires in {l.days_left}d</Tag>;
  if (l.state === "expired") return <Tag tone="red">Expired</Tag>;
  return <span style={muted}>Not set</span>;
}

export function UsersPanel() {
  const { data: users, isLoading } = useAdminList<User>("users/");
  const save = useAdminSave("users");
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState({
    email: "", first_name: "", last_name: "", roles: [] as string[], is_active: true, password: "",
    manager: "" as string,
  });
  const [profile, setProfile] = useState<Profile>(BLANK);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(user: User | "new") {
    setEditing(user);
    setErrors({});
    if (user === "new") {
      setForm({ email: "", first_name: "", last_name: "", roles: [], is_active: true, password: "", manager: "" });
      setProfile(BLANK);
    } else {
      // Opening someone waiting for access is approving them.
      setForm({ ...user, password: "", manager: user.manager ? String(user.manager) : "",
        is_active: user.access_request === "pending" ? true : user.is_active });
      setProfile({ ...BLANK, ...(user.valuer_profile ?? {}), rera_licence_expiry: user.valuer_profile?.rera_licence_expiry ?? "" });
    }
  }

  async function submit() {
    const body: Record<string, unknown> = {
      email: form.email, first_name: form.first_name, last_name: form.last_name,
      roles: form.roles, is_active: form.is_active, manager: form.manager ? Number(form.manager) : null,
    };
    if (form.password) body.password = form.password;
    const hasProfile = Object.values(profile).some((v) => v);
    if (hasProfile) body.valuer_profile = { ...profile, rera_licence_expiry: emptyToNull(profile.rera_licence_expiry ?? "") };
    try {
      await save.mutateAsync({ id: editing === "new" ? undefined : (editing as User).id, body });
      setEditing(null);
    } catch (err) {
      setErrors(flattenErrors(err));
    }
  }

  const waiting = (users ?? []).filter((u) => u.access_request === "pending");
  const term = search.trim().toLowerCase();
  const listed = (users ?? []).filter(
    (u) => u.access_request !== "pending" && (!term || `${u.name} ${u.email}`.toLowerCase().includes(term)),
  );
  const editingId = editing && editing !== "new" ? editing.id : null;
  const managers = (users ?? []).filter((u) => u.is_active && u.id !== editingId);

  async function decline(user: User) {
    await save.mutateAsync({ id: user.id, body: { access_request: "declined" } }).catch(() => undefined);
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {waiting.length > 0 && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)" }}>
          <div className="row" style={{ gap: 6, fontSize: 16, fontWeight: 500, marginBottom: 12 }}>
            Waiting for access
            <Tip text="Signed in with Google but not added yet. Approve to choose their roles and manager; they can then sign in." />
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            {waiting.map((u) => (
              <div key={u.id} className="row wrap" style={{ justifyContent: "space-between", gap: 10 }}>
                <div>
                  <div>{u.name}</div>
                  <div style={muted}>{u.email}</div>
                </div>
                <div className="row" style={{ gap: 8 }}>
                  <Button size="sm" variant="outline" onClick={() => void decline(u)}>Decline</Button>
                  <Button size="sm" onClick={() => open(u)}>Approve</Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    <div className="card">
      <div className="row wrap" style={{ justifyContent: "space-between", marginBottom: 14, gap: 10 }}>
        <div className="row" style={{ gap: 8, flex: "1 1 260px" }}>
          <Input placeholder="Search name or email" value={search} style={{ maxWidth: 320 }}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)} />
          <Tip text="People, their roles, who they report to, and the credentials printed on reports. Users are deactivated, never deleted." />
        </div>
        <Button size="sm" icon={<Icon name="plus" size={16} />} onClick={() => open("new")}>
          Add user
        </Button>
      </div>

      {isLoading ? (
        <div className="skel" style={{ height: 180 }} />
      ) : !listed.length ? (
        <Empty>{term ? "Nobody matches." : "No users yet."}</Empty>
      ) : (
        <Table
          rows={listed}
          columns={[
            { key: "name", label: "Name", render: (u: User) => (
              <div>
                <div>{u.name}</div>
                <div style={muted}>{u.email}</div>
              </div>
            ) },
            { key: "roles", label: "Roles", render: (u: User) =>
              u.roles.length ? (
                <span className="row wrap" style={{ gap: 4 }}>
                  {u.roles.map((r) => <Tag key={r} tone="neutral">{ROLE_LABELS[r] ?? r}</Tag>)}
                </span>
              ) : <span style={muted}>None</span> },
            { key: "manager", label: "Reports to", render: (u: User) => (
              <div>
                <div>{u.manager_name || <span style={muted}>Nobody</span>}</div>
                {u.team_size > 0 && <div style={muted}>Manages {u.team_size}</div>}
              </div>
            ) },
            { key: "licence", label: "RERA licence", render: (u: User) => licenceTag(u.licence) },
            { key: "is_active", label: "Status", render: (u: User) => (
              <Tag tone={u.is_active ? "green" : "neutral"}>
                {u.is_active ? "Active" : u.access_request === "declined" ? "Declined" : "Inactive"}
              </Tag>
            ) },
            { key: "edit", label: "", align: "right", render: (u: User) => (
              <Button size="sm" variant="outline" onClick={() => open(u)}>Edit</Button>
            ) },
          ]}
        />
      )}

      <FormDialog
        open={editing !== null}
        title={editing === "new" ? "Add user" : editing?.access_request === "pending" ? "Approve access" : "Edit user"}
        busy={save.isPending}
        error={errors._form}
        onClose={() => setEditing(null)}
        onSave={() => void submit()}
      >
        <Grid>
          <F label="First name" error={errors.first_name}>
            <Input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          </F>
          <F label="Last name" error={errors.last_name}>
            <Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </F>
          <F label="Email" span={2} error={errors.email}>
            <Input type="email" invalid={Boolean(errors.email)} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </F>
          <F label="Roles" error={errors.roles} helper="Default roles. What someone does on a given job is set on the job itself.">
            <MultiDropdown
              value={form.roles}
              options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))}
              custom={false}
              onChange={(v) => setForm({ ...form, roles: v as string[] })}
            />
          </F>
          <F label="Reports to" error={errors.manager} helper="Their manager sees their leads on the Dashboard, with everyone else below them.">
            <Select
              value={form.manager}
              placeholder="Nobody"
              options={managers.map((u) => ({ value: String(u.id), label: u.name }))}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, manager: e.target.value })}
            />
          </F>
          <F
            label={editing === "new" ? "Password" : "New password"}
            span={2}
            error={errors.password}
            optional
            helper={editing === "new" ? "Leave blank: they sign in with their Google account." : "Leave blank to keep the current password."}
          >
            <Input type="password" autoComplete="new-password" invalid={Boolean(errors.password)} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </F>
          <F label="Account" span={2}>
            <Toggle on={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label={form.is_active ? "Active" : "Inactive: can't sign in"} />
          </F>
        </Grid>

        <h4 className="row" style={{ margin: "22px 0 12px", fontSize: 15, fontWeight: 500, gap: 6 }}>
          Valuer credentials
          <Tip text="Printed on reports. A signing valuer needs a valid RERA licence before a job can be issued." />
        </h4>
        <Grid>
          <F label="RERA registration no." error={errors.rera_registration_no}>
            <Input value={profile.rera_registration_no} onChange={(e) => setProfile({ ...profile, rera_registration_no: e.target.value })} />
          </F>
          <F label="RERA licence expiry" error={errors.rera_licence_expiry}>
            <Input type="date" value={profile.rera_licence_expiry ?? ""} onChange={(e) => setProfile({ ...profile, rera_licence_expiry: e.target.value })} />
          </F>
          <F label="RICS membership no." error={errors.rics_membership_no}>
            <Input value={profile.rics_membership_no} onChange={(e) => setProfile({ ...profile, rics_membership_no: e.target.value })} />
          </F>
          <F label="Title" error={errors.title}>
            <Input value={profile.title} onChange={(e) => setProfile({ ...profile, title: e.target.value })} />
          </F>
          <F label="Qualifications" span={2} error={errors.qualifications}>
            <Input value={profile.qualifications} onChange={(e) => setProfile({ ...profile, qualifications: e.target.value })} />
          </F>
        </Grid>
      </FormDialog>
    </div>
    </div>
  );
}
