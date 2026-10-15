"use client";

import { useState } from "react";
import { Button, Icon, Input, Table, Tag } from "@/design-system";
import { Chip, F, Toggle } from "@/components/vp/ui";
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
  const [form, setForm] = useState({
    email: "", first_name: "", last_name: "", roles: [] as string[], is_active: true, password: "",
  });
  const [profile, setProfile] = useState<Profile>(BLANK);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(user: User | "new") {
    setEditing(user);
    setErrors({});
    if (user === "new") {
      setForm({ email: "", first_name: "", last_name: "", roles: [], is_active: true, password: "" });
      setProfile(BLANK);
    } else {
      setForm({ ...user, password: "" });
      setProfile({ ...BLANK, ...(user.valuer_profile ?? {}), rera_licence_expiry: user.valuer_profile?.rera_licence_expiry ?? "" });
    }
  }

  async function submit() {
    const body: Record<string, unknown> = {
      email: form.email, first_name: form.first_name, last_name: form.last_name,
      roles: form.roles, is_active: form.is_active,
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

  const toggleRole = (role: string) =>
    setForm((f) => ({ ...f, roles: f.roles.includes(role) ? f.roles.filter((r) => r !== role) : [...f.roles, role] }));

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <div style={muted}>People, their roles, and the credentials printed on reports. Users are deactivated, never deleted.</div>
        <Button size="sm" icon={<Icon name="plus" size={16} />} onClick={() => open("new")}>
          Add user
        </Button>
      </div>

      {isLoading ? (
        <div className="skel" style={{ height: 180 }} />
      ) : !users?.length ? (
        <Empty>No users yet.</Empty>
      ) : (
        <Table
          rows={users}
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
            { key: "licence", label: "RERA licence", render: (u: User) => licenceTag(u.licence) },
            { key: "is_active", label: "Status", render: (u: User) => <Tag tone={u.is_active ? "green" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</Tag> },
            { key: "edit", label: "", align: "right", render: (u: User) => (
              <Button size="sm" variant="outline" onClick={() => open(u)}>Edit</Button>
            ) },
          ]}
        />
      )}

      <FormDialog
        open={editing !== null}
        title={editing === "new" ? "Add user" : "Edit user"}
        subtitle={editing !== "new" ? undefined : "They can sign in once a password is set."}
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
          <F label="Roles" span={2} error={errors.roles} helper="Default roles. What someone does on a given job is set on the job itself.">
            <div className="row wrap" style={{ gap: 6 }}>
              {Object.entries(ROLE_LABELS).map(([key, label]) => (
                <Chip key={key} on={form.roles.includes(key)} onClick={() => toggleRole(key)}>{label}</Chip>
              ))}
            </div>
          </F>
          <F
            label={editing === "new" ? "Password" : "New password"}
            span={2}
            error={errors.password}
            helper={editing === "new" ? "Leave blank to create the account without sign-in." : "Leave blank to keep the current password."}
          >
            <Input type="password" autoComplete="new-password" invalid={Boolean(errors.password)} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </F>
          <F label="Account" span={2}>
            <Toggle on={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label={form.is_active ? "Active" : "Inactive: can't sign in"} />
          </F>
        </Grid>

        <h4 style={{ margin: "22px 0 4px", fontSize: 15, fontWeight: 500 }}>Valuer credentials</h4>
        <div style={{ ...muted, marginBottom: 12 }}>
          Printed on reports. A signing valuer needs a valid RERA licence before a job can be issued.
        </div>
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
  );
}
