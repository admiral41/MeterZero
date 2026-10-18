const SEEN = 'meterzero.tourSeen'

/** The welcome tour shows once per browser. */
export function shouldShowTour() {
  try {
    return localStorage.getItem(SEEN) !== '1'
  } catch {
    return false
  }
}

export function markTourSeen() {
  try {
    localStorage.setItem(SEEN, '1')
  } catch {
    /* private mode: it shows again next time, which is fine */
  }
}

export function resetTour() {
  try {
    localStorage.removeItem(SEEN)
  } catch {
    /* fine */
  }
}
