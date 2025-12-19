"""
Conversation Store - Manages conversation history for follow-up questions

Stores conversation turns to enable contextual follow-up questions.
Uses in-memory storage by default, can be extended to use Redis.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
import structlog

logger = structlog.get_logger()

# Maximum turns to keep in memory per conversation
MAX_TURNS = 10

# Conversation expiry time (1 hour)
CONVERSATION_TTL_HOURS = 1


@dataclass
class ConversationTurn:
    """A single turn in a conversation"""
    question: str
    answer: str
    query: Optional[str] = None
    intent: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "query": self.query,
            "intent": self.intent,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class Conversation:
    """A conversation with history"""
    conversation_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def add_turn(self, turn: ConversationTurn):
        """Add a turn and maintain max turns limit"""
        self.turns.append(turn)
        self.last_activity = datetime.now()

        # Keep only the most recent turns
        if len(self.turns) > MAX_TURNS:
            self.turns = self.turns[-MAX_TURNS:]

    def is_expired(self) -> bool:
        """Check if conversation has expired"""
        expiry = self.last_activity + timedelta(hours=CONVERSATION_TTL_HOURS)
        return datetime.now() > expiry


class ConversationStore:
    """
    Manages conversation history for follow-up questions.

    Enables the agent to understand context from previous questions
    in the same conversation.
    """

    def __init__(self):
        self._conversations: Dict[str, Conversation] = {}
        self._cleanup_counter = 0

    def get_history(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Get conversation history.

        Args:
            conversation_id: The conversation ID

        Returns:
            List of previous turns as dictionaries
        """
        self._maybe_cleanup()

        conversation = self._conversations.get(conversation_id)

        if not conversation:
            return []

        if conversation.is_expired():
            del self._conversations[conversation_id]
            return []

        return [turn.to_dict() for turn in conversation.turns]

    def add_turn(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        query: Optional[str] = None,
        intent: Optional[str] = None
    ):
        """
        Add a turn to the conversation.

        Args:
            conversation_id: The conversation ID
            question: The user's question
            answer: The assistant's answer
            query: The ShopifyQL query used (optional)
            intent: The classified intent (optional)
        """
        # Get or create conversation
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = Conversation(
                conversation_id=conversation_id
            )

        conversation = self._conversations[conversation_id]

        turn = ConversationTurn(
            question=question,
            answer=answer,
            query=query,
            intent=intent
        )

        conversation.add_turn(turn)

        logger.debug(
            "conversation_turn_added",
            conversation_id=conversation_id,
            turn_count=len(conversation.turns)
        )

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full conversation details.

        Args:
            conversation_id: The conversation ID

        Returns:
            Conversation details or None if not found
        """
        conversation = self._conversations.get(conversation_id)

        if not conversation or conversation.is_expired():
            return None

        return {
            "conversation_id": conversation.conversation_id,
            "turn_count": len(conversation.turns),
            "created_at": conversation.created_at.isoformat(),
            "last_activity": conversation.last_activity.isoformat(),
            "turns": [turn.to_dict() for turn in conversation.turns]
        }

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            logger.info("conversation_deleted", conversation_id=conversation_id)
            return True
        return False

    def get_context_summary(self, conversation_id: str) -> str:
        """
        Get a summary of the conversation context for the LLM.

        Args:
            conversation_id: The conversation ID

        Returns:
            A formatted string summarizing the conversation context
        """
        history = self.get_history(conversation_id)

        if not history:
            return ""

        summary_parts = ["Previous conversation context:"]

        for i, turn in enumerate(history[-3:], 1):  # Last 3 turns
            summary_parts.append(f"\nTurn {i}:")
            summary_parts.append(f"  User asked: {turn['question'][:100]}...")
            if turn.get('intent'):
                summary_parts.append(f"  Intent: {turn['intent']}")
            if turn.get('query'):
                summary_parts.append(f"  Query used: {turn['query'][:100]}...")

        return "\n".join(summary_parts)

    def _maybe_cleanup(self):
        """Periodically clean up expired conversations"""
        self._cleanup_counter += 1

        # Cleanup every 100 operations
        if self._cleanup_counter < 100:
            return

        self._cleanup_counter = 0

        expired = [
            conv_id for conv_id, conv in self._conversations.items()
            if conv.is_expired()
        ]

        for conv_id in expired:
            del self._conversations[conv_id]

        if expired:
            logger.info("conversations_cleaned_up", count=len(expired))

    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics"""
        active_count = sum(
            1 for conv in self._conversations.values()
            if not conv.is_expired()
        )

        total_turns = sum(
            len(conv.turns) for conv in self._conversations.values()
        )

        return {
            "active_conversations": active_count,
            "total_conversations": len(self._conversations),
            "total_turns": total_turns
        }
