import { useEffect, useId, useRef, useState } from "react";

// A square dropdown in the site's style, for the class filter and the
// semester pickers. The browser's own <select> list can't be styled.
//
//   <SelectMenu label="Semester" value={value} onChange={setValue}
//               options={[{ value: "Fall 2026", label: "Fall 2026" }]} />
//
// The open list marks the current option. It opens to the left when it
// would run off the right edge of the window, and upward when there's no
// room below.
export default function SelectMenu({
  label,
  value,
  options,
  onChange,
  disabled = false,
  className = "",
}) {
  const ref = useRef(null);
  const listId = useId();
  const [place, setPlace] = useState({ right: false, up: false });
  const current = options.find((option) => option.value === value);

  useEffect(() => {
    function closeOutside(event) {
      const menu = ref.current;
      if (menu?.open && !menu.contains(event.target)) menu.open = false;
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  function close() {
    const menu = ref.current;
    if (!menu) return;
    menu.open = false;
    menu.querySelector("summary")?.focus();
  }

  function moveFocus(event) {
    const items = [...ref.current.querySelectorAll("[role=option]")];
    const index = items.indexOf(document.activeElement);
    if (event.key === "Escape" && ref.current.open) {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!ref.current.open) ref.current.open = true;
      const step = event.key === "ArrowDown" ? 1 : -1;
      const next =
        index === -1
          ? items.find((item) => item.getAttribute("aria-selected") === "true") ??
            items[0]
          : items[(index + step + items.length) % items.length];
      next?.focus();
    }
  }

  return (
    <details
      ref={ref}
      className={`cl-select ${className}`.trim()}
      onToggle={() => {
        const menu = ref.current;
        if (!menu?.open) return;
        const list = menu.querySelector(".cl-select-menu");
        const box = menu.getBoundingClientRect();
        setPlace({
          right: box.left + (list?.offsetWidth ?? 240) > window.innerWidth - 16,
          up:
            box.bottom + (list?.offsetHeight ?? 0) + 16 > window.innerHeight &&
            box.top > (list?.offsetHeight ?? 0) + 16,
        });
      }}
      onKeyDown={moveFocus}
    >
      <summary
        aria-label={`${label}: ${current?.label ?? "none"}`}
        aria-haspopup="listbox"
        aria-controls={listId}
        aria-disabled={disabled || undefined}
        onClick={(event) => {
          if (disabled) event.preventDefault();
        }}
      >
        {current?.label ?? "Choose…"}
      </summary>

      <div
        id={listId}
        className={
          "cl-select-menu" +
          (place.right ? " is-right" : "") +
          (place.up ? " is-up" : "")
        }
        role="listbox"
        aria-label={label}
      >
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={selected}
              onClick={() => {
                onChange(option.value);
                close();
              }}
            >
              <span aria-hidden="true">{selected ? "✓" : ""}</span>
              {option.label}
            </button>
          );
        })}
      </div>
    </details>
  );
}
