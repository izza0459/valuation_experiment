"use client";

/**
 * The conflict-of-interest check (CRM feedback LG-01) as one card: what the
 * system found (earlier instructions for this property or applicant in the
 * last 12 months, each linked), then the answer below it, and who gave it.
 */

import Link from "next/link";
import { Icon } from "@/design-system";
import { useJob } from "@/lib/jobs";
import { formatDate, formatDateTime } from "./format";
import { Tip } from "./ui";

export function CoiCard({ jobId }: { jobId: string }) {
  const { data: job } = useJob(jobId);
  const coi = job?.coi;
  if (!coi) return null;
  const found = coi.matches.length;
  const tone = found ? ["var(--amber-50)", "var(--amber-600)", "alert-triangle"] : ["var(--green-50)", "var(--green-600)", "shield-check"];
  return (
    <div className="coi-card" style={{ background: tone[0], borderColor: `${tone[1]}55` }}>
      <div className="row" style={{ gap: 10, alignItems: "flex-start" }}>
        <Icon name={tone[2]} size={20} color={tone[1]} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row" style={{ gap: 6, fontWeight: 700, fontSize: 15 }}>
            {found ? `${found} possible conflict${found === 1 ? "" : "s"} found` : "No conflict found"}
            <Tip text="Instructions in the last 12 months for the same unit and building, plot and property number, or applicant. Answer Yes if any is a real conflict; Yes needs the client's consent uploaded." />
          </div>
          <div style={{ fontSize: 13.5, color: "var(--text-secondary)", marginTop: 2 }}>
            Suggested answer: <b>{found ? "Yes" : "No"}</b>
          </div>
          {found > 0 && (
            <div className="stack8" style={{ marginTop: 10 }}>
              {coi.matches.map((m) => (
                <Link key={m.id} href={`/jobs/${m.id}`} target="_blank" className="coi-match">
                  <span style={{ minWidth: 0 }}>
                    <b className="num">{m.ref}</b> · {m.property}
                    <span style={{ display: "block", fontSize: 12.5, color: "var(--text-muted)" }}>
                      {m.why[0].toUpperCase() + m.why.slice(1)} · {formatDate(m.created_at)} · {m.status}
                    </span>
                  </span>
                  <Icon name="external-link" size={15} />
                </Link>
              ))}
            </div>
          )}
          {coi.confirmed_at && (
            <div className="row" style={{ gap: 6, fontSize: 12.5, color: "var(--text-muted)", marginTop: 10 }}>
              <Icon name="user-check" size={14} />
              Answered {coi.result === "yes" ? "Yes" : coi.result === "no" ? "No" : ""} by {coi.confirmed_by},{" "}
              {formatDateTime(coi.confirmed_at)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
