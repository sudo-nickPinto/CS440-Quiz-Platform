// End-to-end: one class from first sign-in to the grade export, through the
// real HTTP API and sockets (backend/tests/e2e_server.py stands in for Auth0).
//
//   npm run test:e2e
//
// The steps share state and run in order:
//   1. accounts    prof and ta become faculty; ana, ben, cy, dee are students;
//                  zed signs in but never joins the class
//   2. class       code joins, closed joining, code rotation, a TA, an invite
//   3. quiz A      prof edits with revisions, publishes, submits, approves
//   4. quiz B      ana writes one with ben as a live co-editor; prof approves
//   5. session 1   prof hosts A: countdown, 4 questions, every close reason,
//                  reconnects, a mid-question joiner
//   6. session 2   ana hosts B for ben and cy
//   7. session 3   ta hosts A and cancels it in the lobby
//   8. results     final results, reports, CSV export, history
//   9. reports     class dashboard, tabs, drill-downs, Excel and grade exports
//  10. archive     what still works once the class is archived

import { describe, expect, it } from 'vitest'
import { readCsv, readXlsx } from './files.js'
import { call, connect, phase, refused, rest, runE2EServer, server, until } from './harness.js'

runE2EServer()

const STUDENTS = ['ana', 'ben', 'cy', 'dee']
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

const me = {} // person -> GET /me body
let course // prof's ClassResponse
let base // /classes/{class_id}
let quizA // published QuizResponse
let quizB
const sessions = {} // s1, s2, s3 -> SessionResponse
const finals = {} // s1, s2 -> host's final standings

// One multiple-choice question; `right` is the correct choice's text.
function question(text, choices, right, extra = {}) {
  return {
    question_text: text,
    time_limit_seconds: 20,
    base_points: 1000,
    ...extra,
    choices: choices.map((choice) => ({ choice_text: choice, is_correct: choice === right })),
  }
}

// A question as the editor sends it back on save.
function editable(saved, changes = {}) {
  return {
    question_text: saved.question_text,
    explanation: saved.explanation,
    time_limit_seconds: saved.time_limit_seconds,
    base_points: saved.base_points,
    choices: saved.choices.map(({ choice_text, is_correct }) => ({ choice_text, is_correct })),
    ...changes,
  }
}

// The choice_id with this text in the open question.
function pick(live, text) {
  const choice = live.getState().currentQuestion.choices.find((c) => c.choice_text === text)
  if (!choice) throw new Error(`No choice ${text} in ${JSON.stringify(live.getState().currentQuestion)}`)
  return choice.choice_id
}

const opened = (order) => (s) => s.currentQuestion?.question_order === order
// Results for question `order` have arrived (closed + question_results).
const resultsFor = (order) => (s) =>
  s.lastQuestion?.question_order === order &&
  s.lastClosed !== null &&
  s.lastResults?.session_question_id === s.lastQuestion.session_question_id

const ranking = (standings) => standings.map((r) => [r.display_name, r.correct_count, r.final_rank])

// The quiz editor socket (/ws/quizzes/{id}), recording what it receives.
function editorSocket(person, quizId) {
  const ws = new WebSocket(`${server.baseUrl.replace(/^http/, 'ws')}/ws/quizzes/${quizId}`)
  const seen = { messages: [], closed: null }
  const checks = new Set()
  const notify = () => checks.forEach((check) => check())
  ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: server.tokens[person] }))
  ws.onmessage = (event) => {
    seen.messages.push(JSON.parse(event.data))
    notify()
  }
  ws.onclose = (event) => {
    seen.closed = { code: event.code, reason: event.reason }
    notify()
  }
  const waitFor = (predicate, label) =>
    new Promise((resolve, reject) => {
      const check = () => {
        const value = predicate(seen)
        if (!value) return
        checks.delete(check)
        clearTimeout(timer)
        resolve(value)
      }
      const timer = setTimeout(() => {
        checks.delete(check)
        reject(new Error(`Timed out waiting for ${label}: ${JSON.stringify(seen)}`))
      }, 5000)
      checks.add(check)
      check()
    })
  const message = (type) => waitFor((s) => s.messages.find((m) => m.type === type), type)
  return { waitFor, message, close: () => ws.close() }
}

describe('full flow: one class from sign-in to grade export', () => {
  it('signs everyone in and makes prof and ta faculty', async () => {
    expect(await rest(null, 'GET', '/health')).toEqual({
      status: 'ok',
      components: { database: 'ok' },
    })
    expect(await refused(null, 'GET', '/me')).toMatchObject({ status: 401, code: 'missing_token' })
    const forged = await fetch(`${server.baseUrl}/me`, { headers: { Authorization: 'Bearer nope' } })
    expect(forged.status).toBe(401)
    expect((await forged.json()).error.code).toBe('invalid_token')

    // The first GET /me creates the account from the Auth0 profile.
    for (const person of ['prof', 'ta', ...STUDENTS, 'zed']) {
      me[person] = await rest(person, 'GET', '/me')
      expect(me[person]).toMatchObject({
        email: `${person}@e2e.invalid`,
        display_name: person[0].toUpperCase() + person.slice(1),
        is_active: true,
      })
    }
    expect((await rest('ana', 'GET', '/me')).account_id).toBe(me.ana.account_id)
    for (const person of [...STUDENTS, 'zed']) expect(me[person].role).toBe('USER')

    expect(await refused('ana', 'POST', '/classes', { name: 'Nope' })).toMatchObject({
      status: 403,
      code: 'faculty_required',
    })
    for (const person of ['prof', 'ta']) {
      await rest(person, 'POST', `/e2e/faculty/${person}`)
      expect((await rest(person, 'GET', '/me')).role).toBe('ADMIN')
    }
  })

  it('builds the class: joins by code, closed joining, rotation, a TA and an invite', async () => {
    course = await rest('prof', 'POST', '/classes', { name: '  Full Flow 101  ' })
    expect(course).toMatchObject({
      name: 'Full Flow 101',
      created_by_id: me.prof.account_id,
      joining_open: true,
      archived_at: null,
      current_role: 'ORGANIZER',
      membership_status: 'ACTIVE',
    })
    expect(course.join_code).toMatch(/^[A-Z2-9]{4}-[A-Z2-9]{4}$/)
    base = `/classes/${course.class_id}`

    // Codes are forgiving about case and the dash; members never see them.
    const joined = await rest('ana', 'POST', '/classes/join', {
      code: course.join_code.replace('-', '').toLowerCase(),
    })
    expect(joined).toMatchObject({ class_id: course.class_id, current_role: 'MEMBER', join_code: null })
    for (const person of ['ben', 'cy']) {
      await rest(person, 'POST', '/classes/join', { code: course.join_code })
    }
    expect(await refused('ben', 'POST', '/classes/join', { code: course.join_code })).toMatchObject({
      status: 409,
      code: 'already_class_member',
    })
    expect(await refused('cy', 'POST', '/classes/join', { code: 'ZZZZ-2222' })).toMatchObject({
      status: 404,
      code: 'class_code_not_found',
    })
    expect((await rest('ana', 'GET', '/classes')).map((c) => c.class_id)).toContain(course.class_id)

    // Closing joining stops new members; rotating the code reopens it.
    await rest('prof', 'PATCH', base, { joining_open: false })
    expect(await refused('zed', 'POST', '/classes/join', { code: course.join_code })).toMatchObject({
      status: 403,
      code: 'class_joining_closed',
    })
    const oldCode = course.join_code
    course = await rest('prof', 'POST', `${base}/code`)
    expect(course.join_code).not.toBe(oldCode)
    expect(course.joining_open).toBe(true)
    expect(await refused('zed', 'POST', '/classes/join', { code: oldCode })).toMatchObject({
      status: 404,
      code: 'class_code_not_found',
    })

    // ta joins as a member and is promoted; a student can't be.
    await rest('ta', 'POST', '/classes/join', { code: course.join_code })
    expect(
      await rest('prof', 'PATCH', `${base}/members/${me.ta.account_id}`, { role: 'ORGANIZER' }),
    ).toMatchObject({ role: 'ORGANIZER', status: 'ACTIVE' })
    expect(
      await refused('prof', 'PATCH', `${base}/members/${me.ben.account_id}`, { role: 'ORGANIZER' }),
    ).toMatchObject({ status: 409, code: 'organizer_requires_faculty' })
    expect(await refused('ana', 'GET', `${base}/members`)).toMatchObject({
      status: 403,
      code: 'not_class_organizer',
    })

    // dee comes in by invite instead of the code.
    expect(await rest('prof', 'POST', `${base}/invites`, { email: 'DEE@e2e.invalid ' })).toMatchObject({
      account_id: me.dee.account_id,
      status: 'INVITED',
    })
    expect(await rest('dee', 'POST', `${base}/invite/accept`)).toMatchObject({
      status: 'ACTIVE',
      role: 'MEMBER',
    })

    const members = await rest('prof', 'GET', `${base}/members`)
    expect(members.map((m) => [m.display_name, m.role])).toEqual([
      ['Ana', 'MEMBER'],
      ['Ben', 'MEMBER'],
      ['Cy', 'MEMBER'],
      ['Dee', 'MEMBER'],
      ['Prof', 'ORGANIZER'],
      ['Ta', 'ORGANIZER'],
    ])
  })

  it('edits quiz A with revision checks, then publishes, submits and approves it', async () => {
    const draft = await rest('prof', 'POST', `${base}/quizzes`, {
      title: 'World Capitals',
      description: '  Four capitals  ',
      questions: [
        question('Capital of France?', ['Rome', 'Paris'], 'Paris'),
        question('Capital of Japn?', ['Kyoto', 'Tokyo', 'Osaka'], 'Tokyo'),
      ],
    })
    expect(draft).toMatchObject({ status: 'DRAFT', can_edit: true, class_id: course.class_id })
    expect(draft.version).toMatchObject({ description: 'Four capitals', published_at: null })
    const quizPath = `${base}/quizzes/${draft.quiz_id}`

    // Fix the typo in Q2, then a second save from the old copy conflicts.
    const typo = draft.version.questions[1]
    const fixed = await rest('prof', 'PATCH', `${quizPath}/questions/${typo.question_id}`, {
      ...editable(typo, { question_text: 'Capital of Japan?' }),
      expected_revision: typo.revision,
    })
    expect(fixed.question.question_text).toBe('Capital of Japan?')
    expect(fixed.quiz_revision).toBeGreaterThan(draft.revision)
    expect(
      await refused('prof', 'PATCH', `${quizPath}/questions/${typo.question_id}`, {
        ...editable(typo),
        expected_revision: typo.revision,
      }),
    ).toMatchObject({
      status: 409,
      code: 'question_edit_conflict',
      details: { current_revision: fixed.question.revision },
    })

    await rest('prof', 'POST', `${quizPath}/questions`, question('Capital of Canada?', ['Toronto', 'Ottawa'], 'Ottawa'))
    const added = await rest(
      'prof',
      'POST',
      `${quizPath}/questions`,
      question('Capital of Australia?', ['Sydney', 'Canberra'], 'Canberra', {
        time_limit_seconds: 2,
        base_points: 500,
      }),
    )
    expect(added.question.question_order).toBe(4)
    const revision = added.quiz_revision

    for (const [method, path] of [
      ['PUT', quizPath],
      ['POST', `${quizPath}/publish`],
    ]) {
      const body = method === 'PUT' ? { title: 'Stale', questions: [question('?', ['a', 'b'], 'a')] } : {}
      expect(await refused('prof', method, path, { ...body, expected_revision: draft.revision })).toMatchObject({
        status: 409,
        code: 'quiz_edit_conflict',
        details: { current_revision: revision },
      })
    }

    // Students can't see someone else's quiz; organizers can read but not edit.
    expect(await refused('ana', 'GET', quizPath)).toMatchObject({ status: 404, code: 'quiz_not_found' })
    expect((await rest('ta', 'GET', quizPath)).can_edit).toBe(false)

    // A draft can't be hosted; a published one needs approval first.
    expect(await refused('prof', 'POST', `${quizPath}/sessions`)).toMatchObject({
      status: 409,
      code: 'quiz_not_hostable',
    })
    quizA = await rest('prof', 'POST', `${quizPath}/publish`, { expected_revision: revision })
    expect(quizA.status).toBe('PUBLISHED')
    expect(quizA.version.published_at).not.toBeNull()
    expect(quizA.version.questions.map((q) => [q.question_text, q.time_limit_seconds, q.base_points])).toEqual([
      ['Capital of France?', 20, 1000],
      ['Capital of Japan?', 20, 1000],
      ['Capital of Canada?', 20, 1000],
      ['Capital of Australia?', 2, 500],
    ])
    expect(await refused('prof', 'POST', `${quizPath}/sessions`)).toMatchObject({
      status: 409,
      code: 'quiz_version_not_approved',
    })

    const submission = await rest('prof', 'POST', `${base}/quiz-submissions`, {
      quiz_version_id: quizA.version.quiz_version_id,
    })
    expect(submission.status).toBe('PENDING')
    expect(
      await rest('prof', 'PATCH', `${base}/quiz-submissions/${submission.submission_id}`, { status: 'APPROVED' }),
    ).toMatchObject({ status: 'APPROVED', decided_by_id: me.prof.account_id })

    const approved = await rest('ana', 'GET', `${base}/approved-quizzes`)
    expect(approved.map((q) => [q.quiz_id, q.title])).toEqual([[quizA.quiz_id, 'World Capitals']])
  })

  it('co-edits quiz B live with a collaborator before it is approved', async () => {
    const draft = await rest('ana', 'POST', `${base}/quizzes`, {
      title: '=2+2 warm-up',
      questions: [
        question('2 + 2 = ?', ['4', '5'], '4'),
        question('Largest planet?', ['Mars', 'Jupiter'], 'Jupiter'),
      ],
    })
    const quizPath = `${base}/quizzes/${draft.quiz_id}`

    // Collaborators must be class members, and not the owner.
    for (const [email, code] of [
      ['zed@e2e.invalid', 'not_class_member'],
      ['ana@e2e.invalid', 'quiz_owner_cannot_collaborate'],
    ]) {
      expect(await refused('ana', 'POST', `${quizPath}/collaborators`, { email })).toMatchObject({ status: 409, code })
    }
    expect(await rest('ana', 'POST', `${quizPath}/collaborators`, { email: 'ben@e2e.invalid' })).toMatchObject({
      account_id: me.ben.account_id,
      permission: 'EDITOR',
    })

    const benEditor = editorSocket('ben', draft.quiz_id)
    await benEditor.message('quiz_editor_state')
    const cyEditor = editorSocket('cy', draft.quiz_id)
    expect(await cyEditor.waitFor((s) => s.closed, 'cy refused')).toEqual({ code: 4404, reason: 'quiz_not_found' })

    // ana adds a choice; ben's editor hears about it.
    const planet = draft.version.questions[1]
    const patched = await rest('ana', 'PATCH', `${quizPath}/questions/${planet.question_id}`, {
      ...editable(planet, {
        choices: [...editable(planet).choices, { choice_text: 'Saturn', is_correct: false }],
      }),
      expected_revision: planet.revision,
    })
    const update = await benEditor.message('question_updated')
    expect(update).toMatchObject({ quiz_revision: patched.quiz_revision, editor_account_id: me.ana.account_id })
    expect(update.question.choices.map((c) => c.choice_text)).toEqual(['Mars', 'Jupiter', 'Saturn'])

    // ben saves the whole quiz, but only the owner can publish.
    const current = await rest('ben', 'GET', quizPath)
    expect(current.can_edit).toBe(true)
    const saved = await rest('ben', 'PUT', quizPath, {
      title: current.version.title,
      description: 'Edited by Ben',
      questions: [
        question('2 + 2 = ?', ['3', '4'], '4'),
        editable(current.version.questions[1]),
      ],
      expected_revision: current.revision,
    })
    expect(await benEditor.message('quiz_structure_updated')).toMatchObject({
      quiz_revision: saved.revision,
      editor_account_id: me.ben.account_id,
    })
    expect(await refused('ben', 'POST', `${quizPath}/publish`, { expected_revision: saved.revision })).toMatchObject({
      status: 403,
      code: 'quiz_publish_denied',
    })
    quizB = await rest('ana', 'POST', `${quizPath}/publish`, { expected_revision: saved.revision })
    expect(await benEditor.message('quiz_published')).toMatchObject({ editor_account_id: me.ana.account_id })
    expect(quizB.version).toMatchObject({ title: '=2+2 warm-up', description: 'Edited by Ben' })

    // ben can submit it; only an organizer can approve it. Members only see
    // their own submissions, so to ana it doesn't exist.
    const submission = await rest('ben', 'POST', `${base}/quiz-submissions`, {
      quiz_version_id: quizB.version.quiz_version_id,
    })
    const decide = `${base}/quiz-submissions/${submission.submission_id}`
    expect(await refused('ben', 'PATCH', decide, { status: 'APPROVED' })).toMatchObject({
      status: 403,
      code: 'not_class_organizer',
    })
    expect(await refused('ana', 'PATCH', decide, { status: 'APPROVED' })).toMatchObject({
      status: 404,
      code: 'submission_not_found',
    })
    // The dashboard's queue (Task 6) names the submitter and version for
    // organizers, and shows ben his own pending submission.
    const queue = await rest('prof', 'GET', `${base}/dashboard/submissions?status=PENDING`)
    expect(queue.items).toEqual([
      expect.objectContaining({
        submission_id: submission.submission_id,
        quiz_title: '=2+2 warm-up',
        submitter_name: expect.any(String),
        submitted_by_id: me.ben.account_id,
        is_current_version: true,
      }),
    ])
    const bens = await rest('ben', 'GET', `${base}/dashboard/submissions`)
    expect(bens.items.map((item) => [item.submission_id, item.status])).toEqual([
      [submission.submission_id, 'PENDING'],
    ])
    expect((await rest('prof', 'GET', `${base}/dashboard`)).pending_submission_count).toBe(1)

    await rest('prof', 'PATCH', `${base}/quiz-submissions/${submission.submission_id}`, { status: 'APPROVED' })
    const hostable = async (person) =>
      (await rest(person, 'GET', `${base}/dashboard/approved-quizzes?sort=title&order=asc`)).items
        .filter((item) => item.quiz_id === quizB.quiz_id)
        .map((item) => item.can_host)
    expect(await hostable('ana')).toEqual([true])
    expect(await hostable('ben')).toEqual([false])
    expect(await hostable('prof')).toEqual([true])
    expect(await refused('ben', 'POST', `${quizPath}/sessions`)).toMatchObject({
      status: 403,
      code: 'session_host_denied',
    })

    // Revoking ben closes his editor and hides the quiz from him again.
    await rest('ana', 'DELETE', `${quizPath}/collaborators/${me.ben.account_id}`)
    expect(await benEditor.waitFor((s) => s.closed, 'ben revoked')).toEqual({ code: 4403, reason: 'quiz_edit_denied' })
    expect(await refused('ben', 'GET', quizPath)).toMatchObject({ status: 404, code: 'quiz_not_found' })
  })

  it('runs session 1: countdown, every close reason, reconnects and a late joiner', async () => {
    const s1 = await rest('prof', 'POST', `${base}/quizzes/${quizA.quiz_id}/sessions`)
    sessions.s1 = s1
    expect(s1).toMatchObject({ status: 'LOBBY', class_id: course.class_id, quiz_title: 'World Capitals' })
    expect(s1.join_code).toMatch(/^\d{6}$/)
    const sid = s1.session_id

    let host = connect('prof', sid)
    await until(host, phase('lobby'), 'host lobby')
    expect(host.getState().session.join_code).toBe(s1.join_code)

    const [listed] = await rest('ana', 'GET', `${base}/active-sessions`)
    expect(listed).toMatchObject({ session_id: sid, is_host: false, joined: false, left: false, question_count: 4 })

    // Only class members can play, and the host can't.
    expect(await refused('zed', 'POST', '/sessions/join', { join_code: s1.join_code })).toMatchObject({
      status: 403,
      code: 'not_class_member',
    })
    expect(await refused('zed', 'POST', `/sessions/${sid}/join`)).toMatchObject({ status: 404, code: 'session_not_found' })
    expect(await refused('prof', 'POST', '/sessions/join', { join_code: s1.join_code })).toMatchObject({
      status: 409,
      code: 'host_cannot_join',
    })

    await rest('ana', 'POST', '/sessions/join', { join_code: ` ${s1.join_code} ` })
    await rest('ben', 'POST', '/sessions/join', { join_code: s1.join_code })
    await rest('cy', 'POST', `/sessions/${sid}/join`) // the class page's Live button
    expect(await refused('ana', 'POST', `/sessions/${sid}/join`)).toMatchObject({
      status: 409,
      code: 'session_already_joined',
    })
    await until(host, (s) => s.participants.length === 3, 'three joins')
    expect(host.getState().participants.map((p) => p.display_name).sort()).toEqual(['Ana', 'Ben', 'Cy'])
    expect((await rest('ana', 'GET', `${base}/active-sessions`))[0].joined).toBe(true)

    let ana = connect('ana', sid)
    const ben = connect('ben', sid)
    const cy = connect('cy', sid)
    for (const live of [ana, ben, cy]) {
      const state = await until(live, phase('lobby'), 'participant lobby')
      expect(state.role).toBe('participant')
      expect(state.session.join_code).toBeUndefined()
    }
    const outsider = connect('zed', sid)
    await until(outsider, (s) => s.connection === 'forbidden', 'zed refused')

    // Q1 after the 3-2-1 countdown. Ana and Ben are right, Cy is wrong.
    await host.startCountdown()
    await until(ana, (s) => s.countdown !== null, 'countdown tick')
    await Promise.all([host, ana, ben, cy].map((live) => until(live, opened(1), 'Q1 open')))
    await ana.submitAnswer(pick(ana, 'Paris'))
    await expect(ana.submitAnswer(pick(ana, 'Rome'))).rejects.toMatchObject({ code: 'response_already_submitted' })
    await expect(ben.end()).rejects.toMatchObject({ code: 'session_host_denied' })
    await ben.submitAnswer(pick(ben, 'Paris'))
    await cy.submitAnswer(pick(cy, 'Rome'))
    for (const live of [host, ana, ben, cy]) {
      const state = await until(live, resultsFor(1), 'Q1 results')
      expect(state.lastClosed).toMatchObject({ reason: 'ALL_ANSWERED', answered_count: 3, eligible_count: 3 })
    }
    expect(host.getState().lastResults.participants).toHaveLength(3)
    expect(ana.getState().lastResults.me).toMatchObject({ is_correct: true, rank: 1 })
    expect(ana.getState().lastResults.me.points_awarded).toBeGreaterThan(900)
    expect(cy.getState().lastResults.me).toMatchObject({ is_correct: false, points_awarded: 0, rank: 3 })

    // Q2: Ana answers over REST, Ben is wrong, Cy never answers.
    await host.openNextQuestion()
    await Promise.all([ana, ben, cy].map((live) => until(live, opened(2), 'Q2 open')))
    const q2 = ana.getState().currentQuestion
    const tokyo = pick(ana, 'Tokyo')
    const answerPath = `/sessions/${sid}/questions/${q2.session_question_id}/responses`
    expect(await rest('ana', 'POST', answerPath, { choice_id: tokyo })).toMatchObject({
      session_question_id: q2.session_question_id,
      choice_id: tokyo,
    })
    expect(await refused('ana', 'POST', answerPath, { choice_id: tokyo })).toMatchObject({
      status: 409,
      code: 'response_already_submitted',
    })
    await ben.submitAnswer(pick(ben, 'Kyoto'))
    await until(host, (s) => s.answerProgress?.answered_count === 2, 'Q2 two answers')
    expect(host.getState().answerProgress.eligible_count).toBe(3)

    // A participant reload restores their answer; a host reload is announced.
    ana.close()
    ana = connect('ana', sid)
    expect((await until(ana, opened(2), 'ana back in Q2')).myAnswer.choice_id).toBe(tokyo)
    host.close()
    await until(ben, (s) => !s.hostConnected, 'host gone')
    host = connect('prof', sid)
    await until(host, opened(2), 'host back in Q2')
    await until(ben, (s) => s.hostConnected, 'host back')

    // dee joins mid-question: they start with the next question, so they
    // can't answer Q2 and Q2's roster stays at 3. (The wait is over a second
    // because SQLite stores joined_at to whole seconds.)
    await new Promise((resolve) => setTimeout(resolve, 1_100))
    await rest('dee', 'POST', `/sessions/${sid}/join`)
    await until(host, (s) => s.participantCount === 4, 'dee joined')
    expect(await refused('dee', 'POST', answerPath, { choice_id: tokyo })).toMatchObject({
      status: 409,
      code: 'joined_after_question_opened',
    })

    await host.skip()
    for (const live of [host, ana, ben, cy]) {
      const state = await until(live, resultsFor(2), 'Q2 results')
      // dee isn't on Q2's roster: still 3 eligible.
      expect(state.lastClosed).toMatchObject({ reason: 'HOST', answered_count: 2, eligible_count: 3 })
    }
    expect(cy.getState().lastResults.me).toMatchObject({ selected_choice_id: null, points_awarded: 0 })
    expect(ana.getState().lastResults.me.is_correct).toBe(true)

    // dee, who joined during Q2, connects between questions and plays from Q3 on.
    const dee = connect('dee', sid)
    await until(dee, (s) => s.session?.status === 'ACTIVE', 'dee connected')
    expect(dee.getState().currentQuestion).toBeNull()

    // Q3: everyone answers, so it closes by itself.
    await host.openNextQuestion()
    await Promise.all([ana, ben, cy, dee].map((live) => until(live, opened(3), 'Q3 open')))
    await ana.submitAnswer(pick(ana, 'Ottawa'))
    await until(host, (s) => s.answerProgress?.answered_count === 1, 'Q3 first answer')
    expect(host.getState().answerProgress.eligible_count).toBe(4)
    await ben.submitAnswer(pick(ben, 'Ottawa'))
    await cy.submitAnswer(pick(cy, 'Ottawa'))
    await dee.submitAnswer(pick(dee, 'Toronto'))
    for (const live of [host, ana, ben, cy, dee]) {
      const state = await until(live, resultsFor(3), 'Q3 results')
      expect(state.lastClosed).toMatchObject({ reason: 'ALL_ANSWERED', answered_count: 4, eligible_count: 4 })
    }

    // Q4 (2 seconds): only Dee answers, so the deadline closes it.
    await host.openNextQuestion()
    await until(dee, opened(4), 'dee Q4')
    await dee.submitAnswer(pick(dee, 'Canberra'))
    for (const live of [host, dee, ana]) {
      const state = await until(live, resultsFor(4), 'Q4 deadline', 10_000)
      expect(state.lastClosed).toMatchObject({ reason: 'DEADLINE', answered_count: 1, eligible_count: 4 })
    }
    expect(dee.getState().lastResults.me).toMatchObject({ is_correct: true, rank: 4 })
    expect(dee.getState().lastResults.me.points_awarded).toBeGreaterThan(0)
    expect(dee.getState().lastResults.me.points_awarded).toBeLessThanOrEqual(500)

    await host.end()
    const ended = await Promise.all(
      [host, ana, ben, cy, dee].map((live) => until(live, (s) => s.final && s.connection === 'ended', 'S1 ended')),
    )
    for (const state of ended) expect(state.final.reason).toBe('COMPLETED')
    const [hostFinal, , , , deeFinal] = ended
    expect(ranking(hostFinal.final.standings)).toEqual([
      ['Ana', 3, 1],
      ['Ben', 2, 2],
      ['Cy', 1, 3],
      ['Dee', 1, 4],
    ])
    expect(deeFinal.final.me).toMatchObject({ display_name: 'Dee', final_rank: 4 })
    expect(deeFinal.final.leaderboard.map((r) => r.display_name)).toEqual(['Ana', 'Ben', 'Cy', 'Dee'])
    finals.s1 = hostFinal.final.standings
  }, 60_000)

  it('runs session 2: ana hosts her quiz for ben and cy', async () => {
    const s2 = await rest('ana', 'POST', `${base}/quizzes/${quizB.quiz_id}/sessions`)
    sessions.s2 = s2
    const host = connect('ana', s2.session_id)
    await until(host, phase('lobby'), 'ana hosting')
    for (const person of ['ben', 'cy']) await rest(person, 'POST', '/sessions/join', { join_code: s2.join_code })
    await until(host, (s) => s.participants.length === 2, 'two joins')
    const ben = connect('ben', s2.session_id)
    const cy = connect('cy', s2.session_id)
    await until(ben, phase('lobby'), 'ben lobby')
    await until(cy, phase('lobby'), 'cy lobby')

    for (const [order, benPick, cyPick] of [
      [1, '4', '4'],
      [2, 'Mars', 'Jupiter'],
    ]) {
      await host.openNextQuestion()
      await until(ben, opened(order), `Q${order} ben`)
      await until(cy, opened(order), `Q${order} cy`)
      await ben.submitAnswer(pick(ben, benPick))
      await cy.submitAnswer(pick(cy, cyPick))
      const state = await until(host, resultsFor(order), `Q${order} results`)
      expect(state.lastClosed.reason).toBe('ALL_ANSWERED')
    }
    await expect(host.openNextQuestion()).rejects.toThrow('no more questions')
    await host.end()
    const final = await until(host, (s) => s.final && s.connection === 'ended', 'S2 ended')
    expect(ranking(final.final.standings)).toEqual([
      ['Cy', 2, 1],
      ['Ben', 1, 2],
    ])
    finals.s2 = final.final.standings
  }, 30_000)

  it('runs session 3: ta hosts quiz A and cancels it in the lobby', async () => {
    const s3 = await rest('ta', 'POST', `${base}/quizzes/${quizA.quiz_id}/sessions`)
    sessions.s3 = s3
    const host = connect('ta', s3.session_id)
    await until(host, phase('lobby'), 'ta hosting')
    await rest('cy', 'POST', `/sessions/${s3.session_id}/join`)
    const cy = connect('cy', s3.session_id)
    await until(cy, phase('lobby'), 'cy lobby')
    await host.cancel()
    for (const live of [host, cy]) {
      expect((await until(live, phase('ended'), 'cancelled')).final.reason).toBe('CANCELLED')
    }
    expect(await rest('ana', 'GET', `${base}/active-sessions`)).toEqual([])
  })

  it('shows final results, reports, the CSV export and history', async () => {
    const s1 = sessions.s1.session_id
    const hostView = await rest('prof', 'GET', `/sessions/${s1}/results`)
    expect(hostView.status).toBe('COMPLETED')
    expect(hostView.standings).toEqual(finals.s1)
    const deeView = await rest('dee', 'GET', `/sessions/${s1}/results`)
    expect(deeView.me).toMatchObject({ display_name: 'Dee', correct_count: 1, final_rank: 4 })
    expect(deeView.leaderboard).toHaveLength(4)
    // Being faculty or an organizer doesn't open someone else's session.
    expect(await refused('ta', 'GET', `/sessions/${s1}/results`)).toMatchObject({
      status: 403,
      code: 'session_access_denied',
    })
    expect(await refused('zed', 'GET', `/sessions/${s1}/results`)).toMatchObject({ status: 404 })
    expect((await rest('cy', 'GET', `/sessions/${sessions.s3.session_id}/results`)).status).toBe('CANCELLED')

    // Per-question report: host sees everyone, a player only themself.
    const report = await rest('prof', 'GET', `/sessions/${s1}/report`)
    expect(report).toMatchObject({ view: 'host', host_name: 'Prof', total_participants: 4, played_count: 4 })
    const states = Object.fromEntries(report.players.map((p) => [p.name, p.answers.map((a) => a.state)]))
    expect(states).toEqual({
      Ana: ['correct', 'correct', 'correct', 'missed'],
      Ben: ['correct', 'wrong', 'correct', 'missed'],
      Cy: ['wrong', 'missed', 'correct', 'missed'],
      Dee: ['missed', 'missed', 'wrong', 'correct'],
    })
    const own = await rest('ana', 'GET', `/sessions/${s1}/report`)
    expect(own.view).toBe('participant')
    expect(own.players.map((p) => p.name)).toEqual(['Ana'])
    expect(await refused('prof', 'GET', `/sessions/${s1}/report?personal=true`)).toMatchObject({
      status: 403,
      code: 'participant_report_denied',
    })

    // CSV export: host only, BOM for Excel, formula-looking text defused.
    const csv = await call('prof', 'GET', `/sessions/${s1}/results/export.csv`)
    expect(csv.status).toBe(200)
    expect(csv.headers.get('content-type')).toContain('text/csv')
    expect(csv.headers.get('content-disposition')).toBe(`attachment; filename="session-${s1}-results.csv"`)
    expect(csv.bytes.subarray(0, 3)).toEqual(Buffer.from([0xef, 0xbb, 0xbf]))
    const rows = readCsv(csv.bytes)
    expect(rows[0]).toEqual(['Quiz', 'World Capitals', 'Session', String(s1)])
    const scoreHeader = rows.findIndex((r) => r[0] === 'Rank')
    expect(rows.slice(scoreHeader + 1, scoreHeader + 5).map((r) => [r[0], r[1], r[3]])).toEqual([
      ['1', 'Ana', '3'],
      ['2', 'Ben', '2'],
      ['3', 'Cy', '1'],
      ['4', 'Dee', '1'],
    ])
    expect(rows.filter((r) => r[0] === 'Dee' && r[3] === 'missed')).toHaveLength(2)
    expect(await refused('ana', 'GET', `/sessions/${s1}/results/export.csv`)).toMatchObject({
      status: 403,
      code: 'results_export_denied',
    })
    const s2csv = readCsv((await call('ana', 'GET', `/sessions/${sessions.s2.session_id}/results/export.csv`)).bytes)
    expect(s2csv[0][1]).toBe("'=2+2 warm-up")

    // History: what each student played (newest first; a reused MySQL
    // database may hold older runs), and what prof hosted from quiz A.
    const taken = await rest('ben', 'GET', '/me/sessions/taken')
    expect(taken.items.slice(0, 2).map((s) => [s.session_id, s.rank])).toEqual([
      [sessions.s2.session_id, 2],
      [s1, 2],
    ])
    expect((await rest('dee', 'GET', '/me/sessions/taken')).items[0].session_id).toBe(s1)
    const hosted = await rest('prof', 'GET', `/quizzes/${quizA.quiz_id}/history`)
    expect(hosted.items.map((s) => s.session_id)).toEqual([s1])
    expect(await refused('ta', 'GET', `/quizzes/${quizA.quiz_id}/history`)).toMatchObject({ status: 404 })
  })

  it('reports on the class: dashboard, tabs, drill-downs and exports', async () => {
    const s1 = sessions.s1.session_id
    const s2 = sessions.s2.session_id
    const score = (standings, name) => standings.find((r) => r.display_name === name)?.total_score
    const played = {
      Ana: [score(finals.s1, 'Ana')],
      Ben: [score(finals.s1, 'Ben'), score(finals.s2, 'Ben')],
      Cy: [score(finals.s1, 'Cy'), score(finals.s2, 'Cy')],
      Dee: [score(finals.s1, 'Dee')],
    }
    const mean = (values) => values.reduce((a, b) => a + b, 0) / values.length
    const classAverage = mean(Object.values(played).map(mean))

    // Only completed sessions count; the cancelled one is left out.
    const dashboard = await rest('prof', 'GET', `${base}/dashboard`)
    expect(dashboard).toMatchObject({
      class_name: 'Full Flow 101',
      current_user_role: 'ORGANIZER',
      is_archived: false,
      active_member_count: 6,
      student_count: 4,
      completed_session_count: 2,
      attendance_rate: 0.75,
      active_sessions: [],
    })
    expect(dashboard.class_average).toBeCloseTo(classAverage, 0)
    expect(dashboard.students.map((s) => s.display_name)).toEqual(['Ana', 'Ben', 'Cy', 'Dee'])
    expect(dashboard.completed_sessions.map((s) => s.session_id)).toEqual([s2, s1])
    const memberView = await rest('ana', 'GET', `${base}/dashboard`)
    expect(memberView).toMatchObject({
      current_user_role: 'MEMBER',
      class_average: null,
      attendance_rate: null,
      students: null,
    })

    const quizzes = await rest('prof', 'GET', `${base}/presented-quizzes?sort=title&order=asc`)
    expect(quizzes.items.map((q) => [q.title, q.session_count, q.participant_count])).toEqual([
      ['=2+2 warm-up', 1, 2],
      ['World Capitals', 1, 4],
    ])
    const sessionTab = await rest('prof', 'GET', `${base}/sessions`)
    expect(sessionTab.items.map((s) => [s.session_id, s.host_name, s.participant_count])).toEqual([
      [s2, 'Ana', 2],
      [s1, 'Prof', 4],
    ])
    expect(sessionTab.items[1].top_score).toBe(score(finals.s1, 'Ana'))
    const benSessions = await rest('ben', 'GET', `${base}/sessions`)
    expect(benSessions.items.find((s) => s.session_id === s1)).toMatchObject({
      average_score: null,
      top_score: null,
      my_score: score(finals.s1, 'Ben'),
      my_rank: 2,
    })

    const students = await rest('prof', 'GET', `${base}/students`)
    const byName = Object.fromEntries(students.items.map((s) => [s.display_name, s]))
    expect(Object.keys(byName)).toEqual(['Ana', 'Ben', 'Cy', 'Dee'])
    expect(byName.Ana).toMatchObject({
      session_count: 1,
      attendance_rate: 0.5,
      total_points: score(finals.s1, 'Ana'),
      recent_scores: [null, score(finals.s1, 'Ana')],
    })
    expect(byName.Cy.recent_scores).toEqual([score(finals.s2, 'Cy'), score(finals.s1, 'Cy')])
    expect(await refused('ana', 'GET', `${base}/students`)).toMatchObject({
      status: 403,
      code: 'not_class_organizer',
    })

    // Drill-downs.
    const sessionReport = await rest('ta', 'GET', `${base}/sessions/${s1}/results`)
    expect(sessionReport).toMatchObject({ view: 'host', class_id: course.class_id, total_participants: 4 })
    expect(sessionReport.players.map((p) => p.name)).toEqual(['Ana', 'Ben', 'Cy', 'Dee'])
    expect((await rest('ana', 'GET', `${base}/sessions/${s1}/results`)).players.map((p) => p.name)).toEqual(['Ana'])
    expect(await refused('dee', 'GET', `${base}/sessions/${s2}/results`)).toMatchObject({
      status: 403,
      code: 'participant_report_denied',
    })
    expect(await refused('prof', 'GET', `${base}/sessions/${sessions.s3.session_id}/results`)).toMatchObject({
      status: 404,
      code: 'session_not_found',
    })
    expect(await refused('zed', 'GET', `${base}/sessions/${s1}/results`)).toMatchObject({
      status: 404,
      code: 'class_not_found',
    })

    const quizReport = await rest('prof', 'GET', `${base}/quizzes/${quizA.quiz_id}/results`)
    expect(quizReport).toMatchObject({ view: 'organizer', title: 'World Capitals', session_count: 1, participant_count: 4 })
    expect(quizReport.sessions[0].results.map((r) => [r.name, r.rank])).toEqual([
      ['Ana', 1],
      ['Ben', 2],
      ['Cy', 3],
      ['Dee', 4],
    ])
    const ownQuizReport = await rest('cy', 'GET', `${base}/quizzes/${quizA.quiz_id}/results`)
    expect(ownQuizReport).toMatchObject({ view: 'member', average_score: null })
    expect(ownQuizReport.sessions[0].results.map((r) => r.name)).toEqual(['Cy'])

    const dee = await rest('prof', 'GET', `${base}/students/${me.dee.account_id}/results`)
    expect(dee).toMatchObject({
      view: 'organizer',
      email: 'dee@e2e.invalid',
      class_session_count: 2,
      session_count: 1,
      attendance_rate: 0.5,
      correct_count: 1,
      incorrect_count: 3,
    })
    expect(dee.sessions.map((s) => [s.session_id, s.played])).toEqual([
      [s2, false],
      [s1, true],
    ])
    expect(await rest('ben', 'GET', `${base}/students/${me.ben.account_id}/results`)).toMatchObject({
      view: 'member',
      email: null,
      correct_count: 3,
      incorrect_count: 3,
      class_average: null,
    })
    expect(await refused('ana', 'GET', `${base}/students/${me.ben.account_id}/results`)).toMatchObject({
      status: 403,
      code: 'not_class_organizer',
    })

    // Excel exports: real workbooks, and text never turns into a formula.
    const download = async (person, path) => {
      const res = await call(person, 'GET', path)
      expect(res.status, `${person} ${path}`).toBe(200)
      expect(res.headers.get('content-type')).toBe(XLSX)
      const book = readXlsx(res.bytes)
      expect(book.formulas).toBe(0)
      return book
    }
    const sessionBook = await download('prof', `${base}/sessions/${s1}/export.xlsx`)
    expect(sessionBook.sheetNames).toEqual(['Summary', 'Scores', 'Answers'])
    expect(sessionBook.sheets.Scores.slice(1).map((r) => [r[0], r[1], r[3]])).toEqual([
      [1, 'Ana', 3],
      [2, 'Ben', 2],
      [3, 'Cy', 1],
      [4, 'Dee', 1],
    ])
    expect(sessionBook.sheets.Answers).toHaveLength(1 + 4 * 4)
    const quizBook = await download('prof', `${base}/quizzes/${quizB.quiz_id}/export.xlsx`)
    expect(quizBook.sheetNames).toEqual(['Summary', 'Presentations', 'Results'])
    expect(quizBook.sheets.Summary[1]).toEqual(['Quiz', "'=2+2 warm-up"])
    expect(quizBook.sheets.Results.slice(1).map((r) => [r[2], r[3]])).toEqual([
      [1, 'Cy'],
      [2, 'Ben'],
    ])
    const studentBook = await download('prof', `${base}/students/${me.dee.account_id}/export.xlsx`)
    expect(studentBook.sheetNames).toEqual(['Summary', 'Sessions'])
    expect(studentBook.sheets.Sessions.slice(1).map((r) => [r[1], r[3]])).toEqual([
      [s2, 'No'],
      [s1, 'Yes'],
    ])
    const ownBook = await download('ana', `${base}/students/${me.ana.account_id}/export.xlsx`)
    expect(ownBook.sheets.Summary.map((r) => r[0])).not.toContain('Email')
    for (const path of [
      `${base}/sessions/${s1}/export.xlsx`,
      `${base}/quizzes/${quizA.quiz_id}/export.xlsx`,
      `${base}/students/${me.ben.account_id}/export.xlsx`,
    ]) {
      expect(await refused('ana', 'GET', path)).toMatchObject({ status: 403, code: 'not_class_organizer' })
    }

    // The gradebook: one column per completed session, oldest first; a blank
    // cell means absent, not zero.
    const grades = await call('prof', 'GET', `${base}/grades/export.csv`)
    expect(grades.status).toBe(200)
    expect(grades.headers.get('content-disposition')).toBe('attachment; filename="full-flow-101-grades.csv"')
    const [header, ...gradeRows] = readCsv(grades.bytes)
    expect(header[0]).toBe('Student')
    expect(header[2]).toMatch(/^World Capitals \(\d{4}-\d{2}-\d{2}\)$/)
    expect(header[3]).toMatch(/^'=2\+2 warm-up \(\d{4}-\d{2}-\d{2}\)$/)
    expect(header.slice(4)).toEqual(['Sessions played', 'Attendance %', 'Average points', 'Total points'])
    expect(gradeRows.map((r) => r.slice(0, 2))).toEqual(STUDENTS.map((p) => [me[p].display_name, me[p].email]))
    const anaRow = gradeRows[0]
    expect(anaRow.slice(2, 6)).toEqual([String(score(finals.s1, 'Ana')), '', '1', '50.0'])
    expect(await refused('ana', 'GET', `${base}/grades/export.csv`)).toMatchObject({
      status: 403,
      code: 'not_class_organizer',
    })
  })

  it('archives the class: reports stay, new activity stops', async () => {
    const archived = await rest('prof', 'POST', `${base}/archive`)
    expect(archived.archived_at).not.toBeNull()
    expect(archived).toMatchObject({ joining_open: false, join_code: null })

    expect(await refused('zed', 'POST', '/classes/join', { code: course.join_code })).toMatchObject({
      status: 404,
      code: 'class_code_not_found',
    })
    expect(await refused('prof', 'POST', `${base}/quizzes/${quizA.quiz_id}/sessions`)).toMatchObject({
      status: 409,
      code: 'class_archived',
    })
    expect(await refused('ana', 'GET', `${base}/approved-quizzes`)).toMatchObject({
      status: 409,
      code: 'class_archived',
    })
    expect(await rest('prof', 'GET', `${base}/dashboard`)).toMatchObject({
      is_archived: true,
      completed_session_count: 2,
    })
    expect((await call('prof', 'GET', `${base}/grades/export.csv`)).status).toBe(200)
  })
})
