import { useAuth0 } from "@auth0/auth0-react";
import { useAction } from "./rest";
import { pickTokenGetter } from "../guest/guestSession";

/*
 * Downloads a file from an authenticated API route, such as a CSV or
 * Excel export. The server's Content-Disposition filename is used when
 * it sends one; otherwise fallbackName.
 *
 * options: { method, body } for a POST export (body is sent as JSON), and
 * { filename } to name the file yourself whatever the server says.
 */
export function useFileDownload() {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0();
  const action = useAction();

  async function download(path, fallbackName, options = {}) {
    const { method = "GET", body, filename } = options;
    const result = await action.run(async () => {
      const token = await pickTokenGetter(
        isAuthenticated,
        getAccessTokenSilently,
      )();
      const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "");
      const headers = { Authorization: "Bearer " + token };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      const response = await fetch(base + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
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
      return { blob: await response.blob(), name: filename || name || fallbackName };
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
