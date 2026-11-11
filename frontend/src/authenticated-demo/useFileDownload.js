import { useAuth0 } from "@auth0/auth0-react";
import { useAction } from "./rest";

/*
 * Downloads a file from an authenticated API route, such as a CSV or
 * Excel export. The server's Content-Disposition filename is used when
 * it sends one; otherwise fallbackName.
 */
export function useFileDownload() {
  const { getAccessTokenSilently } = useAuth0();
  const action = useAction();

  async function download(path, fallbackName) {
    const result = await action.run(async () => {
      const token = await getAccessTokenSilently();
      const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "");
      const response = await fetch(base + path, {
        headers: { Authorization: "Bearer " + token },
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const error = new Error(body?.error?.message || "Export failed.");
        error.status = response.status;
        error.code = body?.error?.code;
        throw error;
      }

      const name = /filename="([^"]+)"/.exec(
        response.headers.get("Content-Disposition") || "",
      )?.[1];
      return { blob: await response.blob(), name: name || fallbackName };
    });

    if (!result) return;

    const url = URL.createObjectURL(result.blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = result.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return { download, busy: action.busy, error: action.error };
}
