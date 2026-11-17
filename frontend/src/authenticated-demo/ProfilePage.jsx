import { Link } from "react-router";

import ProfileForm from "../components/ProfileForm";
import { useAccount } from "./account";
import "./profile-page.css";

export default function ProfilePage({ onSaved }) {
  const account = useAccount();

  return (
    <section>
      <div className="ui-titlebar">
        <span>Your profile</span>
        <span>Account</span>
      </div>

      <div className="qb-profile-page">
        <p className="ui-eyebrow">Account</p>

        <h1>
          Edit your <span className="ui-highlight">profile</span>
        </h1>

        <p>
          Signed in as <strong className="qb-profile-email">{account.email}</strong>.
          Your name and avatar show in lobbies and on leaderboards.
        </p>

        <ProfileForm
          account={account}
          submitLabel="Save changes"
          submitClassName="qp-primary"
          savedMessage="Saved. Your new name and avatar are live."
          onSaved={onSaved}
        >
          <Link className="qp-button" to="/app/classes">
            Back to classes
          </Link>
        </ProfileForm>
      </div>
    </section>
  );
}
