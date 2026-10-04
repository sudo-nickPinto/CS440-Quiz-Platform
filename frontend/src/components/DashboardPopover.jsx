import { useEffect, useId, useRef, useState } from "react";

export default function DashboardPopover({ label, accessibleLabel, children }) {
  const id = useId();
  const trigger = useRef(null);
  const panel = useRef(null);
  const [position, setPosition] = useState(null);
  const [focusRequest, setFocusRequest] = useState(0);

  const open = position !== null;

  function close(restoreFocus = false) {
    setPosition(null);

    if (restoreFocus) {
      setFocusRequest((request) => request + 1);
    }
  }

  useEffect(() => {
    if (focusRequest > 0) {
      trigger.current?.focus();
    }
  }, [focusRequest]);

  function toggle() {
    if (open) {
      close();
      return;
    }

    const rect = trigger.current.getBoundingClientRect();

    setPosition({
      left: Math.max(12, Math.min(rect.right - 280, window.innerWidth - 292)),
      top: Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 372)),
    });
  }

  useEffect(() => {
    if (!open) return;

    panel.current?.querySelector("button")?.focus();

    function handlePointer(event) {
      if (
        !panel.current?.contains(event.target) &&
        !trigger.current?.contains(event.target)
      ) {
        setPosition(null);
      }
    }

    function handleKey(event) {
      if (event.key === "Escape") {
        setPosition(null);
        trigger.current?.focus();
      }
    }

    function handleScroll(event) {
      if (!panel.current?.contains(event.target)) {
        setPosition(null);
      }
    }

    function handleResize() {
      setPosition(null);
    }

    document.addEventListener("pointerdown", handlePointer);
    document.addEventListener("keydown", handleKey);
    document.addEventListener("scroll", handleScroll, true);
    window.addEventListener("resize", handleResize);

    return () => {
      document.removeEventListener("pointerdown", handlePointer);
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("scroll", handleScroll, true);
      window.removeEventListener("resize", handleResize);
    };
  }, [open]);

  return (
    <div className="db-popover-wrap">
      <button
        ref={trigger}
        className="db-control"
        type="button"
        aria-label={accessibleLabel}
        aria-expanded={open}
        aria-controls={id}
        onClick={toggle}
      >
        {label}
      </button>

      {open && (
        <div
          id={id}
          ref={panel}
          className="db-popover"
          style={position}
          role="group"
          aria-label={accessibleLabel || label}
        >
          {children(close)}
        </div>
      )}
    </div>
  );
}
