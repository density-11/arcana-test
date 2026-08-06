"""Convert UNI streaming chunks into OpenAI-compatible completion objects."""

from types import SimpleNamespace


def _content_text(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, dict):
            text = item.get("text")
        else:
            text = getattr(item, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


class ChatCompletionStreamAccumulator:
    def __init__(self):
        self.content_parts = []
        self.reasoning_parts = []
        self.usage = None
        self.finish_reason = None
        self.response_id = None
        self.model = None

    def add(self, chunk):
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage is not None:
            self.usage = chunk_usage
        self.response_id = getattr(chunk, "id", None) or self.response_id
        self.model = getattr(chunk, "model", None) or self.model
        choices = getattr(chunk, "choices", None) or []
        for choice in choices:
            finish_reason = getattr(choice, "finish_reason", None)
            if finish_reason is not None:
                self.finish_reason = finish_reason
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            content = _content_text(getattr(delta, "content", None))
            if content:
                self.content_parts.append(content)
            reasoning = (
                    getattr(delta, "reasoning", None)
                    or getattr(delta, "reasoning_content", None)
                    )
            if isinstance(reasoning, str):
                self.reasoning_parts.append(reasoning)

    def build(self):
        message = SimpleNamespace(
                content="".join(self.content_parts),
                reasoning="".join(self.reasoning_parts) or None,
                role="assistant",
                )
        choice = SimpleNamespace(
                index=0,
                message=message,
                finish_reason=self.finish_reason,
                )
        return SimpleNamespace(
                id=self.response_id,
                model=self.model,
                choices=[choice],
                usage=self.usage,
                )


def collect_chat_completion_stream(stream):
    accumulator = ChatCompletionStreamAccumulator()
    for chunk in stream:
        accumulator.add(chunk)
    return accumulator.build()


async def collect_async_chat_completion_stream(stream):
    accumulator = ChatCompletionStreamAccumulator()
    async for chunk in stream:
        accumulator.add(chunk)
    return accumulator.build()
