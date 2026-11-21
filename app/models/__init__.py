# Register ORM classes in a consistent order before create_all() runs.
from app.models.user import User
from app.models.status import StatusPost, UserStatus
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.attachment import Attachment

__all__ = ["User", "StatusPost", "UserStatus", "Conversation", "Message", "Attachment"]
