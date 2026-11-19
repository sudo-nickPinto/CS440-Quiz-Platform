import { useEffect, useState } from "react";

import { useApi } from "../authenticated-demo/rest";
import { suggestionQuery } from "./rosterHelpers";

// Search-as-you-type for the "+ Add student" and "Add collaborator" boxes.
// After a short pause in typing it asks `${path}?q=...` and returns the
// matches; under two characters it returns []. A failed request also
// returns [] (typing a full email still works). `path` null turns it off.
//
// Raise `revision` to ask again for the same text, after something changed
// what the results say (someone added or removed). The current results stay
// on screen until the new ones arrive, so the list doesn't flicker.
export function useSuggestions(path, text, { revision = 0, delayMs = 250 } = {}) {
  const api = useApi();
  const query = path ? suggestionQuery(text) : "";
  const [result, setResult] = useState({ key: "", items: [] });
  const key = `${path}?${query}`;

  useEffect(() => {
    if (!query) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const items = await api(`${path}?q=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setResult({ key, items: Array.isArray(items) ? items : [] });
        }
      } catch {
        if (!controller.signal.aborted) setResult({ key, items: [] });
      }
    }, delayMs);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [api, path, query, key, delayMs, revision]);

  return query && result.key === key ? result.items : [];
}
