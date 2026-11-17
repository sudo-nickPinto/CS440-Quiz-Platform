import { useEffect, useRef, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";

import {
  createQuizEditClient,
  quizEditSocketUrl,
} from "./quizCollaboration";

export function useQuizCollaboration(quizId, onMessage) {
  const { getAccessTokenSilently } = useAuth0();
  const callback = useRef(onMessage);
  const [status, setStatus] = useState(quizId ? "connecting" : "closed");

  useEffect(() => {
    callback.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!quizId) return undefined;
    const url = quizEditSocketUrl(
      import.meta.env.VITE_API_BASE_URL,
      quizId,
    );
    const client = createQuizEditClient({
      url,
      getToken: () => getAccessTokenSilently(),
      onMessage: (message) => callback.current?.(message),
      onStatus: setStatus,
    });
    return () => client.close();
  }, [getAccessTokenSilently, quizId]);

  return status;
}
