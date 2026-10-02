from app.models import AnswerChoice, Question, QuestionType, QuizVersion
from app.services.quizzes import publication_errors


def valid_version() -> QuizVersion:
    return QuizVersion(
        version_number=1,
        title="Publishable quiz",
        questions=[
            Question(
                question_order=1,
                question_type=QuestionType.MULTIPLE_CHOICE,
                question_text="Question?",
                time_limit_seconds=20,
                base_points=1000,
                choices=[
                    AnswerChoice(
                        choice_order=1, choice_text="Correct", is_correct=True
                    ),
                    AnswerChoice(
                        choice_order=2, choice_text="Incorrect", is_correct=False
                    ),
                ],
            )
        ],
    )


def test_complete_multiple_choice_quiz_is_publishable() -> None:
    assert publication_errors(valid_version()) == []


def test_publication_validation_reports_all_invalid_content() -> None:
    version = valid_version()
    version.title = " "
    question = version.questions[0]
    question.question_order = 2
    question.question_text = " "
    question.time_limit_seconds = 0
    question.base_points = 0
    question.choices = [
        AnswerChoice(choice_order=2, choice_text=" ", is_correct=False)
    ]

    errors = publication_errors(version)

    assert "The quiz title must not be blank." in errors
    assert "Question positions must be consecutive and start at 1." in errors
    assert "Question 2 text must not be blank." in errors
    assert "Question 2 must have at least two choices." in errors
    assert "Question 2 must have at least one correct choice." in errors
    assert "Question 2 choices must not be blank." in errors
