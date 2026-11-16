import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import ConfirmDialog from "./ConfirmDialog";
import { isLiveGamePath, joinSession } from "./liveSessions";
import { useNotifications } from "./notifications";
import { useAction, useApi } from "./rest";
import RequestError from "./RequestError";

// "A quiz is live": pops up on any signed-in page when a host opens a lobby in
// one of the caller's classes (the server's session_live push; the host never
// gets one). Join goes straight into the game like the class page's Live
// button. Only pushed events show it; sessions that were already live when the
// page loaded are covered by the Live button and the header's Join game link.
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
    const id = event?.session_id;
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

  function dismiss() {
    seen.current.add(String(live.session_id));
    returnFocus.current = true;
    setLive(null);
  }

  async function joinLive() {
    const id = live.session_id;
    const joined = await join.run(() => joinSession(api, id));
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
