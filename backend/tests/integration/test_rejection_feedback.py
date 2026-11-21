from tests.integration.approval_support import approval_class  # noqa: F401


QUIZ = {
    "title": "Review feedback",
    "questions": [{
        "question_text": "Which answer should the reviewer see?",
        "choices": [
            {"choice_text": "First", "is_correct": True},
            {"choice_text": "Second", "is_correct": False},
        ],
    }],
}


def test_collaborator_submission_feedback_and_preview_permissions(approval_class) -> None:
    course = approval_class
    quiz = course.publish("owner", course.create_quiz("owner", QUIZ))
    quiz_id = quiz["quiz_id"]
    share = f"{course.path}/quizzes/{quiz_id}/collaborators"
    for name in ("submitter", "editor"):
        course.request(
            "owner", "POST", share, status=201,
            json={"email": f"{name}@test.invalid", "permission": "EDITOR"},
        )

    submission = course.submit("submitter", quiz)
    submission_id = submission["submission_id"]
    assert submission["submitted_by_id"] == course.accounts["submitter"].account_id
    comment = "Explain the second choice’s wording."
    decision = course.request(
        "organizer", "PATCH", f"{course.path}/quiz-submissions/{submission_id}",
        json={"status": "REJECTED", "rejection_comment": f"  {comment}  "},
    ).json()
    assert (decision["status"], decision["rejection_comment"]) == ("REJECTED", comment)

    preview = f"{course.path}/dashboard/submissions/{submission_id}/preview"
    for name in ("organizer", "submitter"):
        reviewed = course.request(name, "GET", preview).json()
        assert reviewed["submission"]["rejection_comment"] == comment
        assert reviewed["version"]["quiz_version_id"] == quiz["version"]["quiz_version_id"]
        assert reviewed["version"]["questions"][0]["choices"][0]["is_correct"] is True

    mine = f"{course.path}/quizzes"
    for name in ("owner", "editor"):
        [item] = course.request(name, "GET", mine, params={"mine": "true"}).json()["items"]
        assert (item["quiz_id"], item["approval_submission_id"]) == (quiz_id, submission_id)
        assert (item["approval_status"], item["rejection_comment"]) == ("REJECTED", comment)
        assert item["approval_sent_by_me"] is False
        assert course.request(name, "GET", preview, status=404).json()["error"]["code"] == (
            "submission_not_found"
        )

    for name in ("submitter", "editor"):
        course.request(
            "owner", "DELETE", f"{share}/{course.accounts[name].account_id}", status=204
        )
    for name in ("submitter", "editor", "member"):
        assert course.request(name, "GET", mine, params={"mine": "true"}).json()["items"] == []
        assert course.request(name, "GET", preview, status=404).json()["error"]["code"] == (
            "submission_not_found"
        )

    [audit] = course.request("submitter", "GET", f"{course.path}/quiz-submissions").json()
    assert audit["submission_id"] == submission_id
    assert audit["rejection_comment"] is None
    assert course.request("organizer", "GET", preview).json()["submission"]["rejection_comment"] == comment
