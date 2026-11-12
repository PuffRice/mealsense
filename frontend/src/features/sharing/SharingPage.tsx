import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Check,
  Clock,
  Eye,
  Mail,
  Phone,
  ShieldCheck,
  Stethoscope,
  Undo2,
  X,
} from "lucide-react";
import { Badge, EmptyState, GlassButton, GlassCard } from "../../design/ui";
import { doctorAccessApi } from "../../lib/api";
import type { DoctorAccessRequest } from "../../lib/types";

function formatWhen(value: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function statusBadge(
  status: DoctorAccessRequest["status"],
  expiresAt: string | null,
  nowMs: number,
) {
  if (status === "approved") {
    const active = expiresAt ? new Date(expiresAt).getTime() > nowMs : false;
    return (
      <Badge tone={active ? "green" : "neutral"}>
        {active ? "Active" : "Expired"}
      </Badge>
    );
  }
  if (status === "pending") return <Badge tone="peach">Waiting for you</Badge>;
  if (status === "denied") return <Badge tone="neutral">Denied</Badge>;
  return <Badge tone="danger">Revoked</Badge>;
}

export function SharingPage({ onDecided }: { onDecided: () => void }) {
  const [requests, setRequests] = useState<DoctorAccessRequest[]>([]);
  const [nowMs, setNowMs] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const loadRequests = useCallback(async () => {
    try {
      const list = await doctorAccessApi.list();
      setRequests(list);
      setNowMs(Date.now());
      setError("");
    } catch (cause: unknown) {
      setError(
        cause instanceof Error ? cause.message : "Could not load requests.",
      );
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadRequests);
    const timer = window.setInterval(() => void loadRequests(), 30000);
    return () => window.clearInterval(timer);
  }, [loadRequests]);

  async function decide(
    request: DoctorAccessRequest,
    action: "approve" | "deny" | "revoke",
  ) {
    if (action === "approve") {
      const ok = window.confirm(
        `Let ${request.doctor_name} see your meal history and nutrition analytics for 72 hours? They will not see photos, notes, or health metrics.`,
      );
      if (!ok) return;
    }
    if (
      action === "revoke" &&
      !window.confirm("Revoke this doctor's access now?")
    )
      return;
    setBusyId(request.id);
    try {
      await doctorAccessApi.decide(request.id, action);
      await loadRequests();
      onDecided();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not update the request.",
      );
    } finally {
      setBusyId(null);
    }
  }

  const pending = requests.filter((request) => request.status === "pending");
  const active = requests.filter(
    (request) =>
      request.status === "approved" &&
      Boolean(request.expires_at) &&
      new Date(request.expires_at as string).getTime() > nowMs,
  );
  const past = requests.filter(
    (request) => !pending.includes(request) && !active.includes(request),
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">WHO CAN SEE YOUR HISTORY</span>
          <h1>Sharing & access</h1>
          <p>
            A doctor can ask to review your meal history and nutrition
            analytics. Nothing is shared until you approve it, and you can
            revoke access at any time.
          </p>
        </div>
      </div>

      {error && (
        <motion.div
          initial={{ x: 80, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          className="error-banner"
          role="alert"
        >
          {error}
        </motion.div>
      )}

      <GlassCard className="list-card sharing-info">
        <div className="card-heading">
          <div>
            <h2>What a doctor can and cannot see</h2>
            <p>Approval lasts 72 hours, then access ends automatically.</p>
          </div>
          <span className="sharing-info__icon">
            <Eye size={18} />
          </span>
        </div>
        <div className="sharing-info__columns">
          <div className="sharing-info__col">
            <Badge tone="green">
              <Check size={12} /> Shared
            </Badge>
            <ul>
              <li>Your meal history as a list (foods, portions, calories)</li>
              <li>Most-consumed foods and how often you eat them</li>
              <li>Monthly and daily nutrition summaries</li>
              <li>The nutrition source behind each entry</li>
            </ul>
          </div>
          <div className="sharing-info__col">
            <Badge tone="danger">
              <X size={12} /> Never shared
            </Badge>
            <ul>
              <li>Meal photos</li>
              <li>Personal notes</li>
              <li>Weight, BMI, and goals</li>
              <li>Your password or account details</li>
            </ul>
          </div>
        </div>
      </GlassCard>

      {pending.length > 0 && (
        <GlassCard className="list-card">
          <div className="card-heading">
            <div>
              <h2>Access requests</h2>
              <p>Decide whether these doctors can view your history.</p>
            </div>
          </div>
          <div className="sharing-request-list">
            {pending.map((request) => (
              <motion.article
                key={request.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="sharing-request sharing-request--pending"
              >
                <span className="sharing-request__avatar">
                  <Stethoscope size={18} />
                </span>
                <div className="sharing-request__body">
                  <h3>{request.doctor_name}</h3>
                  <p>
                    Sent a request {formatWhen(request.created_at)} · found you
                    by{" "}
                    {request.identifier_type === "email" ? (
                      <>
                        <Mail size={12} /> email
                      </>
                    ) : (
                      <>
                        <Phone size={12} /> phone
                      </>
                    )}
                  </p>
                </div>
                <div className="sharing-request__actions">
                  <GlassButton
                    size="sm"
                    disabled={busyId === request.id}
                    icon={<Check size={14} />}
                    onClick={() => void decide(request, "approve")}
                  >
                    Approve
                  </GlassButton>
                  <GlassButton
                    size="sm"
                    variant="secondary"
                    disabled={busyId === request.id}
                    icon={<X size={14} />}
                    onClick={() => void decide(request, "deny")}
                  >
                    Deny
                  </GlassButton>
                </div>
              </motion.article>
            ))}
          </div>
        </GlassCard>
      )}

      {active.length > 0 && (
        <GlassCard className="list-card">
          <div className="card-heading">
            <div>
              <h2>Active access</h2>
              <p>Doctors currently allowed to view your history.</p>
            </div>
          </div>
          <div className="sharing-request-list">
            {active.map((request) => (
              <article key={request.id} className="sharing-request">
                <span className="sharing-request__avatar sharing-request__avatar--active">
                  <ShieldCheck size={18} />
                </span>
                <div className="sharing-request__body">
                  <h3>{request.doctor_name}</h3>
                  <p>
                    <Clock size={12} /> Access ends{" "}
                    {formatWhen(request.expires_at)}
                  </p>
                </div>
                <div className="sharing-request__actions">
                  <GlassButton
                    size="sm"
                    variant="danger"
                    disabled={busyId === request.id}
                    icon={<Undo2 size={14} />}
                    onClick={() => void decide(request, "revoke")}
                  >
                    Revoke
                  </GlassButton>
                </div>
              </article>
            ))}
          </div>
        </GlassCard>
      )}

      <GlassCard className="list-card">
        <div className="card-heading">
          <div>
            <h2>Past requests</h2>
            <p>Denied, revoked, and expired access.</p>
          </div>
        </div>
        {!loaded ? (
          <p className="sharing-loading">Loading…</p>
        ) : past.length ? (
          <div className="sharing-request-list sharing-request-list--muted">
            {past.map((request) => (
              <article key={request.id} className="sharing-request">
                <span className="sharing-request__avatar sharing-request__avatar--muted">
                  <Stethoscope size={16} />
                </span>
                <div className="sharing-request__body">
                  <h3>{request.doctor_name}</h3>
                  <p>
                    {request.identifier_type === "email" ? "Email" : "Phone"}{" "}
                    request · {formatWhen(request.created_at)}
                    {request.denied_at &&
                      ` · denied ${formatWhen(request.denied_at)}`}
                    {request.revoked_at &&
                      ` · revoked ${formatWhen(request.revoked_at)}`}
                  </p>
                </div>
                <div>
                  {statusBadge(request.status, request.expires_at, nowMs)}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<Stethoscope size={24} />}
            title="No sharing history yet"
            text="When a doctor asks for access, the request shows up here for you to approve or deny."
          />
        )}
      </GlassCard>
    </>
  );
}
