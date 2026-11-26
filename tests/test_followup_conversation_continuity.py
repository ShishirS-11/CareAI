
from agents.followup_questions_agent import FollowupQuestionsAgent


class FakeGemini:
    def __init__(self, response):
        self.response = response
        self.prompt = None

    def generate_json(self, prompt):
        self.prompt = prompt
        return self.response


def test_followup_receives_previous_questions_and_answers():
    agent = FollowupQuestionsAgent()
    fake = FakeGemini({
        "question": "How long have you had the pain?",
        "questions_complete": False,
        "missing_information": ["Duration"],
        "rationale_for_question": "Duration is not yet known.",
    })
    agent.llm = fake

    history = [
        {"role": "patient", "content": "I have knee pain."},
        {"role": "assistant", "content": "Which knee is affected?"},
        {"role": "patient", "content": "My right knee."},
    ]

    agent.run(
        {"symptoms": {"complaint": "Knee pain", "side": "right"}},
        history,
    )

    assert "Which knee is affected?" in fake.prompt
    assert "My right knee." in fake.prompt


def test_followup_returns_one_relevant_question():
    agent = FollowupQuestionsAgent()
    agent.llm = FakeGemini({
        "question": "How long have you had the pain?",
        "questions_complete": False,
        "missing_information": ["Duration"],
        "rationale_for_question": "Duration is missing.",
    })

    result = agent.run(
        {"symptoms": {"complaint": "Knee pain"}},
        [],
    )

    assert result["question"] == "How long have you had the pain?"
    assert result["questions_complete"] is False


def test_followup_can_mark_questions_complete():
    agent = FollowupQuestionsAgent()
    agent.llm = FakeGemini({
        "question": None,
        "questions_complete": True,
        "missing_information": [],
        "rationale_for_question": "Enough information is available.",
    })

    result = agent.run(
        {"symptoms": {"complaint": "Knee pain"}},
        [],
    )

    assert result["question"] is None
    assert result["questions_complete"] is True


def test_followup_rejects_non_string_question():
    agent = FollowupQuestionsAgent()
    agent.llm = FakeGemini({
        "question": ["Question 1", "Question 2"],
        "questions_complete": False,
        "missing_information": [],
        "rationale_for_question": "",
    })

    result = agent.run({}, [])

    assert result["question"] is None
