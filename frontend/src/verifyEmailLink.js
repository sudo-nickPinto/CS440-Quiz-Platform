// Reads the Auth0 email-verification link that the verification email puts
// in the fragment of /verify-email (see docs/AUTH.md, "Email verification
// needs a click").

// Auth0's New Universal Login route that marks an email verified. Loading it
// with a valid ticket verifies the address, so the app only ever goes there
// from a button click.
export const VERIFICATION_PATH = '/u/email-verification'

// A fragment that starts with a percent-encoded scheme ("https%3A..."), which
// is what the template's url_encode filter produces.
const ENCODED_URL = /^[a-z][a-z0-9+.-]*%3a/i

// Returns the verification URL carried by `hash` (location.hash, i.e. the
// first "#" and everything after it), or null unless it is exactly an https
// link to our tenant's verification route with a ticket. This is the only
// address the page will send anyone to, so the page can't be used to
// redirect people elsewhere.
export function verificationTarget(hash, auth0Domain) {
  const domain = String(auth0Domain ?? '').trim().toLowerCase()
  let link = String(hash ?? '')
  if (link.startsWith('#')) link = link.slice(1)
  if (!link || !domain) return null

  // The email sends the link percent-encoded; a raw link is accepted too.
  if (ENCODED_URL.test(link)) {
    try {
      link = decodeURIComponent(link)
    } catch {
      return null
    }
  }

  let url
  try {
    url = new URL(link)
  } catch {
    return null
  }

  // The URL parser lowercases the host and drops a default :443.
  if (url.protocol !== 'https:') return null
  if (url.username || url.password || url.port) return null
  if (url.hostname !== domain) return null
  if (url.pathname !== VERIFICATION_PATH) return null
  if (!url.searchParams.get('ticket')?.trim()) return null

  return url.href
}
