// Menus and pop-ups built from <details> stay open until their summary is
// clicked again. This closes them the way the mockups' menus close: on a
// click outside, after picking an item inside, or on Escape.

const POPOVERS = [
  "details.qb-account",
  "details.ui-filter",
  "details.ui-row-menu",
  "details.qb-pop",
].join(",");

function closeAll(except) {
  document.querySelectorAll(POPOVERS).forEach((details) => {
    if (details.open && details !== except) details.open = false;
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("click", (event) => {
    const inside = event.target.closest?.(POPOVERS);
    closeAll(inside);

    // Picking a menu item (but not a filter option) closes its menu.
    // Items marked data-keep-open close themselves when they're done.
    const item = event.target.closest?.("a, button");
    if (
      inside &&
      item &&
      !item.closest("summary") &&
      !item.hasAttribute("data-keep-open") &&
      !inside.matches(".ui-filter")
    ) {
      inside.open = false;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;

    const open = [...document.querySelectorAll(POPOVERS)].find(
      (details) => details.open,
    );

    if (open) {
      open.open = false;
      open.querySelector("summary")?.focus();
    }
  });
}
