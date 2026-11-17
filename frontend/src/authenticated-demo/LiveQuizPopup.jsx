import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import ConfirmDialog from "./ConfirmDialog";
import { isLiveGamePath, joinSession } from "./liveSessions";
import { useCatchUp, useNotifications } from "./notifications";
import { useAction, useApi } from "./rest";
import RequestError from "./RequestError";

// Join answers that mean the session is gone for this account (it ended, or
// they are no longer in its class).
const GONE_CODES = new Set(["session_not_joinable", "session_not_found"]);

// "A quiz is live": pops up on any signed-in page when a host opens a lobby in
// one of the caller's classes where they are a member (the server's
// session_live push with role MEMBER; co-organizers just see the Live button,
// and the host gets nothing). Join goes straight into the game like the class
// page's Live button. Only pushed events show it; sessions that were already
// live when the page loaded are covered by the Live button and the header's
// Join game link. No event says a lobby closed, so the popup rechecks when
// the tab comes back and closes quietly if the session is gone.
export default function LiveQuizPopup() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const api = useApi();
  const join = useAction();
  const [live, setLive] = useState(null);
  // Sessions dismissed (or joined) while this page is open don't pop again.
  const seen = useRef(new Set());
  // Where focus was when the popup opened, to put it back on Dismiss.
  const opener = useRef(null);
  const returnFocus = useRef(false);
  const inGame = isLiveGamePath(pathname);

  useNotifications("session_live", (event) => {
    if (event?.role !== "MEMBER") return;
    const id = event.session_id;
    if (id == null || seen.current.has(String(id))) return;
    // Never interrupt hosting or playing, and leave a join in progress alone.
    if (inGame || join.busy) return;
    if (!live) opener.current = document.activeElement;
    // A newer lobby replaces the one showing.
    join.clearError();
    setLive(event);
  });

  // Entering a game drops the popup instead of keeping it for later.
  if (inGame && live) setLive(null);

  useEffect(() => {
    if (live) return;
    const target = opener.current;
    opener.current = null;
    if (returnFocus.current && target?.isConnected) {
      target.focus({ preventScroll: true });
    }
    returnFocus.current = false;
  }, [live]);

  // Back in the tab: the class's active sessions (what its Live button
  // shows) say whether the session can still be joined. If the check fails,
  // keep the popup; Join will tell.
  useCatchUp(() => {
    if (!live || join.busy) return;
    const id = live.session_id;
    api(`/classes/${live.class_id}/active-sessions`).then(
      (sessions) => {
        const open =
          Array.isArray(sessions) &&
          sessions.some(
            (session) =>
              String(session.session_id) === String(id) && !session.left,
          );
        if (!open) close(id);
      },
      () => {},
    );
  });

  // Closes the popup for this session if it is still the one showing.
  function close(id) {
    seen.current.add(String(id));
    returnFocus.current = true;
    setLive((current) =>
      current && String(current.session_id) === String(id) ? null : current,
    );
  }

  function dismiss() {
    close(live.session_id);
  }

  async function joinLive() {
    const id = live.session_id;
    let gone = false;
    const joined = await join.run(async () => {
      try {
        return await joinSession(api, id);
      } catch (error) {
        if (!GONE_CODES.has(error?.code)) throw error;
        gone = true;
        return null;
      }
    });
    if (gone) {
      close(id);
      return;
    }
    if (!joined) return;
    seen.current.add(String(id));
    setLive(null);
    navigate(`/app/play/${id}`);
  }

  const request = live && {
    label: "Live now",
    title: "A quiz is live",
    confirmLabel: join.busy ? "Joining…" : "Join",
    cancelLabel: "Dismiss",
    busy: join.busy,
    details: (
      <>
        <div className="qb-live-popup">
          <p className="qb-live-popup-quiz">{live.quiz_title}</p>
          <p>{live.class_name}</p>
          <p>Hosted by {live.host_name}</p>
        </div>
        <RequestError error={join.error} />
      </>
    ),
  };

  return (
    <ConfirmDialog
      confirmer={{
        request,
        settle: (answer) => (answer ? joinLive() : dismiss()),
      }}
    />
  );
}
