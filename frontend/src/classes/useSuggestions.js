import { useCallback, useEffect, useRef, useState } from "react";

import { useApi } from "../authenticated-demo/rest";
import { suggestionQuery } from "./rosterHelpers";

export const SUGGESTION_PAGE_SIZE = 20;

const EMPTY = { key: null, items: [], hasMore: false };

// Folds one page of results into what the list shows. A page for an older
// search is ignored. The first page replaces the list and later pages are
// added to it; a page shorter than the limit means there is nothing more.
export function mergeSuggestionPage(state, { key, offset, limit, items }) {
  if (offset > 0 && key !== state.key) return state;
  const page = Array.isArray(items) ? items : [];
  if (offset === 0) return { key, items: page, hasMore: page.length === limit };
  const seen = new Set(state.items.map((item) => item.account_id));
  return {
    key,
    items: [...state.items, ...page.filter((item) => !seen.has(item.account_id))],
    hasMore: page.length === limit,
  };
}

// The people list in the "+ Add student" and "Add collaborator" pop-ups.
// It lists everyone as soon as it opens, filters as you type (after a short
// pause), and loads the next page when loadMore() is called (on scroll).
//
// While a new search is loading, the previous results stay on screen, so the
// list doesn't blank out on every keystroke. `path` null turns it off.
// Raise `revision` to fetch the loaded results again after something changed
// what they say (someone added or removed).
export function useSuggestions(
  path,
  text,
  { revision = 0, delayMs = 250, pageSize = SUGGESTION_PAGE_SIZE } = {},
) {
  const api = useApi();
  const query = suggestionQuery(text);
  const key = path ? `${path}?${query}` : null;
  const [state, setState] = useState(EMPTY);
  const [loading, setLoading] = useState(false);
  const shown = useRef(EMPTY);
  const pending = useRef(null); // key of a loadMore in flight
  // What's on screen, for the effects and loadMore below (declared first, so
  // it's up to date when they run).
  useEffect(() => {
    shown.current = state;
  }, [state]);

  const fetchPage = useCallback(
    (offset, limit, signal) => {
      const params = new URLSearchParams({
        q: query,
        limit: String(limit),
        offset: String(offset),
      });
      return api(`${path}?${params}`, { signal });
    },
    [api, path, query],
  );

  // First page, whenever the search (or revision) changes. The first open
  // asks straight away; typing waits for a pause.
  useEffect(() => {
    if (!key) return undefined;
    const controller = new AbortController();
    const loaded = shown.current.key === key ? shown.current.items.length : 0;
    const limit = Math.max(pageSize, loaded);
    const timer = window.setTimeout(
      async () => {
        setLoading(true);
        try {
          const items = await fetchPage(0, limit, controller.signal);
          if (!controller.signal.aborted) {
            setState((current) =>
              mergeSuggestionPage(current, { key, offset: 0, limit, items }),
            );
          }
        } catch {
          // A failed search shows nothing; typing a full email still works.
          if (!controller.signal.aborted) {
            setState({ key, items: [], hasMore: false });
          }
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      },
      shown.current.key === null ? 0 : delayMs,
    );
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [key, revision, fetchPage, pageSize, delayMs]);

  const loadMore = useCallback(async () => {
    const current = shown.current;
    if (!key || current.key !== key || !current.hasMore || pending.current === key) {
      return;
    }
    pending.current = key;
    const offset = current.items.length;
    try {
      const items = await fetchPage(offset, pageSize);
      setState((latest) =>
        mergeSuggestionPage(latest, { key, offset, limit: pageSize, items }),
      );
    } catch {
      // Leave the list as it is; scrolling again retries.
    } finally {
      pending.current = null;
    }
  }, [key, fetchPage, pageSize]);

  return {
    items: key ? state.items : [],
    hasMore: key ? state.hasMore && state.key === key : false,
    // True until the first results for this search arrive.
    loading: Boolean(key) && (loading || state.key !== key),
    loadMore,
  };
}
