import { useState } from "react";

import {
  useAction,
  useApi,
  useResource,
} from "../authenticated-demo/rest";
import { ResourceMessage } from "./ClassUI";

export function ClassMembers({ classInfo, onChange }) {
  const api = useApi();
  const action = useAction();
  const resource = useResource(`/classes/${classInfo.id}/members`);

  const [email, setEmail] = useState("");
  const [query, setQuery] = useState("");
  const [sentInvites, setSentInvites] = useState([]);

  const members = Array.isArray(resource.data) ? resource.data : [];

  const visible = members.filter((member) =>
    `${member.display_name ?? ""} ${member.email}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );

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
      setSentInvites((current) => [
        ...current.filter(
          (item) => item.account_id !== invited.account_id,
        ),
        invited,
      ]);
    }
  }

  async function cancelInvitation(invitation) {
    const succeeded = await action.run(async () => {
      await api(
        `/classes/${classInfo.id}/invites/${invitation.account_id}`,
        { method: "DELETE" },
      );
      return true;
    });

    if (succeeded) {
      setSentInvites((current) =>
        current.filter(
          (item) => item.account_id !== invitation.account_id,
        ),
      );
    }
  }

  async function changeRole(member) {
    const nextRole =
      member.role === "ORGANIZER" ? "MEMBER" : "ORGANIZER";

    const confirmed = window.confirm(
      `Change ${member.display_name || member.email} to ${
        nextRole === "ORGANIZER" ? "organizer" : "member"
      }?`,
    );

    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(
        `/classes/${classInfo.id}/members/${member.account_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ role: nextRole }),
        },
      );
      return true;
    });

    // Reload class permissions too: the caller may have changed
    // their own organizer role.
    if (succeeded) onChange();
  }

  async function removeMember(member) {
    const confirmed = window.confirm(
      `Remove ${member.display_name || member.email} from this class?`,
    );

    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(
        `/classes/${classInfo.id}/members/${member.account_id}`,
        { method: "DELETE" },
      );
      return true;
    });

    // This also handles the caller removing their own membership.
    if (succeeded) onChange();
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
          disabled={
            action.busy || classInfo.archived || !email.trim()
          }
        >
          Invite member
        </button>

        <p>
          Invite someone who already has a QuizBurg account.
          They must accept the invitation before joining the class.
        </p>

        {classInfo.archived && (
          <p>This class is archived. New invitations are disabled.</p>
        )}
      </form>

      {sentInvites.length > 0 && (
        <section className="cl-invitations">
          <h2>Invitations created during this visit</h2>
          <p>
            Refresh the member list after an invitation is accepted.
          </p>

          {sentInvites.map((invitation) => (
            <div
              className="cl-invitation"
              key={invitation.account_id}
            >
              <span>{invitation.email}</span>

              <button
                type="button"
                disabled={action.busy}
                onClick={() => cancelInvitation(invitation)}
              >
                Cancel invitation
              </button>
            </div>
          ))}
        </section>
      )}

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

        <span className="cl-count">
          {visible.length} members
        </span>

        <button
          type="button"
          onClick={resource.reload}
          disabled={action.busy}
        >
          Refresh members
        </button>
      </div>

      <div className="cl-table-wrap">
        <table className="cl-table cl-members-table">
          <caption className="cl-sr">Active class members</caption>

          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>

          <tbody>
            {visible.map((member) => (
              <tr key={member.account_id}>
                <td>{member.display_name || member.email}</td>
                <td>{member.email}</td>
                <td>
                  {member.role === "ORGANIZER"
                    ? "Organizer"
                    : "Member"}
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
                <td colSpan={4}>No matching members.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="cl-section-note">
        The last active organizer cannot be removed or changed to a
        member.
      </p>
    </section>
  );
}

export function ClassSettings({ classInfo, onChange }) {
  const api = useApi();
  const action = useAction();

  const [name, setName] = useState(classInfo.name);
  const [joiningOpen, setJoiningOpen] = useState(
    classInfo.joiningOpen,
  );

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
    const confirmed = window.confirm(
      "Generate a new class code? The previous code will stop working " +
        "and the class code will be enabled.",
    );

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
    const confirmed = window.confirm(
      "Archive this class? Its class code will be removed. " +
        "There is currently no restore action.",
    );

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
      <h2 id="settings-heading">Class settings</h2>

      {action.error && (
        <p className="cl-feedback cl-error" role="alert">
          {action.error.message}
        </p>
      )}

      {classInfo.archived && (
        <p role="status">This class is archived.</p>
      )}

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
            onChange={(event) =>
              setJoiningOpen(event.target.checked)
            }
            disabled={action.busy || classInfo.archived}
          />
          Class code enabled
        </label>

        <button
          type="submit"
          disabled={
            action.busy || classInfo.archived || !name.trim()
          }
        >
          Save settings
        </button>
      </form>

      <div className="cl-settings-block">
        <h3>Class code</h3>
        <p className="cl-code-value">
          {classInfo.code || "No class code"}
        </p>
        <p>
          Joining by class code is not available yet. Use invitations
          to add members.
        </p>

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
          Archiving disables the class code and marks the class as
          archived.
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
