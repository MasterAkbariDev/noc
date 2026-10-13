import json
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from noc.llm.client import LLMClient, StructuredOutputError
from noc.llm.types import ChatMessage, LLMRequest, LLMResponse, ResponseSchema, Role


@dataclass
class StructuredResult[ModelT: BaseModel]:
    value: ModelT
    responses: list[LLMResponse] = field(default_factory=list)


def response_schema_for(model_type: type[BaseModel]) -> ResponseSchema:
    return ResponseSchema(name=model_type.__name__, json_schema=model_type.model_json_schema())


def extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        stripped = stripped.rsplit("```", 1)[0]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in model output")
    return stripped[start : end + 1]


def parse_model[ModelT: BaseModel](model_type: type[ModelT], content: str | None) -> ModelT:
    if not content:
        raise ValueError("empty model output")
    return model_type.model_validate(json.loads(extract_json(content)))


def repair_message(error: Exception) -> ChatMessage:
    return ChatMessage(
        role=Role.USER,
        content=(
            "Your previous answer was not valid for the required JSON schema. "
            f"Error: {error}. Reply again with only the corrected JSON object."
        ),
    )


async def complete_structured[ModelT: BaseModel](
    llm: LLMClient,
    request: LLMRequest,
    model_type: type[ModelT],
    max_repairs: int = 1,
) -> StructuredResult[ModelT]:
    request = request.model_copy(
        update={"response_schema": response_schema_for(model_type), "tool_choice": "none"}
    )
    responses: list[LLMResponse] = []
    for _attempt in range(max_repairs + 1):
        response = await llm.complete(request)
        responses.append(response)
        try:
            return StructuredResult(parse_model(model_type, response.content), responses)
        except (ValueError, ValidationError) as error:
            messages = [*request.messages, response.as_assistant_message(), repair_message(error)]
            request = request.model_copy(update={"messages": messages})
    raise StructuredOutputError(f"{model_type.__name__} invalid after {max_repairs} repair(s)")
