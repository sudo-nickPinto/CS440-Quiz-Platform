from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.models import AnswerChoice, Question, Quiz, QuizVersion


def test_quiz_model_graph_round_trip(mysql_session: Session) -> None:
    unique = uuid4().hex
    account_id = mysql_session.execute(
        text(
            """
            INSERT INTO account (auth0_sub, email, display_name, account_type)
            VALUES (:auth0_sub, :email, :display_name, 'STUDENT')
            """
        ),
        {
            "auth0_sub": f"test|{unique}",
            "email": f"{unique}@example.test",
            "display_name": "Quiz model test",
        },
    ).lastrowid

    quiz = Quiz(
        author_id=account_id,
        versions=[
            QuizVersion(
                version_number=1,
                title="Integration test quiz",
                questions=[
                    Question(
                        question_order=1,
                        question_text="Which answer is correct?",
                        choices=[
                            AnswerChoice(
                                choice_order=1,
                                choice_text="This one",
                                is_correct=True,
                            ),
                            AnswerChoice(
                                choice_order=2,
                                choice_text="Not this one",
                                is_correct=False,
                            ),
                        ],
                    )
                ],
            )
        ],
    )
    mysql_session.add(quiz)
    mysql_session.flush()
    quiz_id = quiz.quiz_id
    mysql_session.expire_all()

    loaded = mysql_session.scalar(
        select(Quiz)
        .where(Quiz.quiz_id == quiz_id)
        .options(
            selectinload(Quiz.versions)
            .selectinload(QuizVersion.questions)
            .selectinload(Question.choices)
        )
    )

    assert loaded is not None
    assert loaded.versions[0].title == "Integration test quiz"
    assert loaded.versions[0].questions[0].choices[0].is_correct is True
    assert loaded.versions[0].questions[0].choices[1].choice_text == "Not this one"
