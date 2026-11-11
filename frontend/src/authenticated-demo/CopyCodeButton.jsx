import { useEffect, useRef, useState } from "react";

import { copyToClipboard } from "./clipboard";

import "./copy-code.css";

// A small "Copy" button next to a join code. It copies the code exactly as
// the join form expects it (no spaces), then says "Copied" for a moment.
export default function CopyCodeButton({ code, label = "code", className = "" }) {
  const [status, setStatus] = useState("idle");
  const timer = useRef(null);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  if (!code) return null;

  async function copy() {
    const copied = await copyToClipboard(code);
    setStatus(copied ? "copied" : "failed");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setStatus("idle"), 1600);
  }

  const text =
    status === "copied" ? "Copied!" : status === "failed" ? "Copy failed" : "Copy";

  // The status text sits outside the button so screen readers announce it;
  // text inside a button with an aria-label is not read out.
  return (
    <>
      <button
        type="button"
        className={`ui-copy-code ${className}`.trim()}
        onClick={() => void copy()}
        aria-label={`Copy ${label} ${code}`}
      >
        <span aria-hidden="true">⧉</span> {text}
      </button>
      <span className="ui-copy-status" role="status">
        {status === "copied"
          ? `${label} copied`
          : status === "failed"
            ? `Couldn't copy the ${label}`
            : ""}
      </span>
    </>
  );
}
