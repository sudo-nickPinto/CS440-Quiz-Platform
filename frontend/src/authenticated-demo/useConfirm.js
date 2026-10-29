import { useCallback, useEffect, useRef, useState } from "react";

// Styled replacement for window.confirm(). Resolves true or false exactly
// like window.confirm, so callers keep their existing logic:
//
//   const confirmer = useConfirm();
//   if (await confirmer.confirm({ title: "Archive quiz?" })) …
//   return <><ConfirmDialog confirmer={confirmer} />…</>;
export function useConfirm() {
  const [request, setRequest] = useState(null);
  const resolver = useRef(null);

  const confirm = useCallback(
    (options) =>
      new Promise((resolve) => {
        resolver.current?.(false);
        resolver.current = resolve;
        setRequest(options);
      }),
    [],
  );

  const settle = useCallback((answer) => {
    resolver.current?.(answer);
    resolver.current = null;
    setRequest(null);
  }, []);

  useEffect(() => () => resolver.current?.(false), []);

  return { request, confirm, settle };
}
