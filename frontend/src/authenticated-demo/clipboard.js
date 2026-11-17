// Copies text to the clipboard. Returns true when it worked.
//
// navigator.clipboard only works on HTTPS or localhost, so on other pages
// (for example a projector laptop opening the app by IP address) it falls
// back to selecting a hidden text box and using the copy command.
export async function copyToClipboard(text) {
  const value = String(text ?? "");
  if (!value) return false;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Fall through to the older method.
  }

  try {
    const box = document.createElement("textarea");
    box.value = value;
    box.setAttribute("readonly", "");
    box.style.position = "fixed";
    box.style.opacity = "0";
    document.body.appendChild(box);
    box.select();
    const copied = document.execCommand("copy");
    box.remove();
    return copied;
  } catch {
    return false;
  }
}
