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
// (./notifications.js).
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
        if (reconnected) bus.emitReconnect();
      },
    });
    return () => client.close();
  }, [accountId, bus, getAccessTokenSilently]);

  return (
    <NotificationsContext.Provider value={bus}>
      {children}
    </NotificationsContext.Provider>
  );
}
