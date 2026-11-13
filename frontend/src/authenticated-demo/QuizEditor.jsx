import { useEffect, useRef, useState } from "react";
import {
  Link,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router";
import { useAccount } from "./account";
import QuizCollaborators from "./QuizCollaborators";

import { blankEditor, LETTERS, newQuestion } from "./model";
import {
  normalizeEditorDefaultTime,
  quizQuestionToEditor,
  toQuestionCreate,
  toQuizCreate,
} from "./quizPayload";
import {
  canApplyRemoteQuestion,
  canSaveDraftIndependently,
  nextAggregateRevision,
  remoteStructureDecision,
  saveAggregateQuiz,
  saveDraftQuestions,
} from "./quizDraftSave";
import { useAction, useApi, useResource } from "./rest";
import RequestError from "./RequestError";
import ConfirmDialog from "./ConfirmDialog";
import { useConfirm } from "./useConfirm";
import { QuestionMenu, TimePicker } from "./EditorParts";
import { useQuizCollaboration } from "./useQuizCollaboration";
import { classPagePath } from "../classes/classPaths";
import NewQuizClassPicker from "../classes/NewQuizClassPicker";
import HostQuizButton from "./HostQuizButton";
import { sendQuizForApproval, useQuizFlow } from "./quizFlow";
import { QuizFlowPanel } from "./QuizFlowPanel";
import "./quiz-flow.css";

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

// m:ss, as in the mockup's "6 questions · 3:20 total"
function clock(totalSeconds) {
  const seconds = Number.isFinite(totalSeconds) ? totalSeconds : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

// Scroll a question card under the sticky strip and focus it.
function goToQuestion(id) {
  const card = document.getElementById(`question-${id}`);
  card?.scrollIntoView({ block: "start", behavior: "smooth" });
  card?.focus({ preventScroll: true });
}

// Highlights the jump chip of the card in the upper part of the viewport.
function useCurrentQuestion(ids) {
  const [current, setCurrent] = useState(null);
  const key = ids.join(",");

  useEffect(() => {
    function update() {
      const strip = document.querySelector(".qe-strip");
      const line = (strip?.getBoundingClientRect().bottom ?? 0) + 120;
      let found = ids[0] ?? null;

      for (const id of ids) {
        const card = document.getElementById(`question-${id}`);
        if (card && card.getBoundingClientRect().top <= line) found = id;
      }

      setCurrent(found);
    }

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);

    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
    // `key` stands in for the ids array, which is rebuilt every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return current;
}

function JumpChips({ ids, current }) {
  return (
    <nav className="qe-jump" aria-label="Jump to question">
      {ids.length ? (
        ids.map((id, index) => (
          <button
            type="button"
            key={id}
            className="qe-jchip"
            aria-current={current === id ? "true" : undefined}
            onClick={() => goToQuestion(id)}
          >
            Q{index + 1}
          </button>
        ))
      ) : (
        <span className="qe-jnone">No questions yet</span>
      )}
    </nav>
  );
}

export function QuizEditor({
  initialEditor = null,
  existingQuiz = null,
  onReload,
}) {
  const [initial] = useState(() => initialEditor ?? blankEditor());
  const [editor, setEditor] = useState(initial);
  const [baselineEditor, setBaselineEditor] = useState(initial);
  const [validation, setValidation] = useState("");
  const [explaining, setExplaining] = useState(() => new Set());
  const [remoteNotice, setRemoteNotice] = useState(null);
  const [autosaveError, setAutosaveError] = useState(null);
  const [questionSaveStatus, setQuestionSaveStatus] = useState({});
  const autosaveTimers = useRef(new Map());
  const savingQuestions = useRef(new Set());
  const editorRef = useRef(initial);
  const baselineEditorRef = useRef(initial);
  const quizRevisionRef = useRef(existingQuiz?.revision ?? null);
  const aggregateStaleRef = useRef(false);

  const api = useApi();
  const action = useAction();
  const account = useAccount();
  const navigate = useNavigate();
  const confirmer = useConfirm();
  const archiveAction = useAction();
  const [searchParams] = useSearchParams();

  const editing = existingQuiz !== null;
  // Sharing and archiving are the owner's, on a saved quiz in a class.
  const ownsQuiz =
    editing &&
    existingQuiz.author_id === account.account_id &&
    Boolean(existingQuiz.class_id);
  // Sending publishes the draft first, and only the owner can publish.
  const canSendFromEditor =
    !editing || existingQuiz.author_id === account.account_id;
  // Which save button was pressed, for its "Saving…" / "Sending…" label.
  const [savingKind, setSavingKind] = useState(null);
  // New quizzes belong to a class: the class page links here with ?class=ID.
  const classId = searchParams.get("class");
  const validClass = /^[1-9][0-9]*$/.test(classId ?? "");
  const dirty = JSON.stringify(editor) !== JSON.stringify(baselineEditor);

  const requestError = autosaveError ?? action.error;
  const conflict = ["quiz_edit_conflict", "question_edit_conflict"].includes(
    requestError?.code,
  );
  const questionSaving = Object.values(questionSaveStatus).includes("saving");

  const collaborationStatus = useQuizCollaboration(
    editing ? existingQuiz.quiz_id : null,
    (message) => {
      if (message.editor_account_id === account.account_id) return;
      if (message.type === "question_updated") {
        const questionId = message.question.question_id;
        const currentEditor = editorRef.current;
        const currentBaseline = baselineEditorRef.current;
        const local = currentEditor.questions.find(
          (question) => question.questionId === questionId,
        );
        const baseline = currentBaseline.questions.find(
          (question) => question.questionId === questionId,
        );
        if (!canApplyRemoteQuestion(local, baseline)) {
          aggregateStaleRef.current = true;
          setRemoteNotice({
            tone: "warning",
            text: "A collaborator saved this question while you have local changes.",
            detail:
              "Your work is still here. Save to check for a conflict, or reload the latest quiz.",
            reload: true,
          });
          return;
        }
        const index = currentEditor.questions.indexOf(local);
        const updated = quizQuestionToEditor(
          message.question,
          index,
          currentEditor.defaultTime,
        );
        const nextEditor = normalizeEditorDefaultTime({
          ...currentEditor,
          questions: currentEditor.questions.map((question) =>
            question.questionId === questionId ? updated : question,
          ),
        });
        const nextBaseline = normalizeEditorDefaultTime({
          ...currentBaseline,
          questions: currentBaseline.questions.map((question) =>
            question.questionId === questionId ? updated : question,
          ),
        });
        editorRef.current = nextEditor;
        baselineEditorRef.current = nextBaseline;
        setEditor(nextEditor);
        setBaselineEditor(nextBaseline);
        acceptQuizRevision(message.quiz_revision);
        setQuestionStatus(questionId, "remote");
        if (!aggregateStaleRef.current) {
          setRemoteNotice({
            tone: "success",
            text: `Question ${index + 1} was updated by a collaborator.`,
            detail: "The saved change is now shown in your editor.",
            reload: false,
          });
        }
        return;
      }
      if (message.type === "question_added") {
        const questionId = message.question.question_id;
        const append = (currentEditor) => {
          if (
            currentEditor.questions.some(
              (question) => question.questionId === questionId,
            )
          ) {
            return currentEditor;
          }
          return {
            ...currentEditor,
            questions: [
              ...currentEditor.questions,
              quizQuestionToEditor(
                message.question,
                currentEditor.questions.length,
                currentEditor.defaultTime,
              ),
            ],
          };
        };
        const nextEditor = append(editorRef.current);
        const nextBaseline = append(baselineEditorRef.current);
        editorRef.current = nextEditor;
        baselineEditorRef.current = nextBaseline;
        setEditor(nextEditor);
        setBaselineEditor(nextBaseline);
        acceptQuizRevision(message.quiz_revision);
        if (!aggregateStaleRef.current) {
          setRemoteNotice({
            tone: "success",
            text: "A collaborator added a new question.",
            detail: "It was added without changing your unsaved question work.",
            reload: false,
          });
        }
        return;
      }
      if (message.type === "quiz_structure_updated") {
        const decision = remoteStructureDecision({
          editor: editorRef.current,
          baselineEditor: baselineEditorRef.current,
          currentRevision: quizRevisionRef.current,
          incomingRevision: message.quiz_revision,
        });
        if (decision.reload) {
          quizRevisionRef.current = decision.revision;
          onReload?.();
          return;
        }
        aggregateStaleRef.current = true;
        setRemoteNotice({
          tone: "warning",
          text: "A collaborator changed the quiz structure.",
          detail:
            "Reload when you are ready. Your unsaved work has not been replaced.",
          reload: true,
        });
      } else if (message.type === "quiz_published") {
        const decision = remoteStructureDecision({
          editor: editorRef.current,
          baselineEditor: baselineEditorRef.current,
          currentRevision: quizRevisionRef.current,
          incomingRevision: message.quiz_revision,
        });
        if (decision.reload) {
          quizRevisionRef.current = decision.revision;
          onReload?.();
          return;
        }
        aggregateStaleRef.current = true;
        setRemoteNotice({
          tone: "info",
          text: "The owner sent this version for approval.",
          detail:
            "Reload when you are ready. Your unsaved work has not been replaced.",
          reload: true,
        });
      }
    },
  );

  const backTo = editing
    ? `/app/quizzes/${existingQuiz.quiz_id}`
    : validClass
      ? `/app/classes/${classId}`
      : "/app/classes";

  const ids = editor.questions.map((question) => question.id);
  const current = useCurrentQuestion(ids);

  const defaultTime = Number(editor.defaultTime);
  const ownTime = (question) =>
    question.limit != null && Number(question.limit) !== defaultTime
      ? Number(question.limit)
      : null;
  const timeOf = (question) => Number(question.limit ?? editor.defaultTime);
  // Validation messages start with "Question N:" when one card is at fault.
  const badQuestion =
    ids[Number(/^Question (\d+):/.exec(validation)?.[1]) - 1] ?? null;

  const totalTime = editor.questions.reduce(
    (sum, question) => sum + (timeOf(question) || 0),
    0,
  );

  useEffect(() => {
    if (!dirty) return;

    function warnBeforeUnload(event) {
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", warnBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
    };
  }, [dirty]);

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  useEffect(() => {
    baselineEditorRef.current = baselineEditor;
  }, [baselineEditor]);

  useEffect(
    () => () => {
      for (const timer of autosaveTimers.current.values()) {
        window.clearTimeout(timer);
      }
      autosaveTimers.current.clear();
    },
    [],
  );

  async function leaveEditor(event) {
    if (action.busy) {
      event.preventDefault();
      return;
    }

    if (!dirty) return;

    event.preventDefault();

    if (
      await confirmer.confirm({
        label: "Unsaved changes",
        title: "Discard your changes?",
        message: "Leaving now throws away everything you haven't saved.",
        confirmLabel: "Discard",
        cancelLabel: "Keep editing",
      })
    ) {
      navigate(backTo);
    }
  }

  // Archive and save can't overlap in either direction: archiving waits for
  // a save (including the publish and submit of "Save and send"), and saving
  // waits for an archive. Otherwise a send could land on an archived quiz.
  const archiveBlocked =
    archiveAction.busy || action.busy || Boolean(savingKind) || questionSaving;

  async function archiveQuiz() {
    if (archiveBlocked) return;
    const sure = await confirmer.confirm({
      label: "Archive quiz",
      title: `Archive “${editor.title.trim() || "this quiz"}”?`,
      message:
        (dirty ? "Your unsaved changes will be lost. " : "") +
        "It will no longer be available to edit or host. Past results stay saved.",
      confirmLabel: "Archive quiz",
      cancelLabel: "Keep it",
    });
    if (!sure) return;

    const done = await archiveAction.run(async () => {
      await api(`/quizzes/${existingQuiz.quiz_id}/archive`, {
        method: "PATCH",
      });
      return true;
    });
    if (done) {
      navigate(classPagePath(existingQuiz.class_id), { replace: true });
    }
  }

  function edit(next) {
    editorRef.current = next;
    setEditor(next);
    setValidation("");
  }

  function changeQuestion(id, changes) {
    const currentEditor = editorRef.current;
    const index = currentEditor.questions.findIndex(
      (question) => question.id === id,
    );
    if (index < 0) return;

    const updatedQuestion = {
      ...currentEditor.questions[index],
      ...changes,
    };
    const questions = [...currentEditor.questions];
    questions[index] = updatedQuestion;
    edit({ ...currentEditor, questions });
    scheduleQuestionAutosave(updatedQuestion, index);
  }

  function move(index, offset) {
    const questions = [...editor.questions];
    const next = index + offset;

    [questions[index], questions[next]] = [questions[next], questions[index]];

    edit({ ...editor, questions });
  }

  // "+ Insert question here": a blank question at this position.
  function insertAt(index) {
    const question = newQuestion();
    const questions = [...editor.questions];
    questions.splice(index, 0, question);

    edit({ ...editor, questions });

    window.requestAnimationFrame(() => {
      goToQuestion(question.id);
      document.getElementById(`question-text-${question.id}`)?.focus({
        preventScroll: true,
      });
    });
  }

  // Changing the quiz-wide time moves every question that followed it.
  function setQuizTime(seconds) {
    edit({
      ...editor,
      defaultTime: seconds,
      questions: editor.questions.map((question) =>
        ownTime(question) == null ? { ...question, limit: null } : question,
      ),
    });
  }

  // Picking the quiz time for one question means "follow the quiz".
  function setOwnTime(id, seconds) {
    changeQuestion(id, {
      limit: seconds == null || seconds === defaultTime ? null : seconds,
    });
  }

  async function deleteQuestion(question, index) {
    if (
      await confirmer.confirm({
        label: `Question ${index + 1}`,
        title: "Delete this question?",
        message: question.text.trim() || "This question is still blank.",
        confirmLabel: "Delete",
        cancelLabel: "Keep it",
      })
    ) {
      if (question.questionId) {
        const timer = autosaveTimers.current.get(question.questionId);
        if (timer) window.clearTimeout(timer);
        autosaveTimers.current.delete(question.questionId);
        setQuestionSaveStatus((currentStatus) => {
          const nextStatus = { ...currentStatus };
          delete nextStatus[question.questionId];
          return nextStatus;
        });
      }
      edit({
        ...editor,
        questions: editor.questions.filter((item) => item.id !== question.id),
      });
    }
  }

  // Checks the quiz can be saved; shows the first problem if not.
  function validate() {
    try {
      toQuizCreate(editorRef.current);
      setValidation("");
      return true;
    } catch (error) {
      setValidation(error.message);
      return false;
    }
  }

  function acceptQuizRevision(revision) {
    quizRevisionRef.current = nextAggregateRevision(
      quizRevisionRef.current,
      revision,
      aggregateStaleRef.current,
    );
  }

  function setQuestionStatus(questionId, status) {
    setQuestionSaveStatus((currentStatus) => ({
      ...currentStatus,
      [questionId]: status,
    }));
  }

  function scheduleQuestionAutosave(question, index, delay = 800) {
    if (
      !editing ||
      existingQuiz.status !== "DRAFT" ||
      !question.questionId ||
      conflict
    ) {
      return;
    }

    const previousTimer = autosaveTimers.current.get(question.questionId);
    if (previousTimer) window.clearTimeout(previousTimer);
    setQuestionStatus(question.questionId, "pending");
    const timer = window.setTimeout(() => {
      autosaveTimers.current.delete(question.questionId);
      void autosaveQuestion(question, index);
    }, delay);
    autosaveTimers.current.set(question.questionId, timer);
  }

  async function autosaveQuestion(question, index) {
    const questionId = question.questionId;
    if (!questionId) return;
    if (savingQuestions.current.has(questionId)) {
      scheduleQuestionAutosave(question, index, 250);
      return;
    }

    let payload;
    try {
      payload = toQuestionCreate(
        question,
        index,
        editorRef.current.defaultTime,
      );
    } catch {
      setQuestionStatus(questionId, "invalid");
      return;
    }

    payload.expected_revision = question.revision;
    savingQuestions.current.add(questionId);
    setQuestionStatus(questionId, "saving");
    setAutosaveError(null);
    let savedSuccessfully = false;

    try {
      const result = await api(
        `/classes/${existingQuiz.class_id}/quizzes/${existingQuiz.quiz_id}` +
          `/questions/${questionId}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      const saved = quizQuestionToEditor(
        result.question,
        index,
        editorRef.current.defaultTime,
      );
      const nextBaseline = {
        ...baselineEditorRef.current,
        questions: baselineEditorRef.current.questions.map((item) =>
          item.questionId === questionId ? saved : item,
        ),
      };
      baselineEditorRef.current = nextBaseline;
      setBaselineEditor(nextBaseline);
      const currentEditor = editorRef.current;
      const nextEditor = {
        ...currentEditor,
        questions: currentEditor.questions.map((currentQuestion) => {
          if (currentQuestion.questionId !== questionId) return currentQuestion;
          // Do not replace keystrokes entered while this request was running.
          return JSON.stringify(currentQuestion) === JSON.stringify(question)
            ? saved
            : { ...currentQuestion, revision: saved.revision };
        }),
      };
      editorRef.current = nextEditor;
      setEditor(nextEditor);
      acceptQuizRevision(result.quiz_revision);
      if (!aggregateStaleRef.current) setRemoteNotice(null);
      setQuestionStatus(questionId, "saved");
      savedSuccessfully = true;
    } catch (failure) {
      setAutosaveError(failure);
      if (failure.code === "question_edit_conflict") {
        aggregateStaleRef.current = true;
        setRemoteNotice({
          tone: "warning",
          text: "A collaborator saved this question before your changes.",
          detail: "Reload the latest quiz before making an aggregate save.",
          reload: true,
        });
      }
      setQuestionStatus(
        questionId,
        failure.code === "question_edit_conflict" ? "conflict" : "error",
      );
    } finally {
      savingQuestions.current.delete(questionId);
      const currentQuestion = editorRef.current.questions.find(
        (item) => item.questionId === questionId,
      );
      const baselineQuestion = baselineEditorRef.current.questions.find(
        (item) => item.questionId === questionId,
      );
      if (
        savedSuccessfully &&
        currentQuestion &&
        baselineQuestion &&
        JSON.stringify(currentQuestion) !== JSON.stringify(baselineQuestion)
      ) {
        scheduleQuestionAutosave(
          currentQuestion,
          editorRef.current.questions.indexOf(currentQuestion),
          250,
        );
      }
    }
  }

  // Saves the draft. With send, it then publishes and sends that version for
  // approval in the same click, so nobody has to go back to the class page.
  async function save({ send = false } = {}) {
    if (
      conflict ||
      savingQuestions.current.size > 0 ||
      savingKind ||
      archiveAction.busy
    ) {
      return;
    }
    if (!validate()) return;
    setSavingKind(send ? "send" : "draft");
    try {
      await saveAndContinue(send);
    } finally {
      setSavingKind(null);
    }
  }

  async function saveAndContinue(send) {
    // The final save owns every still-pending local change. Prevent a delayed
    // question autosave from racing the requests below with the same revision.
    for (const timer of autosaveTimers.current.values()) {
      window.clearTimeout(timer);
    }
    autosaveTimers.current.clear();

    const quiz = await action.run(async () => {
      const savingEditor = editorRef.current;
      const savingBaseline = baselineEditorRef.current;

      if (editing) {
        // Published quizzes need one aggregate save to create the next draft.
        // Existing questions and questions appended to a draft use independent
        // mutations. Deleting, reordering, inserting in the middle, or renaming
        // still uses the aggregate revision until those operations are split.
        if (
          existingQuiz.status === "DRAFT" &&
          canSaveDraftIndependently(savingEditor, savingBaseline)
        ) {
          const result = await saveDraftQuestions({
            editor: savingEditor,
            baselineEditor: savingBaseline,
            existingQuiz,
            api,
            onProgress: (progress) => {
              editorRef.current = progress.editor;
              baselineEditorRef.current = progress.baselineEditor;
              setEditor(progress.editor);
              setBaselineEditor(progress.baselineEditor);
              acceptQuizRevision(progress.quizRevision);
            },
          });
          return result.lastResult
            ? { quiz_id: existingQuiz.quiz_id }
            : existingQuiz;
        }

        return saveAggregateQuiz({
          editor: savingEditor,
          revision: quizRevisionRef.current,
          existingQuiz,
          api,
        });
      }

      return api(`/classes/${classId}/quizzes`, {
        method: "POST",
        body: JSON.stringify(toQuizCreate(savingEditor)),
      });
    });

    if (!quiz) return;

    const savedId = quiz.quiz_id ?? existingQuiz?.quiz_id;
    const quizClassId = editing ? existingQuiz.class_id : Number(classId);
    let notice = { tone: "success", text: "Draft saved." };

    if (send) {
      // The draft is already saved, so a failure here must not send people
      // back into the editor (saving again would duplicate a new quiz).
      try {
        await sendQuizForApproval(api, quizClassId, savedId);
        notice = { tone: "success", text: "Saved and sent for approval." };
      } catch (error) {
        notice = {
          tone: "warning",
          text: `Saved as a draft, but it couldn't be sent for approval: ${error.message}`,
        };
      }
    }

    navigate(`/app/quizzes/${savedId}`, {
      replace: true,
      state: { classId: quizClassId, notice },
    });
  }

  if (!editing && !validClass) {
    return <NewQuizClassPicker />;
  }

  return (
    <>
    {/* The collaborator disclosure owns its own invite form, so it must stay
        outside the quiz editor form. Put it first so sharing is visible at
        the top of editing mode instead of below every question. */}
    {ownsQuiz && <QuizCollaborators quiz={existingQuiz} />}

    <form
      className="qe"
      noValidate
      onSubmit={(event) => event.preventDefault()}
    >
      <ConfirmDialog confirmer={confirmer} />

      <fieldset
        disabled={action.busy || archiveAction.busy}
        className="qp-form-fields"
      >
        <div className="qe-bar">
          <Link className="qe-back" to={backTo} onClick={leaveEditor}>
            <span aria-hidden="true">←</span>
            <span className="qe-back-word">{editing ? "Quiz" : "Class"}</span>
            <span className="ui-sr">
              {editing ? "Cancel editing" : "Back to class"}
            </span>
          </Link>

          <div className="qe-titlebox">
            <label className="qe-eyebrow" htmlFor="quiz-title">
              Quiz title
            </label>
            <input
              id="quiz-title"
              maxLength={200}
              autoComplete="off"
              placeholder="Untitled quiz"
              value={editor.title}
              onChange={(event) =>
                edit({
                  ...editor,
                  title: event.target.value,
                })
              }
            />

            <textarea
              rows={1}
              className="qe-description"
              aria-label="Description (optional)"
              placeholder="Add a short description (optional)"
              value={editor.description ?? ""}
              onChange={(event) =>
                edit({
                  ...editor,
                  description: event.target.value,
                })
              }
            />
          </div>

          <div className="qe-state">
            <span className={"qe-pill" + (editing ? " is-saved" : "")}>
              {editing
                ? `Editing · v${existingQuiz.version.version_number}`
                : "New quiz"}
            </span>
          </div>
        </div>

        <div className="qe-strip">
          <JumpChips ids={ids} current={current} />

          <TimePicker
            title="Time per question"
            label={`Time per question: ${editor.defaultTime} seconds. Change`}
            defaultTime={editor.defaultTime}
            onPick={setQuizTime}
            summaryClass="qe-tpbtn"
            footer={
              <p className="qe-fine">
                Every question uses this unless you give it its own time. The
                quiz runs <b>{clock(totalTime)}</b>.
              </p>
            }
          >
            <span className="qe-k">
              <span className="qe-long">Time </span>per question
            </span>
            <span className="qe-v">
              <b>{editor.defaultTime}s</b>
              <span aria-hidden="true">▾</span>
            </span>
          </TimePicker>
        </div>

        {editing && (collaborationStatus !== "open" || remoteNotice) && (
          <div
            className={`qe-collaboration is-${collaborationStatus}`}
            aria-live="polite"
          >
            {collaborationStatus !== "open" && (
              <div className="qe-live-state">
                <span className="qe-live-dot" aria-hidden="true" />
                <span>
                  <b>
                    {collaborationStatus === "reconnecting"
                      ? "Reconnecting live editing…"
                      : collaborationStatus === "failed"
                        ? "Live editing unavailable"
                        : "Connecting live editing…"}
                  </b>
                  <small>
                    You can still save; refresh before editing shared content.
                  </small>
                </span>
              </div>
            )}

            {remoteNotice && (
              <div className={`qe-live-message is-${remoteNotice.tone}`}>
                <span aria-hidden="true">
                  {remoteNotice.tone === "success" ? "✓" : "!"}
                </span>
                <p>
                  <strong>{remoteNotice.text}</strong>
                  <small>{remoteNotice.detail}</small>
                </p>
                {remoteNotice.reload && (
                  <button
                    type="button"
                    className="qb-btn qb-btn-paper"
                    onClick={() => onReload?.()}
                  >
                    Reload latest
                  </button>
                )}
                {!remoteNotice.reload && (
                  <button
                    type="button"
                    className="ui-linkbtn"
                    onClick={() => setRemoteNotice(null)}
                  >
                    Dismiss
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        <div className="qe-stack">
          {editor.questions.length > 0 ? (
            <p className="qe-intro">
              Click a letter to mark the <b>correct answer</b>. Every question
              gets <b>{editor.defaultTime}s</b> unless you give it its own time.
            </p>
          ) : (
            <div className="qe-empty">
              <h2>No questions yet.</h2>
              <p>Add one to get started. You need at least one to save.</p>
            </div>
          )}

          {editor.questions.map((question, index) => {
            const own = ownTime(question);
            const showExplanation =
              explaining.has(question.id) || Boolean(question.explanation);

            return (
              <div className="qe-item" key={question.id}>
                {index > 0 && (
                  <div className="qe-insert">
                    <button type="button" onClick={() => insertAt(index)}>
                      + Insert question here
                      <span className="ui-sr">
                        {" "}
                        (before question {index + 1})
                      </span>
                    </button>
                  </div>
                )}

                <article
                  className="qe-card"
                  id={`question-${question.id}`}
                  tabIndex={-1}
                  aria-label={`Question ${index + 1}`}
                >
                  <div className="qe-top">
                    <span>Question {index + 1}</span>

                    <QuestionMenu
                      number={index + 1}
                      first={index === 0}
                      last={index === editor.questions.length - 1}
                      onMove={(offset) => move(index, offset)}
                      onDelete={() => void deleteQuestion(question, index)}
                    />
                  </div>

                  <div className="qe-body">
                    <textarea
                      id={`question-text-${question.id}`}
                      className="qe-qtext"
                      rows={1}
                      aria-label={`Question ${index + 1} text`}
                      placeholder="Type your question"
                      value={question.text}
                      onChange={(event) =>
                        changeQuestion(question.id, {
                          text: event.target.value,
                        })
                      }
                    />

                    <div
                      className="qe-choices"
                      role="radiogroup"
                      aria-label={`Correct answer for question ${index + 1}`}
                    >
                      {question.options.map((option, choiceIndex) => {
                        const correct = question.correct === choiceIndex;

                        return (
                          <div
                            className={
                              "qe-choice" + (correct ? " is-correct" : "")
                            }
                            key={choiceIndex}
                          >
                            <button
                              type="button"
                              className="qe-mark"
                              role="radio"
                              aria-checked={correct}
                              aria-label={`Choice ${LETTERS[choiceIndex]}, mark correct`}
                              title={`Mark ${LETTERS[choiceIndex]} as the correct answer`}
                              onClick={() =>
                                changeQuestion(question.id, {
                                  correct: choiceIndex,
                                })
                              }
                            >
                              <span aria-hidden="true">
                                {correct ? "✓" : LETTERS[choiceIndex]}
                              </span>
                            </button>

                            <input
                              maxLength={500}
                              value={option}
                              placeholder={`Choice ${LETTERS[choiceIndex]}`}
                              aria-label={
                                `Question ${index + 1}, ` +
                                `choice ${LETTERS[choiceIndex]}`
                              }
                              onChange={(event) =>
                                changeQuestion(question.id, {
                                  options: question.options.map((text, i) =>
                                    i === choiceIndex
                                      ? event.target.value
                                      : text,
                                  ),
                                })
                              }
                            />

                            <span className="qe-choice-end">
                              {correct && (
                                <span className="qe-tag" aria-hidden="true">
                                  Correct
                                </span>
                              )}

                              {question.options.length > 2 && (
                                <button
                                  type="button"
                                  className="qe-rm"
                                  aria-label={`Remove choice ${LETTERS[choiceIndex]}`}
                                  title="Remove choice"
                                  onClick={() =>
                                    changeQuestion(question.id, {
                                      options: question.options.filter(
                                        (_, i) => i !== choiceIndex,
                                      ),
                                      correct:
                                        question.correct === choiceIndex
                                          ? null
                                          : question.correct !== null &&
                                              question.correct > choiceIndex
                                            ? question.correct - 1
                                            : question.correct,
                                    })
                                  }
                                >
                                  ×
                                </button>
                              )}
                            </span>
                          </div>
                        );
                      })}
                    </div>

                    <div className="qe-links">
                      {question.options.length < 4 && (
                        <button
                          type="button"
                          className="ui-linkbtn"
                          onClick={() =>
                            changeQuestion(question.id, {
                              options: [...question.options, ""],
                            })
                          }
                        >
                          + Add choice
                        </button>
                      )}

                      {!showExplanation && (
                        <button
                          type="button"
                          className="ui-linkbtn"
                          onClick={() => {
                            setExplaining(
                              (open) => new Set([...open, question.id]),
                            );
                            window.requestAnimationFrame(() =>
                              document
                                .getElementById(`explanation-${question.id}`)
                                ?.focus(),
                            );
                          }}
                        >
                          + Add explanation
                        </button>
                      )}
                    </div>

                    {showExplanation && (
                      <label className="qe-explanation">
                        <span className="qe-eyebrow">
                          Answer explanation (optional)
                        </span>
                        <textarea
                          id={`explanation-${question.id}`}
                          rows={2}
                          maxLength={5000}
                          value={question.explanation ?? ""}
                          placeholder="Why is this the right answer? Shown in the results review."
                          onChange={(event) =>
                            changeQuestion(question.id, {
                              explanation: event.target.value,
                            })
                          }
                        />
                        <small>
                          {(question.explanation ?? "").length.toLocaleString()}
                          /5,000
                        </small>
                      </label>
                    )}
                  </div>

                  <div className="qe-foot">
                    <span className="qe-eyebrow">Time to answer</span>

                    <TimePicker
                      question
                      title={`Question ${index + 1} time`}
                      label={
                        `Question ${index + 1} time: ${timeOf(question)} seconds, ` +
                        `${own == null ? "quiz default" : "custom"}. Change`
                      }
                      current={own}
                      defaultTime={editor.defaultTime}
                      onPick={(seconds) => setOwnTime(question.id, seconds)}
                      summaryClass={"qe-tchip" + (own == null ? "" : " is-own")}
                    >
                      <b>{timeOf(question)}s</b>
                      <span className="qe-src">
                        {own == null ? "Quiz default" : "Custom"}
                      </span>
                      <span className="qe-car" aria-hidden="true">
                        ▾
                      </span>
                    </TimePicker>

                    {own != null && (
                      <button
                        type="button"
                        className="ui-linkbtn"
                        onClick={() => setOwnTime(question.id, null)}
                      >
                        Reset to default ({editor.defaultTime}s)
                      </button>
                    )}

                    {editing &&
                      existingQuiz.status === "DRAFT" &&
                      question.questionId && (
                        <div className="qe-question-save">
                          <span
                            className={`is-${questionSaveStatus[question.questionId] ?? "saved"}`}
                            role="status"
                          >
                            {questionSaveStatus[question.questionId] ===
                            "pending"
                              ? "Unsaved changes…"
                              : questionSaveStatus[question.questionId] ===
                                  "saving"
                                ? "Saving…"
                                : questionSaveStatus[question.questionId] ===
                                    "invalid"
                                  ? "Complete this question to autosave"
                                  : questionSaveStatus[question.questionId] ===
                                      "error"
                                    ? "Autosave failed"
                                    : questionSaveStatus[
                                          question.questionId
                                        ] === "conflict"
                                      ? "Editing conflict"
                                      : questionSaveStatus[
                                            question.questionId
                                          ] === "remote"
                                        ? "↻ Updated by collaborator"
                                        : "✓ Saved live"}
                          </span>
                        </div>
                      )}
                  </div>
                </article>
              </div>
            );
          })}

          <button
            type="button"
            className="qe-addq"
            onClick={() =>
              edit({
                ...editor,
                questions: [...editor.questions, newQuestion()],
              })
            }
          >
            <span aria-hidden="true">+</span> Add question
          </button>

          <RequestError error={requestError} />

          {conflict && (
            <div className="qe-conflict">
              <p>
                Your edits are still on this page. Copy anything you want to
                keep before loading the latest saved version.
              </p>

              <button
                type="button"
                className="qb-btn qb-btn-paper"
                disabled={action.busy}
                onClick={async () => {
                  if (
                    await confirmer.confirm({
                      label: "Newer version saved",
                      title: "Load the latest version?",
                      message: "This discards the changes on this page.",
                      confirmLabel: "Load latest",
                      cancelLabel: "Keep my edits",
                    })
                  ) {
                    onReload?.();
                  }
                }}
              >
                Reload latest version
              </button>
            </div>
          )}
        </div>

        <div className="qe-savebar">
          <div className="qe-savebar-in">
            <p className="qe-savebar-msg">
              {validation ? (
                <>
                  <span className="qe-bad" role="alert">
                    {validation}
                  </span>
                  {badQuestion && (
                    <button
                      type="button"
                      className="ui-linkbtn"
                      onClick={() => goToQuestion(badQuestion)}
                    >
                      Show me
                    </button>
                  )}
                </>
              ) : (
                <>
                  <span>{plural(editor.questions.length, "question")}</span>
                  <span className="qe-dim">{clock(totalTime)} total</span>
                </>
              )}
            </p>

            <div className="qe-save-actions">
              <button
                type="button"
                className={"qb-btn" + (canSendFromEditor ? " qb-btn-paper" : "")}
                disabled={
                  conflict ||
                  questionSaving ||
                  Boolean(savingKind) ||
                  archiveAction.busy
                }
                onClick={() => void save()}
              >
                {questionSaving
                  ? "Finishing live save…"
                  : savingKind === "draft"
                    ? "Saving…"
                    : editing
                      ? "Save changes"
                      : "Save draft"}
              </button>

              {canSendFromEditor && (
                <button
                  type="button"
                  className="qb-btn"
                  disabled={
                  conflict ||
                  questionSaving ||
                  Boolean(savingKind) ||
                  archiveAction.busy
                }
                  title="Saves your quiz and sends it to the class organizers. You can host it once they approve it."
                  onClick={() => void save({ send: true })}
                >
                  {savingKind === "send" ? "Sending…" : "Save and send for approval"}
                </button>
              )}
            </div>
          </div>
        </div>
      </fieldset>
    </form>

    {/* Outside the editor's <form>: archive controls remain at the bottom. */}
    {ownsQuiz && (
      <section className="qe-settings" aria-label="Sharing and settings">
        <div className="qe-archive">
          <div>
            <h2>Archive quiz</h2>
            <p>
              Archived quizzes can&apos;t be edited or hosted. Past sessions
              and results stay saved.
            </p>
          </div>
          <button
            type="button"
            className="qb-btn qb-btn-paper qe-archive-button"
            disabled={archiveBlocked}
            onClick={() => void archiveQuiz()}
          >
            {archiveAction.busy ? "Archiving…" : "Archive quiz"}
          </button>
          <RequestError error={archiveAction.error} />
        </div>
      </section>
    )}
    </>
  );
}

export function QuizViewer() {
  const { quizId } = useParams();
  const account = useAccount();
  const action = useAction();
  const validId = /^[1-9][0-9]*$/.test(quizId);

  const resource = useResource(validId ? `/quizzes/${quizId}` : null);
  const flow = useQuizFlow(resource.data ?? null, account.account_id);

  // Opened from a class page (or straight after saving): the back link
  // returns to that class. A save notice from the editor shows once.
  const location = useLocation();
  const navigate = useNavigate();
  const fromClass = location.state?.classId ?? null;
  const [notice, setNotice] = useState(() => location.state?.notice ?? null);
  useEffect(() => {
    if (location.state?.notice) {
      navigate(location.pathname, {
        replace: true,
        state: { classId: location.state.classId },
      });
    }
  }, [location, navigate]);

  if (!validId) {
    return <p role="alert">Invalid quiz ID.</p>;
  }

  if (resource.loading) {
    return <p role="status">Loading quiz…</p>;
  }

  if (resource.error) {
    return <RequestError error={resource.error} retry={resource.reload} />;
  }

  if (!resource.data) return null;

  const quiz = resource.data;
  const mine = quiz.author_id === account.account_id;
  // Owners and organizers see the approval track below the strip, with the
  // next step as its one button. Collaborators and other members keep the
  // simple Draft / Approved pill and a link to the class page.
  const approved = quiz.hosting?.can_host === true;
  const stateLabel =
    quiz.status === "ARCHIVED"
      ? "Archived"
      : flow.state?.label ?? (approved ? "Approved" : "Draft");
  const questions = [...quiz.version.questions].sort(
    (a, b) => a.question_order - b.question_order,
  );
  const totalTime = questions.reduce(
    (sum, question) => sum + Number(question.time_limit_seconds || 0),
    0,
  );

  return (
    <section className="qv" aria-labelledby="quiz-title">
      <div className="qe-bar">
        <Link
          className="qe-back"
          to={classPagePath(fromClass ?? quiz.class_id)}
        >
          <span aria-hidden="true">←</span>
          <span className="qe-back-word">Class</span>
          <span className="ui-sr">Back to class</span>
        </Link>

        <div className="qe-titlebox">
          <span className="qe-eyebrow">Quiz</span>
          <h1 id="quiz-title" className="qv-title">
            {quiz.version.title}
          </h1>
          {quiz.version.description && (
            <p className="qv-description">{quiz.version.description}</p>
          )}
        </div>

        <div className="qe-state">
          <span className={"qe-pill" + (approved ? " is-saved" : "")}>
            {stateLabel} · v{quiz.version.version_number}
          </span>
        </div>
      </div>

      <div className="qv-strip">
        <p className="qv-facts">
          <b>{plural(questions.length, "question")}</b>
          <span>{clock(totalTime)} total</span>
          <span>{quiz.visibility === "PUBLIC" ? "Public" : "Private"}</span>
        </p>

        <div className="qv-actions">
          {mine && (
            <Link
              className="qb-btn qb-btn-paper"
              to={`/app/quizzes/${quiz.quiz_id}/reports`}
            >
              Hosting history
            </Link>
          )}

          {quiz.can_edit && quiz.status !== "ARCHIVED" && (
            <Link
              className="qb-btn qb-btn-paper"
              to={`/app/quizzes/${quiz.quiz_id}/edit`}
            >
              Edit quiz
            </Link>
          )}

          {/* Without the approval track (collaborators, other members),
              keep the previous Host button and class-page link. */}
          {!flow.visible &&
            quiz.class_id &&
            quiz.status !== "ARCHIVED" &&
            approved && (
            <div className="qv-host">
              <HostQuizButton
                quiz={quiz}
                classId={quiz.class_id}
                action={action}
                label="Host live session →"
              />
            </div>
          )}

          {!flow.visible &&
            quiz.class_id &&
            quiz.status !== "ARCHIVED" &&
            !approved &&
            (mine || quiz.can_edit) && (
              <div className="qv-host">
                <Link
                  className="qb-btn"
                  to={`/app/classes/${quiz.class_id}?view=user&section=My%20quizzes`}
                >
                  Send for approval →
                </Link>
              </div>
            )}
        </div>
      </div>

      {notice && (
        <p className={`qf-notice is-${notice.tone}`} role="status">
          {notice.text}
        </p>
      )}

      <QuizFlowPanel
        quiz={quiz}
        flow={flow}
        onChange={(text) => {
          setNotice({ tone: "success", text });
          resource.reload();
        }}
      />

      {mine && quiz.class_id && quiz.status !== "ARCHIVED" && (
        <QuizCollaborators quiz={quiz} />
      )}

      <div className="qe-stack">
        <RequestError error={action.error} />

        {questions.map((question, index) => {
          const choices = [...question.choices].sort(
            (a, b) => a.choice_order - b.choice_order,
          );

          return (
            <div className="qe-item" key={question.question_id}>
              {index > 0 && <div className="qv-gap" aria-hidden="true" />}

              <article className="qe-card qv-card">
                <div className="qe-top">
                  <span>Question {index + 1}</span>
                  <span className="qv-time">
                    {question.time_limit_seconds} sec
                  </span>
                </div>

                <div className="qe-body">
                  <h2 className="qv-qtext">{question.question_text}</h2>

                  <ul className="qe-choices" aria-label="Choices">
                    {choices.map((choice, choiceIndex) => (
                      <li
                        key={choice.choice_id}
                        className={
                          "qe-choice" + (choice.is_correct ? " is-correct" : "")
                        }
                      >
                        <span className="qe-mark" aria-hidden="true">
                          {choice.is_correct ? "✓" : LETTERS[choiceIndex]}
                        </span>
                        <span className="qv-ctext">
                          <span className="ui-sr">
                            {LETTERS[choiceIndex]}.{" "}
                          </span>
                          {choice.choice_text}
                        </span>
                        <span className="qe-choice-end">
                          {choice.is_correct && (
                            <span className="qe-tag">Correct</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="qv-explanation">
                  <span className="qe-eyebrow">Answer explanation</span>
                  <p className={question.explanation ? "" : "qv-none"}>
                    {question.explanation || "No explanation was provided."}
                  </p>
                </div>
              </article>
            </div>
          );
        })}
      </div>
    </section>
  );
}
