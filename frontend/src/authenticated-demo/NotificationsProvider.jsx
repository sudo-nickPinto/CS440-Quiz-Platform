import { useContext, useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";

import { AccountContext } from "./account";
import { createNotificationsBus, NotificationsContext } from "./notifications";
import {
  createNotificationsClient,
  notificationsSocketUrl,
} from "./notificationsClient";

// One notification socket for the signed-in app. Opens while there is an
// active account in AccountContext and closes on sign-out or unmount. Pages
// listen with useNotifications / useNotificationsReconnect / useCatchUp
// (./notifications.js). This is also the app's one focus/visibility listener
// for catching up, so pages don't each add their own.
export default function NotificationsProvider({ children }) {
  const account = useContext(AccountContext);
  const { getAccessTokenSilently } = useAuth0();
  const [bus] = useState(createNotificationsBus);
  const accountId = account?.is_active ? account.account_id : null;

  useEffect(() => {
    if (accountId == null) return undefined;
    const client = createNotificationsClient({
      url: notificationsSocketUrl(import.meta.env.VITE_API_BASE_URL),
      getToken: ({ freshToken } = {}) =>
        getAccessTokenSilently(freshToken ? { cacheMode: "off" } : undefined),
      onEvent: (event) => bus.emit(event),
      onReady: ({ reconnected }) => {
        if (!reconnected) return;
        bus.emitReconnect();
        // Events sent while the socket was down are not replayed.
        bus.catchUp({ force: true });
      },
    });
    return () => client.close();
  }, [accountId, bus, getAccessTokenSilently]);

  // The tab came back: timers may have been throttled and events missed
  // while it was hidden. Throttled inside the bus.
  useEffect(() => {
    function onReturn() {
      if (document.visibilityState !== "hidden") bus.catchUp();
    }
    window.addEventListener("focus", onReturn);
    document.addEventListener("visibilitychange", onReturn);
    return () => {
      window.removeEventListener("focus", onReturn);
      document.removeEventListener("visibilitychange", onReturn);
    };
  }, [bus]);

  return (
    <NotificationsContext.Provider value={bus}>
      {children}
    </NotificationsContext.Provider>
  );
}
