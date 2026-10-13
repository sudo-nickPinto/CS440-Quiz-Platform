import { useSyncExternalStore } from 'react'
import { createInitialState, reducer } from './model'

const KEY = 'quiz-platform-frontend-preview-v1'
const listeners = new Set()
let snapshot

function getSnapshot() {
  if (!snapshot) {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY))

      snapshot =
        saved?.version === 1 &&
        Array.isArray(saved.quizzes) &&
        Array.isArray(saved.sessions) &&
        saved.editor
          ? saved
          : createInitialState()
    } catch {
      snapshot = createInitialState()
    }
  }

  return snapshot
}

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function dispatch(action) {
  snapshot = reducer(getSnapshot(), action)

  try {
    localStorage.setItem(KEY, JSON.stringify(snapshot))
    snapshot = { ...snapshot, storageWarning: '' }
  } catch {
    snapshot = {
      ...snapshot,
      storageWarning:
        'Browser storage is unavailable. Changes will be lost when you reload.',
    }
  }

  listeners.forEach((listener) => listener())
}

export function usePreview() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}