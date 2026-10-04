// Sample data from Taha's HTML mockup.
// Replace with backend responses during the integration step.

export const classes = [
  'CS 440 · Fall 26',
  'CS 216 · Data Structures',
  'CS 111 · Intro',
]

export const madeQuizzes = [
  {
    id: 'made-1',
    title: 'Quiz 1 — Big-O Warmup',
    status: 'draft',
    owner: 'owned',
    questions: 8,
    edited: '2026-09-26',
    className: '',
  },
  {
    id: 'made-2',
    title: 'Quiz 2 — Recursion Check',
    status: 'published',
    owner: 'owned',
    questions: 12,
    edited: '2026-09-22',
    className: 'CS 216 · Data Structures',
  },
  {
    id: 'made-3',
    title: 'Quiz 3 — SQL Joins',
    status: 'published',
    owner: 'shared',
    questions: 10,
    edited: '2026-09-18',
    className: 'CS 440 · Fall 26',
    sharedBy: 'N. Pinto',
  },
  {
    id: 'made-4',
    title: 'Sorting Speedrun',
    status: 'draft',
    owner: 'shared',
    questions: 6,
    edited: '2026-09-12',
    className: '',
    sharedBy: 'A. Majumder',
  },
]

export const takenQuizzes = [
  {
    id: 'taken-1',
    title: 'Git Basics Pop Quiz',
    host: 'Prof. Kim',
    date: '2026-09-25',
    correct: 9,
    total: 10,
    rank: 2,
    participants: 31,
  },
  {
    id: 'taken-2',
    title: 'HTTP & REST',
    host: 'Prof. Kim',
    date: '2026-09-18',
    correct: 6,
    total: 10,
    rank: 14,
    participants: 29,
  },
  {
    id: 'taken-3',
    title: 'Agile Vocab',
    host: 'U. Khairulla',
    date: '2026-09-10',
    correct: 7,
    total: 8,
    rank: 1,
    participants: 6,
  },
]