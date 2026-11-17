import { useLayoutEffect, useRef } from 'react'

// Font sizes (px) the host screen can use, biggest first. Every question
// lands on one of these, so questions look alike from one to the next.
// The last step is the smallest size that still reads from the back of a
// classroom; the character limits keep text from needing anything smaller.
export const QUESTION_STEPS = [80, 72, 64, 56, 48, 42, 36, 32, 28]
export const PREVIEW_STEPS = [88, 76, 64, 56, 48, 42, 36, 32, 28]
export const ANSWER_STEPS = [34, 30, 27, 24, 22]

// The question stays about this many times the answers' size, so it is
// always the biggest thing on screen.
export const QUESTION_TO_ANSWER = 1.8

// Step both sizes down until nothing overflows. `apply(q, a)` sets the step
// indexes on the page; `measure()` then reports { question, answers }: true
// when that text still overflows its box. An overflowing question shrinks
// first. When the answers overflow, the answers shrink while they are more
// than 1/QUESTION_TO_ANSWER of the question's size, otherwise the question
// does, so the two come down together and keep their proportion. Either one
// keeps shrinking once the other has reached its smallest step. All four
// answers always share one size.
export function fitSteps({ questionSteps, answerSteps, apply, measure }) {
  const lastQ = questionSteps.length - 1
  const lastA = answerSteps.length - 1
  let q = 0
  let a = 0

  apply(q, a)
  for (;;) {
    const over = measure()
    if (!over.question && !over.answers) return { q, a, fits: true }

    let shrink = null
    if (over.question && q < lastQ) {
      shrink = 'question'
    } else if (over.answers) {
      const answersBig =
        answerSteps[a] * QUESTION_TO_ANSWER > questionSteps[q]
      if (a < lastA && (answersBig || q === lastQ)) shrink = 'answers'
      else if (q < lastQ) shrink = 'question'
      else if (a < lastA) shrink = 'answers'
    }
    if (!shrink) return { q, a, fits: false }

    if (shrink === 'question') q += 1
    else a += 1
    apply(q, a)
  }
}

// True when a box's content is taller than the space inside it. Compares the
// children's layout boxes (offsetTop/offsetHeight, which ignore animations'
// transforms) instead of scrollHeight, which also counts the bits of display
// letters that reach past their line (Archivo Black does) and would make even
// a two-word question look like it overflows. Boxes are position: relative so
// they are their children's offsetParent; SVG suits are skipped.
function overflows(element) {
  const style = getComputedStyle(element)
  const space =
    element.clientHeight -
    parseFloat(style.paddingTop) -
    parseFloat(style.paddingBottom)
  let top = Infinity
  let bottom = -Infinity
  for (const child of element.children) {
    if (!(child instanceof HTMLElement) || !child.offsetHeight) continue
    top = Math.min(top, child.offsetTop)
    bottom = Math.max(bottom, child.offsetTop + child.offsetHeight)
  }
  return bottom - top > space + 1
}

// Fits the host's question text and answers into their boxes. Mark the
// question's box with data-fit-question and each answer box with
// data-fit-answer inside the element that gets the returned ref. Sizes are
// written as --lv-q-size / --lv-a-size on that element, and data-fit says
// "ok", or "overflow" when even the smallest step does not fit. Runs before
// the screen is painted, again when fonts finish loading, and when the
// window changes size. Phones lay the page out as a normal scrolling page,
// so they keep the CSS sizes.
export function useFitText(key, questionSteps = QUESTION_STEPS) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return undefined
    const wide = window.matchMedia('(min-width: 641px)')

    function run() {
      if (!wide.matches) {
        root.style.removeProperty('--lv-q-size')
        root.style.removeProperty('--lv-a-size')
        delete root.dataset.fit
        return
      }
      const questionBox = root.querySelector('[data-fit-question]')
      const answerBoxes = [...root.querySelectorAll('[data-fit-answer]')]
      const answerSteps = answerBoxes.length ? ANSWER_STEPS : []
      const result = fitSteps({
        questionSteps,
        answerSteps,
        apply(q, a) {
          root.style.setProperty('--lv-q-size', `${questionSteps[q]}px`)
          if (answerSteps.length) {
            root.style.setProperty('--lv-a-size', `${answerSteps[a]}px`)
          }
        },
        measure: () => ({
          question: questionBox ? overflows(questionBox) : false,
          answers: answerBoxes.some(overflows),
        }),
      })
      root.dataset.fit = result.fits ? 'ok' : 'overflow'
    }

    run()

    let cancelled = false
    document.fonts?.ready.then(() => {
      if (!cancelled) run()
    })

    let width = root.clientWidth
    let height = root.clientHeight
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            if (root.clientWidth === width && root.clientHeight === height) return
            width = root.clientWidth
            height = root.clientHeight
            run()
          })
    observer?.observe(root)

    return () => {
      cancelled = true
      observer?.disconnect()
    }
  }, [key, questionSteps])

  return ref
}
