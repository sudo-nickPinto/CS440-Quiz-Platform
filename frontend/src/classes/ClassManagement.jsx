import { useState } from "react";
import { Link } from "react-router";
import { useAccount } from "../authenticated-demo/account";

import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import CopyCodeButton from "../authenticated-demo/CopyCodeButton";
import { useConfirm } from "../authenticated-demo/useConfirm";
import { ResourceMessage } from "./ClassUI";
import { MEMBER_SORTS, membersWithStats } from "./classHelpers";
import { useClassStudentStats } from "./classResources";

function formatAverage(value) {
  return value === null || value === undefined
    ? "—"
    : Number(value).toLocaleString();
}

function formatAttendance(value) {
  return value === null || value === undefined
    ? "—"
    : `${Math.round(value * 100)}%`;
}

// Everyone in the class once each, with their role and, for students, their
// scores. A student's name opens their class report.
export function ClassMembers({ classInfo, onChange }) {
  const account = useAccount();
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();

  const resource = useResource(`/classes/${classInfo.id}/members`);
  const invitesResource = useResource(`/classes/${classInfo.id}/invites`);
  const stats = useClassStudentStats(classInfo.id);

  const [email, setEmail] = useState("");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState("name");

  function refreshLists() {
    resource.reload();
    invitesResource.reload();
    stats.reload();
  }

  function refreshAfterMemberChange(member) {
    if (Number(member.account_id) === Number(account.account_id)) {
      // Recheck access when the signed-in user's own membership changes.
      onChange();
    } else {
      // Keep the workspace and its selected Students tab mounted.
      resource.reload();
      stats.reload();
    }
  }

  const members = Array.isArray(resource.data) ? resource.data : [];

  const visible = membersWithStats(members, stats.data, sortKey).filter((member) =>
    `${member.display_name ?? ""} ${member.email}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );

  // Organizers aren't scored; "…" while the scores are still loading.
  function scoreCell(member, field, format) {
    if (member.role === "ORGANIZER") return "—";
    if (stats.loading) return "…";
    return format(member.stats?.[field]);
  }

  async function inviteMember(event) {
    event.preventDefault();

    const invited = await action.run(() =>
      api(`/classes/${classInfo.id}/invites`, {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      }),
    );

    if (invited) {
      setEmail("");
      invitesResource.reload();
    }
  }

  async function cancelInvitation(invitation) {
    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}/invites/${invitation.account_id}`, {
        method: "DELETE",
      });

      return true;
    });

    if (succeeded) {
      refreshLists();
    }
  }
  async function changeRole(member) {
    const nextRole = member.role === "ORGANIZER" ? "MEMBER" : "ORGANIZER";

    const confirmed = await confirmer.confirm({
      label: "Change role",
      title: `Make ${member.display_name || member.email} ${
        nextRole === "ORGANIZER" ? "an organizer" : "a member"
      }?`,
      message:
        nextRole === "ORGANIZER"
          ? "Organizers can invite, remove and manage members."
          : "They will no longer be able to manage this class.",
      confirmLabel: nextRole === "ORGANIZER" ? "Make organizer" : "Make member",
    });

    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}/members/${member.account_id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: nextRole }),
      });
      return true;
    });

    if (succeeded) {
      refreshAfterMemberChange(member);
    }
  }

  async function removeMember(member) {
    const confirmed = await confirmer.confirm({
      label: "Remove member",
      title: `Remove ${member.display_name || member.email}?`,
      message: "They will lose access to this class.",
      confirmLabel: "Remove",
    });

    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}/members/${member.account_id}`, {
        method: "DELETE",
      });
      return true;
    });

    if (succeeded) {
      refreshAfterMemberChange(member);
    }
  }

  if (resource.loading) {
    return <ResourceMessage resource={{ status: "loading" }} />;
  }

  if (resource.error) {
    return (
      <ResourceMessage
        resource={{
          status:
            resource.error.status === 403
              ? "forbidden"
              : resource.error.status === 404
                ? "not-found"
                : "error",
          error: resource.error,
          reload: resource.reload,
        }}
      />
    );
  }

  if (!Array.isArray(resource.data)) {
    return (
      <ResourceMessage
        resource={{
          status: "error",
          error: new Error("The member list could not be read."),
          reload: resource.reload,
        }}
      />
    );
  }

  return (
    <section aria-label="Class members">
      <ConfirmDialog confirmer={confirmer} />

      {action.error && (
        <p className="cl-feedback cl-error" role="alert">
          {action.error.message}
        </p>
      )}

      <form className="cl-inline-panel" onSubmit={inviteMember}>
        <h2>Invite a member</h2>

        <label>
          Account email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            disabled={action.busy || classInfo.archived}
          />
        </label>

        <button
          type="submit"
          disabled={action.busy || classInfo.archived || !email.trim()}
        >
          Invite member
        </button>

        <p>
          Invite someone who already has a QuizBurg account. They must accept
          the invitation before joining the class.
        </p>

        {classInfo.archived && (
          <p>This class is archived. New invitations are disabled.</p>
        )}
      </form>

      <section
        className="cl-invitations"
        aria-labelledby="pending-invitations-heading"
      >
        <h2 id="pending-invitations-heading">Pending invitations</h2>

        {invitesResource.loading ? (
          <p role="status">Loading invitations…</p>
        ) : invitesResource.error ? (
          <div>
            <p role="alert">{invitesResource.error.message}</p>

            <button
              type="button"
              onClick={invitesResource.reload}
              disabled={action.busy}
            >
              Retry invitations
            </button>
          </div>
        ) : !Array.isArray(invitesResource.data) ? (
          <div>
            <p role="alert">The invitation list could not be read.</p>

            <button
              type="button"
              onClick={invitesResource.reload}
              disabled={action.busy}
            >
              Retry invitations
            </button>
          </div>
        ) : invitesResource.data.length === 0 ? (
          <p>No pending invitations.</p>
        ) : (
          invitesResource.data.map((invitation) => (
            <div className="cl-invitation" key={invitation.account_id}>
              <div>
                <strong>{invitation.display_name || invitation.email}</strong>
                {invitation.display_name &&
                  invitation.display_name !== invitation.email && (
                    <p>{invitation.email}</p>
                  )}
              </div>

              <button
                type="button"
                disabled={action.busy}
                onClick={() => cancelInvitation(invitation)}
              >
                Cancel invitation
              </button>
            </div>
          ))
        )}
      </section>

      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">Search members</span>
          <input
            type="search"
            placeholder="Search members…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <label className="cl-sort">
          <span className="cl-sr">Sort members</span>
          <select
            value={sortKey}
            onChange={(event) => setSortKey(event.target.value)}
          >
            {Object.entries(MEMBER_SORTS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <span className="cl-count">
          {visible.length} {visible.length === 1 ? "member" : "members"}
        </span>

        <button
          type="button"
          onClick={refreshLists}
          disabled={action.busy || invitesResource.loading}
        >
          Refresh members and invitations
        </button>
      </div>

      {stats.error && (
        <p className="cl-feedback cl-error" role="alert">
          Scores could not be loaded: {stats.error.message}{" "}
          <button type="button" onClick={stats.reload}>
            Retry scores
          </button>
        </p>
      )}

      <div className="cl-table-wrap">
        <table className="cl-table cl-members-table">
          <caption className="cl-sr">Active class members</caption>

          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              <th scope="col">Average</th>
              <th scope="col">Attendance</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>

          <tbody>
            {visible.map((member) => (
              <tr key={member.account_id}>
                <td>
                  {member.role === "MEMBER" ? (
                    <Link
                      to={`/app/classes/${classInfo.id}/students/${member.account_id}/report`}
                      title="Open this student's class report"
                    >
                      {member.display_name || member.email}
                    </Link>
                  ) : (
                    member.display_name || member.email
                  )}
                </td>
                <td>{member.email}</td>
                <td>{member.role === "ORGANIZER" ? "Organizer" : "Member"}</td>
                <td>{scoreCell(member, "average_score", formatAverage)}</td>
                <td>
                  {scoreCell(member, "attendance_rate", formatAttendance)}
                </td>
                <td>
                  <div className="cl-actions">
                    <button
                      type="button"
                      disabled={action.busy || classInfo.archived}
                      onClick={() => changeRole(member)}
                    >
                      {member.role === "ORGANIZER"
                        ? "Make member"
                        : "Make organizer"}
                    </button>

                    <button
                      type="button"
                      disabled={action.busy || classInfo.archived}
                      onClick={() => removeMember(member)}
                    >
                      Remove
                    </button>
                  </div>
                </td>
              </tr>
            ))}

            {visible.length === 0 && (
              <tr>
                <td colSpan={6}>No matching members.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="cl-section-note">
        The last active organizer cannot be removed or changed to a member.
      </p>
    </section>
  );
}

export function ClassSettings({ classInfo, onChange }) {
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();

  const [name, setName] = useState(classInfo.name);
  const [joiningOpen, setJoiningOpen] = useState(classInfo.joiningOpen);

  async function saveSettings(event) {
    event.preventDefault();

    if (!name.trim()) return;

    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: name.trim(),
          joining_open: joiningOpen,
        }),
      });
      return true;
    });

    if (succeeded) onChange();
  }

  async function regenerateCode() {
    const confirmed = await confirmer.confirm({
      label: "Class code",
      title: "Generate a new class code?",
      message:
        "The previous code will stop working and the class code will be " +
        "enabled.",
      confirmLabel: "Generate code",
    });

    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}/code`, {
        method: "POST",
      });
      return true;
    });

    if (succeeded) onChange();
  }

  async function archiveClass() {
    const confirmed = await confirmer.confirm({
      label: "Archive class",
      title: "Archive this class?",
      message:
        "Its class code will be removed. There is currently no restore " +
        "action.",
      confirmLabel: "Archive class",
    });

    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}/archive`, {
        method: "POST",
      });
      return true;
    });

    if (succeeded) onChange();
  }

  return (
    <section className="cl-settings" aria-labelledby="settings-heading">
      <ConfirmDialog confirmer={confirmer} />

      <h2 id="settings-heading">Class settings</h2>

      {action.error && (
        <p className="cl-feedback cl-error" role="alert">
          {action.error.message}
        </p>
      )}

      {classInfo.archived && <p role="status">This class is archived.</p>}

      <form className="cl-settings-form" onSubmit={saveSettings}>
        <label>
          Class name
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={100}
            required
            disabled={action.busy || classInfo.archived}
          />
        </label>

        <label className="cl-checkbox">
          <input
            type="checkbox"
            checked={joiningOpen}
            onChange={(event) => setJoiningOpen(event.target.checked)}
            disabled={action.busy || classInfo.archived}
          />
          Class code enabled
        </label>

        <button
          type="submit"
          disabled={action.busy || classInfo.archived || !name.trim()}
        >
          Save settings
        </button>
      </form>

      <div className="cl-settings-block">
        <h3>Class code</h3>
        <p className="cl-code-value">
          {classInfo.code || "No class code"}{" "}
          <CopyCodeButton code={classInfo.code} label="class code" />
        </p>
        {classInfo.code && classInfo.joiningOpen ? (
          <p>
            Members join from <strong>Classes → Join class</strong> with this code,
            or by opening{" "}
            <code>{`${window.location.origin}/app/join/class/${classInfo.code}`}</code>
            .{" "}
            <CopyCodeButton
              code={`${window.location.origin}/app/join/class/${classInfo.code}`}
              label="join link"
              className="ui-copy-code-small"
            />
          </p>
        ) : (
          <p>
            The class code is turned off. Turn it on above, or invite members
            by email.
          </p>
        )}

        <button
          type="button"
          onClick={regenerateCode}
          disabled={action.busy || classInfo.archived}
        >
          Generate new code
        </button>
      </div>

      <div className="cl-settings-block">
        <h3>Archive class</h3>
        <p>
          Archiving disables the class code and marks the class as archived.
        </p>

        <button
          type="button"
          onClick={archiveClass}
          disabled={action.busy || classInfo.archived}
        >
          Archive class
        </button>
      </div>
    </section>
  );
}
