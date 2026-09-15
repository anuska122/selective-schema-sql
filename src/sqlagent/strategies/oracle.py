from sqlagent.eval.dataset import Question
from sqlagent.eval.types import Prediction


class GoldOracle:
    """Returns the gold SQL. A correct harness scores 100% EX with it."""

    name = "gold_oracle"
    config: dict = {}

    def answer(self, question: Question) -> Prediction:
        return Prediction(sql=question.gold_sql)
