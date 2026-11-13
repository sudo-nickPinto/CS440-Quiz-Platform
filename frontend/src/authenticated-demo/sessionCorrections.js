export function canCorrectSessionQuestion(report, question) {
  return Boolean(report?.can_correct && question?.session_question_id)
}

export function canSelectCorrectChoice({ editing, choice, currentChoices, busy }) {
  return Boolean(
    editing &&
      !busy &&
      choice &&
      (!choice.correct || currentChoices.length > 1),
  )
}

export function correctionModesForChoice(currentChoices, selectedChoice) {
  const alreadyCorrect = currentChoices.some(
    (choice) => choice.id === selectedChoice?.id,
  )
  return alreadyCorrect ? ['REMOVE'] : ['REPLACE', 'ADD']
}

export function correctionRequest(choiceId, mode, scoreRevision) {
  return {
    choice_id: Number(choiceId),
    mode,
    expected_score_revision: scoreRevision,
  }
}
