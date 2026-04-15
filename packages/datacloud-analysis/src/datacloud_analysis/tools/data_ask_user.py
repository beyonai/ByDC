import json
from typing import Optional, Union

from by_framework import AgentContext
from by_framework.common.emitter import _build_sse_layout
from by_framework.core.protocol.events import AskUserEvent
from by_framework.core.protocol.event_type import EventType
from by_framework.core.protocol.agent_state import AgentState

class DataAskUserContext(AgentContext):

    async def complex_ask_user(self, event: Union[AskUserEvent, str], message_id: Optional[str] = None, parent_message_id: Optional[str] = None) -> dict:

        if isinstance(event, str):
            event = AskUserEvent(prompt=event)

        await self.emitter.emit_event(
            session_id=self.session_id,
            trace_id=self.trace_id,
            event_type=EventType.ANSWER_DELTA.value,
            source_agent_type=self.current_agent_id,
            message_id=message_id,
            parent_message_id=parent_message_id,
            data=_build_sse_layout(
                content=json.dumps(
                    {"paradigmList": event.metadata.get("paradigmList",[])}, 
                    ensure_ascii=False),
                role="assistant",
                content_type='3012',
                source_agent_type=self.current_agent_id,
                order_id=message_id,
                parent_order_id=parent_message_id
            ),
            metadata=event.metadata,
        )

        self._is_suspended = True
        return {"status": AgentState.WAITING_USER.value}
