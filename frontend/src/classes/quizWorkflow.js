export function submissionMatchesQuiz(submission, quiz) {
  return (
    submission.class_id === quiz.class_id &&
    submission.quiz_version_id === quiz.version.quiz_version_id
  );
}

export function canSubmitQuiz(quiz) {
  return (
    quiz.can_edit === true &&
    quiz.status !== "ARCHIVED" &&
    Boolean(quiz.version.published_at)
  );
}

export function canHostApprovedQuiz(approved, accountId, classInfo) {
  return (
    !classInfo.archived &&
    classInfo.membershipStatus === "ACTIVE" &&
    (classInfo.canManage || approved.author_id === accountId)
  );
}

export function paginate(items, requestedPage, pageSize = 12) {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(Math.max(requestedPage, 1), totalPages);

  return {
    page,
    totalPages,
    items: items.slice((page - 1) * pageSize, page * pageSize),
  };
}

export async function loadQuizWorkflow(api, classId, signal, archived = false) {
  const base = `/classes/${classId}`;

  const [submissions, approved] = await Promise.all([
    api(`${base}/quiz-submissions`, { signal }),
    archived
      ? Promise.resolve([])
      : api(`${base}/approved-quizzes`, { signal }),
  ]);

  // The class quiz endpoint is paginated. Read all pages before sorting,
  // filtering, or matching submission versions.
  const summaries = [];
  let page = 1;

  while (true) {
    const result = await api(`${base}/quizzes?page=${page}&page_size=100`, {
      signal,
    });

    summaries.push(...result.items);

    if (page >= result.pagination.total_pages) break;
    page += 1;
  }

  // Details supply can_edit, the version ID, and the review questions.
  // Limit concurrent requests rather than issuing one large burst.
  const quizzes = [];

  for (let offset = 0; offset < summaries.length; offset += 6) {
    const batch = summaries.slice(offset, offset + 6);

    const details = await Promise.all(
      batch.map(async (summary) => {
        try {
          const quiz = await api(`${base}/quizzes/${summary.quiz_id}`, {
            signal,
          });

          return { ...quiz, author_name: summary.author_name };
        } catch (error) {
          // Access may have been revoked after the list was fetched.
          if (error.status === 403 || error.status === 404) return null;
          throw error;
        }
      }),
    );

    quizzes.push(...details.filter(Boolean));
  }

  return { quizzes, submissions, approved };
}
