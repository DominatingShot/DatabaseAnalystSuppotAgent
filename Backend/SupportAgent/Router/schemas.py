from typing import Literal, Optional
from pydantic import BaseModel, model_validator

class RouteDecision(BaseModel):
    status: Literal["solvable", "not_possible", "out_of_scope"]
    reasoning: str                                   # for logs and evals, not the user
    md_files: list[str] = []
    agent: Optional[Literal["insight", "debug"]] = None
    enhanced_query: Optional[str] = None
    message: Optional[str] = None                    # user-facing text when rejecting

    @model_validator(mode="after")
    def check_fields(self):
        if self.status == "solvable":
            if not (self.md_files and self.agent and self.enhanced_query):
                raise ValueError("solvable requires md_files, agent and enhanced_query")
        elif not self.message:
            raise ValueError("not_possible / out_of_scope require a message")
        return self